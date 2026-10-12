"""Patch libThimbleweedPark.so (arm64-v8a) so talkie audio/lipsync lookups are
language-dependent.

GameScene::sayLine builds the pack lookup name with the format tail
"%@_%05d.ogg" (0x4d9cc6) / "%@_%05d.lip" (0x4d9d12) from the actor talkie key
and the talkie id, then GGPackfileManager::doesFileExists. We redirect that
block to a code cave that appends a language suffix when the game language is
not English:

    name = "<KEY>_<ID>.ogg"        (lang == en / unknown)
    name = "<KEY>_<ID>_de.ogg"     (lang == de)   etc.

Language source: `_gameLanguageName` (GGString*) at 0x66bfd0, buffer at +0x18,
lowercase code ("en"/"de"/...).
"""
import struct


# ---------------- minimal aarch64 assembler ----------------

def adrp(rd, pc, addr):
    delta = (addr & ~0xFFF) - (pc & ~0xFFF)
    imm = delta >> 12
    assert -(1 << 20) <= imm < (1 << 20)
    return 0x90000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | rd


def add_imm(rd, rn, imm):
    assert 0 <= imm < 0x1000
    return 0x91000000 | (imm << 10) | (rn << 5) | rd


def mov_reg(rd, rm, wide=True):
    return (0xAA0003E0 if wide else 0x2A0003E0) | (rm << 16) | rd


def ldr_imm(rd, rn, byte_off):
    assert byte_off % 8 == 0 and 0 <= byte_off < 0x8000
    return 0xF9400000 | ((byte_off // 8) << 10) | (rn << 5) | rd


def ldrb_imm(rd, rn, byte_off):
    assert 0 <= byte_off < 0x1000
    return 0x39400000 | (byte_off << 10) | (rn << 5) | rd


def cbz(rt, pc, target):
    off = (target - pc) >> 2
    assert -(1 << 18) <= off < (1 << 18)
    return 0xB4000000 | ((off & 0x7FFFF) << 5) | rt


def cmp_imm(rn, imm):
    assert 0 <= imm < 0x1000
    return 0x7100001F | (imm << 10) | (rn << 5)


def b_cond(cond, pc, target):
    off = (target - pc) >> 2
    assert -(1 << 18) <= off < (1 << 18)
    return 0x54000000 | ((off & 0x7FFFF) << 5) | cond


def bl(target, pc):
    off = (target - pc) >> 2
    assert -(1 << 25) <= off < (1 << 25)
    return 0x94000000 | (off & 0x3FFFFFF)


def b(target, pc):
    off = (target - pc) >> 2
    assert -(1 << 25) <= off < (1 << 25)
    return 0x14000000 | (off & 0x3FFFFFF)


NOP = 0xD503201F
EQ = 0
X0, X1, X2, X3, X5, X6 = range(6)
W2, W5, W7 = 2, 5, 7


def build_cave2(cave_addr, fmt_string, lang_global_addr, bl_target, ret_addr, suffixes, strstr_addr=None):
    """Clean two-pass assembler. Returns (code_bytes, str_base dict, str_bytes)."""
    def assemble(str_base):
        out = []
        lbl = {}

        def pc():
            return cave_addr + 4 * len(out)

        out.append(adrp(X0, pc(), str_base['fmt']))
        out.append(add_imm(X0, X0, str_base['fmt'] & 0xFFF))
        out.append(mov_reg(X1, 28))
        out.append(mov_reg(W2, 20, wide=False))
        out.append(adrp(X6, pc(), lang_global_addr))
        out.append(ldr_imm(X6, X6, lang_global_addr & 0xFFF))
        ph = len(out); out.append(0)
        out.append(ldr_imm(X6, X6, 0x18))
        ph2 = len(out); out.append(0)
        out.append(ldrb_imm(W7, X6, 0))
        out.append(cmp_imm(W7, ord('d')))
        bde = len(out); out.append(0)
        out.append(cmp_imm(W7, ord('e')))
        bee = len(out); out.append(0)
        out.append(cmp_imm(W7, ord('f')))
        bfr = len(out); out.append(0)
        out.append(cmp_imm(W7, ord('i')))
        bit = len(out); out.append(0)
        out.append(cmp_imm(W7, ord('r')))
        bru = len(out); out.append(0)
        be1 = len(out); out.append(0)
        es_or_en = pc()
        out.append(ldrb_imm(W7, X6, 1))
        out.append(cmp_imm(W7, ord('s')))
        bes = len(out); out.append(0)
        be2 = len(out); out.append(0)

        done = None
        # NOTE: STR_WITH_STRING clobbers caller-saved regs (x0-x18 incl. x1, w2),
        # so the format-call args (x0 fmt, x1 key, w2 id) must ALL be set after
        # the last intermediate call, immediately before bl bl_target.
        for i, (s, lab) in enumerate(suffixes):
            lbl[lab] = pc()
            out.append(adrp(X3, pc(), str_base[lab]))
            out.append(add_imm(X3, X3, str_base[lab] & 0xFFF))
            out.append(mov_reg(X0, X3))            # x0 = cstr arg
            out.append(bl(strstr_addr if strstr_addr else STR_WITH_STRING, pc()))
            out.append(mov_reg(X3, X0))            # x3 = suffix GGString* (survives: set after call)
            lbl['_skip_%d' % i] = len(out); out.append(0)
        lbl['empty'] = pc()
        out.append(adrp(X3, pc(), str_base['empty']))
        out.append(add_imm(X3, X3, str_base['empty'] & 0xFFF))
        out.append(mov_reg(X0, X3))
        out.append(bl(strstr_addr if strstr_addr else STR_WITH_STRING, pc()))
        out.append(mov_reg(X3, X0))
        done = pc()
        out.append(adrp(X0, pc(), str_base['fmt']))
        out.append(add_imm(X0, X0, str_base['fmt'] & 0xFFF))
        out.append(mov_reg(X1, 28))            # x1 = talkie key GGString* (fresh)
        out.append(mov_reg(W2, 20, wide=False))  # w2 = talkie id (fresh)
        out.append(bl(bl_target, pc()))
        out.append(b(ret_addr, pc()))

        for i in range(len(suffixes)):
            out[lbl['_skip_%d' % i]] = b(done, cave_addr + 4 * lbl['_skip_%d' % i])
        out[ph] = cbz(X6, cave_addr + 4 * ph, lbl['empty'])
        out[ph2] = cbz(X6, cave_addr + 4 * ph2, lbl['empty'])

        out[bde] = b_cond(EQ, cave_addr + 4 * bde, lbl['de'])
        out[bee] = b_cond(EQ, cave_addr + 4 * bee, es_or_en)
        out[bfr] = b_cond(EQ, cave_addr + 4 * bfr, lbl['fr'])
        out[bit] = b_cond(EQ, cave_addr + 4 * bit, lbl['it'])
        out[bru] = b_cond(EQ, cave_addr + 4 * bru, lbl['ru'])
        out[be1] = b(lbl['empty'], cave_addr + 4 * be1)
        out[bes] = b_cond(EQ, cave_addr + 4 * bes, lbl['es'])
        out[be2] = b(lbl['empty'], cave_addr + 4 * be2)
        return out

    # pass 1 for length
    label_names = ['fmt'] + [lab for s, lab in suffixes] + ['empty']
    n = len(assemble({lab: cave_addr for lab in label_names}))
    str_start = cave_addr + 4 * n

    def align4(x):
        return (x + 3) & ~3

    str_base = {}
    off = str_start
    for s, lab in [(fmt_string, "fmt")] + list(suffixes) + [("", "empty")]:
        str_base[lab] = off
        off = align4(off + len(s.encode()) + 1)
    str_bytes = bytearray(off - str_start)
    for s, lab in [(fmt_string, "fmt")] + list(suffixes) + [("", "empty")]:
        sb = s.encode() + b"\x00"
        o = str_base[lab] - str_start
        str_bytes[o:o + len(sb)] = sb
    code = assemble(str_base)
    blob = b"".join(struct.pack("<I", i & 0xFFFFFFFF) for i in code)
    return blob, str_base, bytes(str_bytes)


def find_cave(data, sections, min_bytes):
    text = next(s for s in sections if s['sname'] == '.text')
    off, size, base = text['offset'], text['size'], text['addr']
    chunk = data[off:off + size]
    run, start, runs = 0, None, []
    for i, byte in enumerate(chunk):
        if byte == 0:
            if run == 0:
                start = i
            run += 1
            if run >= min_bytes:
                runs.append((base + start, off + start, run))
                run = 0
        else:
            run = 0
    return runs


# auto-derived at patch time via so_locate (see apply_patch_auto)
STR_WITH_STRING = 0x15CF14  # known-build default; overridden via strstr_addr
SUFFIXES = [("_de", "de"), ("_es", "es"), ("_fr", "fr"), ("_it", "it"), ("_ru", "ru")]
FMT_OGG_STR = "%@_%05d%@.ogg"
FMT_LIP_STR = "%@_%05d%@.lip"


def _addr2off(sections, addr):
    for s in sections:
        if s['addr'] <= addr < s['addr'] + s['size'] and s['sname'] != '.bss':
            return s['offset'] + (addr - s['addr'])
    raise SystemExit(f"addr {addr:#x} not mapped")


def apply_patch_auto(lib_path, out_path, verbose=True):
    """Generic patch: derive all addresses from the binary itself."""
    import so_locate
    info = so_locate.derive(lib_path)
    data = info['data']
    sections = info['secs']
    sites = info['sites']
    buf = bytearray(data)

    runs = find_cave(data, sections, 0x100)
    if verbose:
        print("caves:", [(hex(a), n) for a, o, n in runs[:8]])
    # merge adjacent runs (find_cave cuts long zero regions at min_bytes)
    merged = []
    for addr, off, n in runs:
        if merged and merged[-1][0] + merged[-1][2] == addr:
            merged[-1][2] += n
        else:
            merged.append([addr, off, n])
    runs = [(a, o, n) for a, o, n in merged]
    if verbose:
        print("merged caves:", [(hex(a), n) for a, o, n in runs[:4]])
    assert len(runs) >= 2, "need two code caves"

    jobs = ((sites['audio'][0], FMT_OGG_STR, "audio"),
            (sites['lip'][0], FMT_LIP_STR, "lipsync"))
    for idx, (site, fmt_str, tag) in enumerate(jobs):
        cave_addr, cave_off, cave_len = runs[idx]
        blob, str_base, str_bytes = build_cave2(cave_addr, fmt_str,
                                                info['lang_global'],
                                                info['fmt_plt'],
                                                site + 0x14, SUFFIXES,
                                                strstr_addr=info['strstr'])
        assert len(blob) + len(str_bytes) <= cave_len, (len(blob), len(str_bytes), cave_len)
        buf[cave_off:cave_off + len(blob)] = blob
        buf[cave_off + len(blob):cave_off + len(blob) + len(str_bytes)] = str_bytes
        for k in range(5):
            i = site + 4 * k
            o = _addr2off(sections, i)
            val = b(cave_addr, i) if k == 0 else NOP
            buf[o:o + 4] = struct.pack("<I", val)
        if verbose:
            print(f"patched {tag}: site {site:#x} -> cave {cave_addr:#x} (code {len(blob)}, data {len(str_bytes)})")

    open(out_path, 'wb').write(bytes(buf))
    if verbose:
        print("wrote", out_path)
    return out_path


# backward-compatible alias
apply_patch = apply_patch_auto


if __name__ == '__main__':
    import sys
    apply_patch(sys.argv[1], sys.argv[2])
