"""Generate German/Spanish TTS voice audio for Thimbleweed Park (piper).

For every English talkie <ACTOR>_<ID>.ogg in the pack:
  - fetch the localized line text from ThimbleweedText_{de,es}.tsv
  - strip stage directions {...} and non-speech *...* bits
  - synthesize with piper (voice per language+gender), trim, loudness-match
    against the English original, encode as Ogg Vorbis
  - produce a .lip file by scaling the English lip-sync timings to the new
    duration
  - if no localized text exists (or nothing speakable remains), fall back to
    copying the English audio/lip

Output: tts_out/<lang>/<actor>_<id>_<lang>.ogg and .lip
"""
import csv
import json
import math
import os
import re
import struct
import subprocess
import sys
import wave
from concurrent.futures import ProcessPoolExecutor, as_completed

from ggpack3 import GGPack

OBB = 'main.65.com.terribletoybox.thimbleweedparkandroid.obb'
OUT_DIR = 'tts_out'
ASSIGN = None  # loaded per worker from cache/voice_assign.json

TAG_RE = re.compile(r'\{[^}]*\}')
STAR_RE = re.compile(r'\*[^*]*\*')
OGG_RE = re.compile(r'^([A-Z0-9]+)_(\d{5})\.ogg$')


def clean_text(t):
    t = TAG_RE.sub(' ', t)
    t = STAR_RE.sub(' ', t)
    t = t.replace('\n', ' ').replace('\r', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    # drop strings that are pure punctuation
    if not re.search(r'\w', t):
        return ''
    return t


def ffmpeg(args):
    return subprocess.run(['ffmpeg', '-v', 'error'] + args, capture_output=True)


def rms_of_wav(path):
    import numpy as np
    with wave.open(path, 'rb') as wf:
        n = wf.getnframes()
        data = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32)
    if len(data) == 0:
        return 0.0, 0.0
    return float(np.sqrt(np.mean(data ** 2)) + 1e-9), n / wf.getframerate()


def trim_silence(samples, rate, thresh=250.0):
    import numpy as np
    a = np.frombuffer(samples, dtype=np.int16).astype(np.float32)
    if len(a) == 0:
        return a
    win = rate // 50  # 20 ms
    nwin = len(a) // win
    if nwin == 0:
        return a
    energy = np.abs(a[:nwin * win]).reshape(nwin, win).mean(axis=1)
    idx = np.where(energy > thresh)[0]
    if len(idx) == 0:
        return a
    start = max(0, idx[0] * win - win // 2)
    end = min(len(a), (idx[-1] + 1) * win + win // 2)
    return a[start:end]


def load_voice(name):
    import onnxruntime
    from piper import PiperVoice

    class _Opts(onnxruntime.SessionOptions):
        def __init__(self):
            super().__init__()
            self.intra_op_num_threads = 2
            self.inter_op_num_threads = 1
            self.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    real = onnxruntime.SessionOptions
    onnxruntime.SessionOptions = _Opts
    try:
        return PiperVoice.load(f'voices/{name}.onnx')
    finally:
        onnxruntime.SessionOptions = real


_VOICE_CACHE = {}
_ENG_RMS = None


def init_worker(rms_map_path):
    global _ENG_RMS, ASSIGN
    with open(rms_map_path) as fh:
        _ENG_RMS = json.load(fh)
    with open('cache/voice_assign.json') as fh:
        ASSIGN = json.load(fh)


def do_line(job):
    try:
        return _do_line(job)
    except Exception as e:
        return (job, f'error: {type(e).__name__}: {e}')


def _do_line(job):
    (actor, oid, lang, text, eng_name, eng_lip_name) = job
    outdir = os.path.join(OUT_DIR, lang)
    os.makedirs(outdir, exist_ok=True)
    base = f'{actor.lower()}_{int(oid):05d}_{lang}'
    ogg_out = os.path.join(outdir, base + '.ogg')
    lip_out = os.path.join(outdir, base + '.lip')
    eng_rms, eng_dur = _ENG_RMS[eng_name]
    if not text:
        # language-neutral fallback: copy english bytes
        from ggpack3 import GGPack
        global _PACK
        try:
            _PACK
        except NameError:
            _PACK = GGPack(OBB)
        data = _PACK.read(eng_name)
        open(ogg_out, 'wb').write(data)
        if eng_lip_name:
            open(lip_out, 'wb').write(_PACK.read(eng_lip_name))
        return (job, 'fallback')

    va = ASSIGN[actor][lang]
    voice_name = va['voice']
    if voice_name not in _VOICE_CACHE:
        _VOICE_CACHE[voice_name] = load_voice(voice_name)
    v = _VOICE_CACHE[voice_name]
    from piper import SynthesisConfig
    syn = SynthesisConfig(length_scale=va['speed'])
    if va.get('speaker') is not None:
        syn.speaker_id = va['speaker']
    chunks = list(v.synthesize(text, syn_config=syn))
    rate = chunks[0].sample_rate
    pcm = b''.join(c.audio_int16_bytes for c in chunks)
    import numpy as np
    a = trim_silence(pcm, rate)
    if len(a) < rate // 4:
        a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    rms = float(np.sqrt(np.mean(a ** 2)) + 1e-9)
    gain = min(12.0, eng_rms / rms) if rms > 0 else 1.0
    a = np.clip(a * gain, -32768, 32767).astype(np.int16)
    new_dur = len(a) / rate

    wav_tmp = ogg_out + '.wav'
    with wave.open(wav_tmp, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(a.tobytes())
    pitch = va.get('pitch', 1.0)
    if abs(pitch - 1.0) > 0.01:
        r = ffmpeg(['-y', '-i', wav_tmp, '-af', f'rubberband=pitch={pitch}',
                    '-c:a', 'libvorbis', '-q:a', '3', '-ar', '22050', '-ac', '1',
                    '-f', 'ogg', ogg_out + '.tmp'])
    else:
        r = ffmpeg(['-y', '-i', wav_tmp, '-c:a', 'libvorbis', '-q:a', '3', '-ar', '22050', '-ac', '1', '-f', 'ogg', ogg_out + '.tmp'])
    os.unlink(wav_tmp)
    if r.returncode != 0:
        return (job, 'ffmpeg-fail: ' + r.stderr.decode()[:200])
    os.replace(ogg_out + '.tmp', ogg_out)

    if eng_lip_name:
        from ggpack3 import GGPack
        try:
            _PACK
        except NameError:
            _PACK = GGPack(OBB)
        lip = _PACK.read(eng_lip_name).decode('utf-8', 'replace')
        out_lines = []
        for line in lip.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) != 2:
                continue
            try:
                t = float(parts[0])
            except ValueError:
                continue
            t2 = t * (new_dur / eng_dur) if eng_dur > 0 else t
            out_lines.append(f'{t2:.2f}\t{parts[1]}')
        open(lip_out, 'w').write('\n'.join(out_lines) + '\n')
    return (job, f'ok dur={new_dur:.2f}')


def _valid_ogg(ogg):
    import subprocess as sp
    if not os.path.exists(ogg) or os.path.getsize(ogg) < 500:
        return False
    with open(ogg, 'rb') as fh:
        if fh.read(4) != b'OggS':
            return False
    r = sp.run(['ffmpeg', '-v', 'error', '-i', ogg, '-f', 'null', '-'],
               capture_output=True)
    return r.returncode == 0


def build_manifest():
    pack = GGPack(OBB)
    texts = {}
    for lang in ('de', 'es'):
        data = pack.read(f'ThimbleweedText_{lang}.tsv').decode('utf-8')
        rows = list(csv.reader(data.splitlines(), delimiter='\t'))
        texts[lang] = {r[0]: r[1] for r in rows[1:] if len(r) >= 2}
    jobs = []
    eng_names = []
    for name in pack.entries:
        m = OGG_RE.match(name)
        if not m:
            continue
        actor, oid = m.group(1), m.group(2)
        lip_name = f'{actor}_{oid}.lip'
        if lip_name not in pack.entries:
            lip_name = None
        eng_names.append(name)
        for lang in ('de', 'es'):
            text = clean_text(texts[lang].get(oid, ''))
            jobs.append((actor, oid, lang, text, name, lip_name))
    return pack, jobs, eng_names


def compute_english_rms(pack, eng_names):
    import numpy as np
    os.makedirs('cache', exist_ok=True)
    path = 'cache/eng_rms.json'
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    out = {}
    for k, name in enumerate(eng_names):
        raw = pack.read(name)
        tmp = f'/tmp/eng_{os.getpid()}.ogg'
        open(tmp, 'wb').write(raw)
        wav = '/tmp/eng_%d.wav' % os.getpid()
        r = ffmpeg(['-y', '-i', tmp, '-c:a', 'pcm_s16le', '-ac', '1', wav])
        if r.returncode == 0:
            rms, dur = rms_of_wav(wav)
            out[name] = [round(rms, 2), round(dur, 3)]
        else:
            out[name] = [1000.0, 1.0]
        os.unlink(tmp)
        if os.path.exists(wav):
            os.unlink(wav)
        if k % 2000 == 0:
            print(f'rms {k}/{len(eng_names)}', flush=True)
    with open(path, 'w') as fh:
        json.dump(out, fh)
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    pack, jobs, eng_names = build_manifest()
    print(f'{len(jobs)} jobs ({len(eng_names)} english lines x2 languages)')
    rms = compute_english_rms(pack, eng_names)
    missing_rms = [j for j in jobs if j[4] not in rms]
    if missing_rms:
        print('missing rms for', len(missing_rms), '— patching')
        for j in missing_rms:
            rms[j[4]] = [1000.0, 1.0]
    if limit:
        jobs = jobs[:limit]
    else:
        # group jobs by (lang, voice, speaker) so each worker loads few models
        import json as _json
        with open('cache/voice_assign.json') as fh:
            _as = _json.load(fh)
        def _vk(j):
            c = _as[j[0]][j[2]]
            return (j[2], c['voice'], c['speaker'] or -1)
        jobs.sort(key=_vk)
    # resume: skip jobs whose output already exists and decodes cleanly
    with ProcessPoolExecutor(max_workers=8) as ex:
        checks = list(ex.map(_valid_ogg, [os.path.join(OUT_DIR, j[2], f'{j[0].lower()}_{int(j[1]):05d}_{j[2]}.ogg') for j in jobs], chunksize=64))
    before = len(jobs)
    jobs = [j for j, ok in zip(jobs, checks) if not ok]
    print(f'resume: {before - len(jobs)} already done, {len(jobs)} to go', flush=True)
    from functools import partial
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    with ProcessPoolExecutor(max_workers=workers, initializer=init_worker,
                             initargs=('cache/eng_rms.json',)) as ex:
        futs = [ex.submit(do_line, j) for j in jobs]
        for k, fut in enumerate(as_completed(futs)):
            try:
                job, status = fut.result()
            except Exception as e:
                print('JOB EXC:', e, flush=True)
                continue
            results[(job[0], job[1], job[2])] = status
            if k % 500 == 0:
                print(f'{k}/{len(jobs)} done', flush=True)
    from collections import Counter
    stat = Counter('ok' if v.startswith(('ok', 'fallback')) else v for v in results.values())
    print(stat)


if __name__ == '__main__':
    main()
