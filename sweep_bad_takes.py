"""Detect suspicious (garbled-sounding) TTS clips and regenerate them.

Heuristic: compare each clip's duration against the per-actor median
chars-per-second for that language. Piper occasionally produces bad takes
(garbled or rushed audio); those deviate strongly from the actor's normal
speaking rate. Clips >1.7x faster or <0.45x slower than the actor's median
rate are deleted so the resume pass in tts_build.py resynthesizes them.

Usage: python3 sweep_bad_takes.py            # both languages
"""
import os
import re
import subprocess
import sys
import wave

import numpy as np
import csv

from ggpack3 import GGPack
from tts_build import clean_text

OBB = 'main.65.com.terribletoybox.thimbleweedparkandroid.obb'
PAT = re.compile(r'^([A-Z0-9]+)_(\d{5})\.ogg$')


def text_len(text):
    return max(1, len(text))


def clip_duration(path):
    try:
        with wave.open(path) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return None


def probe(path):
    """Decode via ffmpeg to wav for non-wav inputs; return duration seconds."""
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main():
    pack = GGPack(OBB)
    langs = ('de', 'es') if len(sys.argv) < 2 else (sys.argv[1],)
    stats = {}
    for lang in langs:
        rows = list(csv.reader(open(f'ThimbleweedText_{lang}.tsv'), delimiter='\t'))
        texts = {r[0]: (r[1] if len(r) >= 2 else '') for r in rows[1:]}
        files = [f for f in os.listdir(f'tts_out/{lang}') if f.endswith('.ogg')]
        # per-actor rate
        rates = {}
        for f in files:
            m = re.match(r'^([a-z0-9]+)_(\d{5})_' + lang + r'\.ogg$', f)
            if not m:
                continue
            actor, oid = m.group(1).upper(), m.group(2)
            t = clean_text(texts.get(oid, ''))
            if not t:
                continue
            d = probe(f'tts_out/{lang}/{f}')
            if d and d > 0.2:
                rates.setdefault(actor, []).append(len(t) / d)
        median = {a: float(np.median(v)) for a, v in rates.items() if len(v) >= 5}
        bad = []
        for f in files:
            m = re.match(r'^([a-z0-9]+)_(\d{5})_' + lang + r'\.ogg$', f)
            if not m:
                continue
            actor, oid = m.group(1).upper(), m.group(2)
            med = median.get(actor)
            t = clean_text(texts.get(oid, ''))
            if not med or not t:
                continue
            d = probe(f'tts_out/{lang}/{f}')
            if d is None:
                continue
            r = len(t) / d
            if r > med * 1.7 or r < med * 0.45:
                bad.append((f, round(r, 1), round(med, 1)))
        print(f"{lang}: {len(files)} clips, {len(bad)} suspicious")
        for f, r, med in bad[:20]:
            print(f"   {f} rate={r} vs median {med}")
        for f, _, _ in bad:
            os.unlink(f'tts_out/{lang}/{f}')
            lip = f[:-4] + '.lip'
            if os.path.exists(f'tts_out/{lang}/{lip}'):
                os.unlink(f'tts_out/{lang}/{lip}')
        print(f"{lang}: deleted {len(bad)} clips for resynthesis")


if __name__ == '__main__':
    main()