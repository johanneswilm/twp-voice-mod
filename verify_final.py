"""Validate the final modded OBB."""
import hashlib
import os
import random
import re
import sys

from ggpack3 import GGPack

SRC = 'main.65.com.terribletoybox.thimbleweedparkandroid.obb'
DST = 'dist/main.81.com.terribletoybox.thimbleweedparkandroid.obb'
OGG_RE = re.compile(r'^([A-Z0-9]+)_(\d{5})\.ogg$')


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    src = GGPack(SRC)
    dst = GGPack(DST)
    print(f"src entries: {len(src.entries)}  dst entries: {len(dst.entries)}")

    src_names = set(src.entries)
    dst_names = {n.lower() for n in dst.entries}
    missing = [n for n in src_names if n.lower() not in dst_names]
    print("originals missing from dst:", len(missing), missing[:5])

    # integrity: sample original entries, byte-compare
    random.seed(42)
    sample = random.sample(sorted(src_names), 80)
    bad = 0
    for n in sample:
        a, b = src.read(n), dst.read(n)
        if md5(a) != md5(b):
            bad += 1
            print("  MISMATCH:", n)
    print(f"original entry sample: {len(sample) - bad}/{len(sample)} intact")

    # language coverage
    pairs = {OGG_RE.match(n).groups() for n in src_names if OGG_RE.match(n)}
    miss_de = [p for p in pairs if f"{p[0]}_{p[1]}_de.ogg".lower() not in dst_names]
    miss_es = [p for p in pairs if f"{p[0]}_{p[1]}_es.ogg".lower() not in dst_names]
    print(f"de coverage: {len(pairs) - len(miss_de)}/{len(pairs)}  missing: {miss_de[:5]}")
    print(f"es coverage: {len(pairs) - len(miss_es)}/{len(pairs)}  missing: {miss_es[:5]}")

    # audio sanity: every new ogg must start with OggS
    badogg = 0
    checked = 0
    for n in dst.entries:
        ln = n.lower()
        if ln.endswith('_de.ogg') or ln.endswith('_es.ogg'):
            head = dst.read(n)[:4]
            checked += 1
            if head != b'OggS':
                badogg += 1
                if badogg < 5:
                    print("  BAD OGG:", n, head)
    print(f"new audio checked: {checked}, bad: {badogg}")

    # lip sanity
    badlip = 0
    for n in dst.entries:
        ln = n.lower()
        if ln.endswith('_de.lip') or ln.endswith('_es.lip'):
            head = dst.read(n)[:16]
            try:
                float(head.split(b'\t')[0])
            except Exception:
                badlip += 1
                if badlip < 5:
                    print("  BAD LIP:", n, head[:24])
    print("bad lips:", badlip)
    print("dst size:", os.path.getsize(DST) / 1e9, "GB")
    print("VERDICT:", "PASS" if (not missing and bad == 0 and badogg == 0) else "FAIL")


if __name__ == '__main__':
    main()
