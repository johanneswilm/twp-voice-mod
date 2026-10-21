"""ASR-verify the clips that were re-rolled after the text fix.

For every line whose TTS input changed (old cleaning vs. new cleaning) the
regenerated clip is transcribed with faster-whisper and compared with the new
source text.  It also reports clips that still contain the old artefacts
("backslash", "sarcastic", "dont translate", ...).

Usage:  python3 tts_verify_fixed.py [de|es] [threshold] [workers]
"""
import csv
import concurrent.futures
import multiprocessing
import os
import re
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

from tts_text import clean_text, clean_text_legacy  # noqa: E402

ARTEFACTS = ['backslash', 'wechsel', 'back slash', 'sarkastisch', 'sarcastic',
             'dont translate', 'don t translate', 'nicht übersetzen', 'markenzeichen',
             'nummer f', 'nummer m', 'armadillo', 'hash f', 'hash m', 'prozent', 'dollar']

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel('tiny', device='cpu', compute_type='int8', cpu_threads=2)
    return _model


def norm(s):
    s = s.lower()
    s = re.sub(r'[^a-zäöüßñáéíóúü¿¡ ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def sim(a, b):
    import difflib
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def load16k(path):
    out = f'/tmp/_vf_{os.getpid()}.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', path, '-ar', '16000', '-ac', '1',
                    '-c:a', 'pcm_s16le', out], check=True)
    with wave.open(out, 'rb') as wf:
        a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    return a.astype(np.float32) / 32768.0


def read_tsv(lang):
    rows = list(csv.reader(open(f'ThimbleweedText_{lang}.tsv', encoding='utf-8').read().splitlines(),
                             delimiter='\t'))
    return {r[0]: r[1] for r in rows[1:] if len(r) >= 2}


def worker(args):
    lang, items = args
    model = get_model()
    out = []
    for path, src in items:
        try:
            a = load16k(path)
            segs, _ = model.transcribe(a, language=lang, beam_size=1,
                                       condition_on_previous_text=False)
            tr = ' '.join(s.text.strip() for s in segs)
        except Exception as e:
            tr = f'<error {e}>'
        out.append((os.path.basename(path), tr, src))
    return out


def main():
    langs = [a for a in sys.argv[1:] if a in ('de', 'es')] or ['de', 'es']
    thresh = 0.65
    workers = 8
    for a in sys.argv[1:]:
        if a in ('de', 'es'):
            continue
        try:
            v = float(a)
        except ValueError:
            continue
        if v == int(v) and int(v) >= 3:
            workers = int(v)
        else:
            thresh = v
    import multiprocessing as mp
    for lang in langs:
        texts = read_tsv(lang)
        changed = {tid: raw for tid, raw in texts.items()
                   if clean_text_legacy(raw) != clean_text(raw, lang)}
        d = f'tts_out/{lang}'
        items = []
        for f in sorted(os.listdir(d)):
            m = re.match(r'^[a-z0-9]+_(\d{5})_%s\.ogg$' % lang, f)
            if m and m.group(1) in changed:
                items.append((os.path.join(d, f), norm(clean_text(texts[m.group(1)], lang))))
        print(f'== {lang}: {len(items)} re-rolled clips', flush=True)
        chunks = [items[i:i + 40] for i in range(0, len(items), 40)]
        results = []
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers,
                                                    mp_context=multiprocessing.get_context('spawn')) as ex:
            for res in ex.map(worker, [(lang, ch) for ch in chunks]):
                results.extend(res)
        scores = []
        flagged = []
        hits = []
        for f, tr, src in results:
            s = sim(norm(tr), src)
            scores.append(s)
            if s < thresh:
                flagged.append((f, s, tr, src))
            low = tr.lower()
            for art in ARTEFACTS:
                if art in low:
                    hits.append((f, art, tr))
        scores.sort()
        n = len(scores) or 1
        print(f'  scored {n}  min={scores[0]:.2f}  p5={scores[n//20]:.2f}  '
              f'median={scores[n//2]:.2f}  below {thresh}: {len(flagged)}')
        for f, s, tr, src in flagged[:30]:
            print(f'   LOW {f} {s:.2f}\n       asr: {tr[:140]}\n       src: {src[:140]}')
        for f, art, tr in hits[:30]:
            print(f'   ARTEFACT {f} contains "{art}": {tr[:140]}')


if __name__ == '__main__':
    main()
