"""Delete the generated clips whose TTS input changed (so they get re-rolled).

The text that every clip was made from is remembered in
cache/built_text_<lang>.json (written by tts_build.py).  Every clip whose
text differs from the current text rules is removed from tts_out/<lang>/.

If the manifest does not exist yet it is created from the text of the
previous rules (the ones without the censored-word replacement).

Usage:  python3 tts_fix_changed.py [--dry]
"""
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

import tts_text                                             # noqa: E402
from tts_text import clean_text, clean_text_legacy          # noqa: E402

DRY = '--dry' in sys.argv
LANGS = ('de', 'es')


def read_tsv(lang):
    rows = list(csv.reader(open(f'ThimbleweedText_{lang}.tsv', encoding='utf-8').read().splitlines(),
                             delimiter='\t'))
    return {r[0]: r[1] for r in rows[1:] if len(r) >= 2}


def manifest_path(lang):
    return f'cache/built_text_{lang}.json'


def load_manifest(lang, texts):
    path = manifest_path(lang)
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    # no manifest yet: the clips were made with the previous rules, i.e.
    # without the censored word replacement
    saved = tts_text.replace_censored
    tts_text.replace_censored = lambda t, lang: t
    try:
        m = {tid: clean_text(raw, lang) for tid, raw in texts.items()}
    finally:
        tts_text.replace_censored = saved
    return m


def main():
    total = 0
    for lang in LANGS:
        texts = read_tsv(lang)
        manifest = load_manifest(lang, texts)
        changed = set()
        for tid, raw in texts.items():
            want = clean_text(raw, lang)
            have = manifest.get(tid)
            if have is not None and have != want:
                changed.add(tid)
            elif have is None and clean_text_legacy(raw) != want:
                changed.add(tid)
        d = os.path.join('tts_out', lang)
        removed = 0
        for f in sorted(os.listdir(d)):
            m = re.match(r'^[a-z0-9]+_(\d{5})_%s\.(ogg|lip)$' % lang, f)
            if not m or m.group(1) not in changed:
                continue
            if not DRY:
                os.unlink(os.path.join(d, f))
            removed += 1
        print(f'{lang}: {len(changed)} lines changed -> {removed // 2} clips'
              f'{" [dry run]" if DRY else ""}')
        total += removed // 2
    print(f'total clips to re-roll: {total}')


if __name__ == '__main__':
    main()
