"""Transcribe ALL generated clips with faster-whisper; flag clips whose ASR
similarity to the source text is low (stutters, artifacts, bad takes).
Standalone + spawn start method (fork after onnxruntime import deadlocks).
Resumable via per-chunk cache files. Audio trimmed to <=15 s per clip.

Usage: python3 asr_sweep.py <lang> [threshold] [workers]
"""
import csv, os, re, sys, json
from collections import defaultdict
import multiprocessing as mp
import numpy as np
import difflib

def norm(s):
    s = s.lower()
    s = re.sub(r'[^a-zäöüßñáéíóúü¿¡ ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def sim(a, b):
    if not a or not b: return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()

def clean_text(t):
    t = re.sub(r'\{[^}]*\}', ' ', t)
    t = re.sub(r'\*[^*]*\*', ' ', t)
    t = t.replace('\\', ' ').replace('"', ' ').replace('\n', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    return t if re.search(r'\w', t) else ''

def load16k(path):
    import subprocess, wave, tempfile
    out = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    out.close()
    subprocess.run(['ffmpeg','-v','error','-y','-i',path,'-ar','16000','-ac','1','-c:a','pcm_s16le',out.name], check=True)
    with wave.open(out.name) as wf:
        a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    os.unlink(out.name)
    return (a.astype(np.float32) / 32768.0)[:15*16000]

_model = None
def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel('tiny', device='cpu', compute_type='int8', cpu_threads=2)
    return _model

def transcribe_sim(f, src, lang):
    a = load16k(f)
    m = get_model()
    segs, _ = m.transcribe(a, language=lang, beam_size=1, condition_on_previous_text=False)
    return sim(norm(' '.join(s.text for s in segs)), src)

def worker(lang, items, out_path):
    res = []
    m = get_model()
    for f, src in items:
        try:
            res.append((os.path.basename(f), round(transcribe_sim(f, src, lang), 3)))
        except Exception:
            res.append((os.path.basename(f), -2.0))
    json.dump(res, open(out_path, 'w'))

def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else 'de'
    thresh = float(sys.argv[2]) if len(sys.argv) > 2 else 0.65
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    CACHE = 'cache/asr_sweep'
    os.makedirs(CACHE, exist_ok=True)
    rows = list(csv.reader(open(f'ThimbleweedText_{lang}.tsv'), delimiter='\t'))
    texts = {r[0]: r[1] for r in rows[1:] if len(r) >= 2}
    pat = re.compile(r'^([a-z0-9]+)_(\d{5})_' + lang + r'\.ogg$')
    items = []
    for f in os.listdir(f'tts_out/{lang}'):
        m = pat.match(f)
        if not m: continue
        src = norm(clean_text(texts.get(m.group(2), '')))
        if not src: continue
        items.append((f'tts_out/{lang}/{f}', src))
    chunks = [items[i:i+50] for i in range(0, len(items), 50)]
    todo = []
    for i, ch in enumerate(chunks):
        cf = f'{CACHE}/{lang}_{i:04d}.json'
        ok = False
        if os.path.exists(cf):
            try:
                d = json.load(open(cf))
                ok = isinstance(d, list) and all(isinstance(t, list) and len(t) == 2 for t in d)
            except Exception:
                ok = False
        if not ok:
            todo.append((i, ch))
        elif not os.path.exists(ch[0][0]):
            pass  # chunk audited, but clip files may have been deleted by a later pass — keep results
    print(f"{lang}: {len(items)} clips, {len(chunks)} chunks, {len(chunks)-len(todo)} cached, {len(todo)} to audit", flush=True)
    ctx = mp.get_context('spawn')
    procs = []
    for i, ch in todo:
        p = ctx.Process(target=worker, args=(lang, ch, f'{CACHE}/{lang}_{i:04d}.json'))
        p.start()
        procs.append(p)
        while sum(1 for q in procs if q.is_alive()) >= workers:
            import time; time.sleep(1)
    for p in procs:
        p.join()
    scored = 0
    flagged = []
    cnt = defaultdict(int)
    for i, ch in enumerate(chunks):
        cf = f'{CACHE}/{lang}_{i:04d}.json'
        if not os.path.exists(cf):
            print(f"MISSING chunk {i}", flush=True); continue
        try:
            cached = json.load(open(cf))
            if not isinstance(cached, list):
                continue
        except Exception:
            continue
        for fname, s in cached:
            scored += 1
            if s < thresh:
                flagged.append((fname, s))
                cnt[os.path.basename(fname).rsplit('_', 2)[0]] += 1
    print(f"{lang}: {scored} clips scored, {len(flagged)} below {thresh}", flush=True)
    for a, c in sorted(cnt.items(), key=lambda x: -x[1])[:14]:
        print(f"   {a}: {c}")
    for f, s in flagged:
        p = f'tts_out/{lang}/{os.path.basename(f)}'
        if os.path.exists(p):
            os.unlink(p)
        lip = p[:-4] + '.lip'
        if os.path.exists(lip): os.unlink(lip)
    print(f"{lang}: deleted {len(flagged)} for re-roll", flush=True)

if __name__ == '__main__':
    main()