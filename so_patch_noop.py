"""Experiment C: no-op cave patch.

Same patch mechanism as so_patch (branch out to a code cave, call the original
stringWithFormat with the ORIGINAL 2-argument format string, branch back), but
without any language logic — byte-for-byte behaviorally identical to the
original code.
"""
import struct

import so_locate
from so_patch import (adrp, add_imm, mov_reg, bl, b, NOP, X0, X1, W2,
                      find_cave, _addr2off)


def apply_noop_patch(lib_path, out_path, verbose=True):
    info = so_locate.derive(lib_path)
    data = info['data']
    sections = info['secs']
    sites = info['sites']
    fmt_plt = info['fmt_plt']
    buf = bytearray(data)

    runs = find_cave(data, sections, 0x40)
    if verbose:
        print("caves:", [(hex(a), n) for a, o, n in runs[:8]])
    assert len(runs) >= 2

    for idx, (site, fmt_addr, tag) in enumerate(((sites['audio'][0], sites['audio'][1], "audio"),
                                                 (sites['lip'][0], sites['lip'][1], "lipsync"))):
        cave_addr, cave_off, cave_len = runs[idx]
        code = []
        pc = cave_addr
        code.append(adrp(X0, pc, fmt_addr))
        code.append(add_imm(X0, X0, fmt_addr & 0xFFF))
        code.append(mov_reg(X1, 28))
        code.append(mov_reg(W2, 20, wide=False))
        pc = cave_addr + 16
        code.append(bl(fmt_plt, pc))
        pc = cave_addr + 20
        code.append(b(site + 0x14, pc))
        blob = b"".join(struct.pack("<I", i & 0xFFFFFFFF) for i in code)
        assert len(blob) <= cave_len
        buf[cave_off:cave_off + len(blob)] = blob
        for k in range(5):
            i = site + 4 * k
            o = _addr2off(sections, i)
            val = b(cave_addr, i) if k == 0 else NOP
            buf[o:o + 4] = struct.pack("<I", val)
        if verbose:
            print(f"noop-patched {tag}: site {site:#x} -> cave {cave_addr:#x}")

    open(out_path, 'wb').write(bytes(buf))
    if verbose:
        print("wrote", out_path)


if __name__ == '__main__':
    import sys
    apply_noop_patch(sys.argv[1], sys.argv[2])
