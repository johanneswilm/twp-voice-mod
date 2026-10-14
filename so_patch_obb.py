"""Deep engine patch: read the OBB directly out of the installed APK.

The Android engine (1.0.10) opens its data pack (the OBB) exclusively from the
external expansion-file path; an assets/obb embedded in the APK is ignored
("Can't open file '<...>/main.65.<pkg>.obb'"). Embedding + extracting would
duplicate ~1.5 GB of storage permanently. Instead, we make the engine read the
pack bytes straight from the APK file:

- The Java wrapper writes a small "<obb path>.ref" file next to where the OBB
  would live, containing three lines: APK path, embedded start offset,
  embedded length (assets/obb is ZIP_STORED, so its bytes are contiguous
  inside the APK).
- We redirect every direct `bl <plt>` call site of fopen / fseek / stat /
  fclose in .text to thunks in a code cave:

  hook_fopen:  real fopen first; on failure look for "<path>.ref"; if present,
               parse it, fopen the APK, seek to the embedded offset, remember
               the FILE* and set the fallback flag, and return it.
  hook_fseek:  for the fallback FILE*, SEEK_SET += offset, SEEK_END ->
               offset+size, SEEK_CUR passes through (the region maps linearly).
  hook_stat:   the pack loader stats the pack when its size is unknown; if the
               stat fails while the fallback is active, synthesize a stat
               buffer whose st_size (= bionic offset 48) is the pack size.
  hook_fclose: clear the fallback handle.

Everything else passes through untouched, so with a normal external OBB (split
layout) the engine behaves exactly as before. The thunks call the real libc
functions through their original PLT stubs (we redirect call sites, not GOT
entries, so RELRO is irrelevant).

The mere existence of "<obb path>.ref" is what identifies the OBB path - no
path comparison is needed; only our mod ever writes .ref files there.

Cave globals (32 bytes) live in the writable zero padding after .bss at the
end of the RW LOAD segment.
"""
import struct

import so_locate
import so_patch
from so_patch import (adrp, add_imm, mov_reg, ldr_imm, ldrb_imm, cbz, cmp_imm,
                      b_cond, bl, b, NOP, EQ)

NE = 1

# ---------------- extra aarch64 encodings ----------------

def str_imm(rt, rn, byte_off=0):
    assert byte_off % 8 == 0 and 0 <= byte_off < 0x8000
    return 0xF9000000 | ((byte_off // 8) << 10) | (rn << 5) | rt


def str_w_imm(rt, rn, byte_off=0):
    assert byte_off % 4 == 0 and 0 <= byte_off < 0x4000
    return 0xB9000000 | ((byte_off // 4) << 10) | (rn << 5) | rt


def strb_imm(rt, rn, byte_off=0):
    assert 0 <= byte_off < 0x1000
    return 0x39000000 | (byte_off << 10) | (rn << 5) | rt


def add_reg(rd, rn, rm):
    return 0x8B000000 | (rm << 16) | (rn << 5) | rd


def add_sp_reg(rd, rn, rm):
    """ADD Xd, SP, Xm"""
    return 0x8B200000 | (rm << 16) | (rn << 5) | rd


def sub_imm64(rd, rn, imm):
    assert 0 <= imm < 0x1000
    return 0xD1000000 | (imm << 10) | (rn << 5) | rd


def cmp_reg(rn, rm):
    return 0xEB000000 | (rm << 16) | (rn << 5) | 0x1F


def cbnz(rt, pc, target):
    off = (target - pc) >> 2
    assert -(1 << 18) <= off < (1 << 18)
    return 0xB5000000 | ((off & 0x7FFFF) << 5) | rt


RET = 0xD65F03C0
HI = 8  # unsigned higher (HS/CS = 2)
X0, X1, X2, X3, X8, X9, X10 = 0, 1, 2, 3, 8, 9, 10
W0, W1, W2, W3, W8, W9, W10, W21 = 0, 1, 2, 3, 8, 9, 10, 21
X19, X20, X21, X22 = 19, 20, 21, 22
X29, X30, SP, XZR = 29, 30, 31, 31


def stp_pre(rt, rt2, rn, byte_off):
    imm7 = (byte_off // 8) & 0x7F
    return 0xA9800000 | (imm7 << 15) | (rt2 << 10) | (rn << 5) | rt


def ldp_post(rt, rt2, rn, byte_off):
    imm7 = (byte_off // 8) & 0x7F
    return 0xA8C00000 | (imm7 << 15) | (rt2 << 10) | (rn << 5) | rt


def stp_off(rt, rt2, rn, byte_off):
    imm7 = (byte_off // 8) & 0x7F
    return 0xA9000000 | (imm7 << 15) | (rt2 << 10) | (rn << 5) | rt


def ldp_off(rt, rt2, rn, byte_off):
    imm7 = (byte_off // 8) & 0x7F
    return 0xA9400000 | (imm7 << 15) | (rt2 << 10) | (rn << 5) | rt


def movz(rd, imm16, hw=0):
    return 0x52800000 | (hw << 21) | (imm16 << 5) | rd


def movz64(rd, imm16, hw=0):
    return 0xD2800000 | (hw << 21) | (imm16 << 5) | rd


def movk(rd, imm16, hw=0):
    return 0x72800000 | (hw << 21) | (imm16 << 5) | rd


def madd(rd, rn, rm, ra):
    return 0x9B000000 | (rm << 16) | (ra << 10) | (rn << 5) | rd


def sub_w_imm(rd, rn, imm):
    assert 0 <= imm < 0x1000
    return 0x51000000 | (imm << 10) | (rn << 5) | rd


def add_imm64(rd, rn, imm):
    assert 0 <= imm < 0x1000
    return 0x91000000 | (imm << 10) | (rn << 5) | rd


# ---------------- binary scans ----------------

def derive_secs(lib_path):
    """Minimal ELF64 section header parse (works on patched libs too)."""
    data = open(lib_path, 'rb').read()
    e_shoff = struct.unpack_from('<Q', data, 0x28)[0]
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', data, 0x3A)
    raw = []
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        name, typ, _flags, addr, off, size = struct.unpack_from('<IIQQQQ', data, o)
        raw.append({'name': name, 'type': typ, 'addr': addr, 'offset': off, 'size': size})
    strtab = raw[e_shstrndx]
    for s in raw:
        start = strtab['offset'] + s['name']
        s['sname'] = data[start:data.index(b'\0', start)].decode()
    return raw


def find_got_addrs(lib_path, names):
    """GOT slot addresses for imported symbol names (JUMP_SLOT relocs)."""
    data = open(lib_path, 'rb').read()
    secs = {s['sname']: s for s in derive_secs(lib_path)}
    dynsym, dynstr = secs['.dynsym'], secs['.dynstr']
    nsym = dynsym['size'] // 24
    sym = []
    for i in range(nsym):
        o = dynsym['offset'] + 24 * i
        nameoff = struct.unpack_from('<I', data, o)[0]
        start = dynstr['offset'] + nameoff
        name = data[start:data.index(b'\0', start)].decode()
        sym.append(name)
    got = {}
    for sname in ('.rela.dyn', '.rela.plt'):
        s = secs[sname]
        for i in range(s['size'] // 24):
            o = s['offset'] + 24 * i
            off, rinfo, _ = struct.unpack_from('<QQq', data, o)
            if rinfo & 0xFFFFFFFF != 0x402:  # R_AARCH64_JUMP_SLOT
                continue
            symidx = rinfo >> 32
            if symidx < len(sym) and sym[symidx] in names:
                got[sym[symidx]] = off
    return got


def find_plt_stubs(lib_path, got_addrs):
    """PLT stub address per GOT slot (stub = adrp page; ldr [page, lo])."""
    from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM
    import capstone
    data = open(lib_path, 'rb').read()
    secs = {s['sname']: s for s in derive_secs(lib_path)}
    plt = secs['.plt']
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    out = {}
    for off in range(plt['offset'], plt['offset'] + plt['size'], 16):
        page = None
        for ins in md.disasm(data[off:off + 16], plt['addr'] + (off - plt['offset'])):
            if ins.mnemonic == 'adrp' and ins.operands[1].type == ARM64_OP_IMM:
                page = ins.operands[1].imm
            elif ins.mnemonic == 'ldr' and ins.operands[1].type == ARM64_OP_MEM and page is not None:
                got = page + ins.operands[1].mem.disp
                for k, a in got_addrs.items():
                    if a == got:
                        out[k] = plt['addr'] + (off - plt['offset'])
    return out


def find_bl_sites(lib_path, target):
    import capstone
    data = open(lib_path, 'rb').read()
    secs = {s['sname']: s for s in derive_secs(lib_path)}
    text = secs['.text']
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_LITTLE_ENDIAN)
    sites = []
    pos = 0
    end = text['size']
    while pos < end:
        reached = pos
        for ins in md.disasm(data[text['offset'] + pos:text['offset'] + end],
                             text['addr'] + pos):
            reached = ins.address - text['addr'] + ins.size
            if ins.mnemonic == 'bl':
                try:
                    if int(ins.op_str.lstrip('#'), 16) == target:
                        sites.append(ins.address)
                except ValueError:
                    pass
        # linear sweep stalled (e.g. embedded data) - resync 4 bytes past it
        pos = reached + 4 if reached <= pos else reached
    return sites


def rw_globals_base(data):
    """32 writable bytes in the zero padding after .bss in the RW LOAD segment."""
    e_phoff = struct.unpack_from('<Q', data, 0x20)[0]
    e_phentsize, e_phnum = struct.unpack_from('<HH', data, 0x36)
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_flags = struct.unpack_from('<II', data, o)
        if p_type == 1 and p_flags & 2:  # PT_LOAD, PF_W
            p_vaddr = struct.unpack_from('<Q', data, o + 0x10)[0]
            p_memsz = struct.unpack_from('<Q', data, o + 0x28)[0]
            return (p_vaddr + p_memsz - 32) & ~7
    raise SystemExit('no writable LOAD segment')


# ---------------- cave assembly ----------------

class Asm:
    def __init__(self, base):
        self.base = base
        self.ins = []
        self.fix = []
        self.labels = {}

    def pc(self):
        return self.base + 4 * len(self.ins)

    def emit(self, *ws):
        self.ins.extend(w & 0xFFFFFFFF for w in ws)

    def lbl(self, name):
        self.labels[name] = self.pc()
        return name

    def _fix(self, kind, *args):
        self.fix.append((len(self.ins), kind, args))
        self.ins.append(0)

    def br(self, l):
        self._fix('b', l)

    def bc(self, cond, l):
        self._fix('bc', cond, l)

    def jcbz(self, rt, l):
        self._fix('cbz', rt, l)

    def jcbnz(self, rt, l):
        self._fix('cbnz', rt, l)

    def call(self, l):
        self._fix('bl', l)

    def resolve(self):
        for idx, kind, args in self.fix:
            tgt = self.labels[args[-1]]
            pc = self.base + 4 * idx
            if kind == 'b':
                self.ins[idx] = b(tgt, pc)
            elif kind == 'bl':
                self.ins[idx] = bl(tgt, pc)
            elif kind == 'bc':
                self.ins[idx] = b_cond(args[0], pc, tgt)
            elif kind == 'cbz':
                self.ins[idx] = cbz(args[0], pc, tgt)
            elif kind == 'cbnz':
                self.ins[idx] = cbnz(args[0], pc, tgt)

    def blob(self):
        return b''.join(struct.pack('<I', w) for w in self.ins)


def _build(cave_addr, plt, g, str_rb):
    """str_rb: (addr) of the const "rb" string placed right after the code."""
    a = Asm(cave_addr)
    E = a.emit

    # ---- local_strlen(x0) -> x1
    a.lbl('strlen')
    E(movz64(X1, 0))
    a.lbl('strlen_loop')
    E(ldrb_imm(W8, X0, 0))
    a.jcbz(W8, 'strlen_done')
    E(add_imm(X0, X0, 1), add_imm(X1, X1, 1))
    a.br('strlen_loop')
    a.lbl('strlen_done')
    E(RET)

    # ---- local_copy_cstr(x0=dst, x1=src)
    a.lbl('copy')
    a.lbl('copy_loop')
    E(ldrb_imm(W8, X1, 0))
    a.jcbz(W8, 'copy_done')
    E(strb_imm(W8, X0, 0), add_imm(X0, X0, 1), add_imm(X1, X1, 1))
    a.br('copy_loop')
    a.lbl('copy_done')
    E(RET)

    # ---- strip_nl(x0)
    a.lbl('stripnl')
    a.lbl('snl_loop')
    E(ldrb_imm(W8, X0, 0))
    a.jcbz(W8, 'snl_done')
    E(cmp_imm(W8, 0x0A))
    a.bc(EQ, 'snl_hit')
    E(add_imm(X0, X0, 1))
    a.br('snl_loop')
    a.lbl('snl_hit')
    E(strb_imm(XZR, X0, 0))
    a.lbl('snl_done')
    E(RET)

    # ---- parse_dec(x0) -> x0
    a.lbl('pdec')
    E(movz64(X1, 0), movz64(X2, 10))
    a.lbl('pdec_loop')
    E(ldrb_imm(W8, X0, 0), sub_w_imm(W8, W8, 0x30))
    E(cmp_imm(W8, 9))
    a.bc(HI, 'pdec_done')
    E(madd(X1, X1, X2, X8), add_imm(X0, X0, 1))  # acc = acc*10 + digit (x8 = c-'0')
    a.br('pdec_loop')
    a.lbl('pdec_done')
    E(mov_reg(X0, X1), RET)

    # ---- hook_fclose(x0)
    a.lbl('fclose')
    E(stp_pre(X29, X30, SP, -48), stp_off(X19, X20, SP, 16))
    E(mov_reg(X19, X0))
    E(adrp(X8, a.pc(), g + 0x18))
    E(ldr_imm(X8, X8, (g + 0x18) & 0xFFF))          # g_apk_file
    a.jcbz(X8, 'fc_do')
    E(cmp_reg(X0, X8))
    a.bc(NE, 'fc_do')
    E(adrp(X9, a.pc(), g + 0x18), str_imm(XZR, X9, (g + 0x18) & 0xFFF))
    a.lbl('fc_do')
    E(mov_reg(X0, X19))
    E(bl(plt['fclose'], a.pc()))
    E(ldp_post(X29, X30, SP, 48), RET)

    # ---- hook_fseek(x0=f, x1=off, w2=whence)
    a.lbl('fseek')
    E(stp_pre(X29, X30, SP, -48), stp_off(X19, X20, SP, 16))
    E(mov_reg(X19, X0), mov_reg(X20, X1), mov_reg(X21, X2))
    E(adrp(X8, a.pc(), g + 0x18))
    E(ldr_imm(X8, X8, (g + 0x18) & 0xFFF))
    a.jcbz(X8, 'fs_plain')
    E(cmp_reg(X19, X8))
    a.bc(NE, 'fs_plain')
    E(cmp_imm(W21, 0))
    a.bc(NE, 'fs_notset')
    E(adrp(X8, a.pc(), g + 0x08), ldr_imm(X8, X8, (g + 0x08) & 0xFFF))
    E(add_reg(X20, X20, X8))
    a.br('fs_plain')
    a.lbl('fs_notset')
    E(cmp_imm(W21, 2))
    a.bc(NE, 'fs_plain')
    E(adrp(X8, a.pc(), g + 0x08), ldr_imm(X8, X8, (g + 0x08) & 0xFFF))
    E(adrp(X9, a.pc(), g + 0x10), ldr_imm(X9, X9, (g + 0x10) & 0xFFF))
    E(add_reg(X20, X8, X9))
    E(movz(W21, 0))                              # absolute -> SEEK_SET
    a.lbl('fs_plain')
    E(mov_reg(X0, X19), mov_reg(X1, X20), mov_reg(W2, W21))
    E(bl(plt['fseek'], a.pc()))
    E(ldp_post(X29, X30, SP, 48), RET)

    # ---- hook_stat(x0=path, x1=buf)
    a.lbl('stat')
    E(stp_pre(X29, X30, SP, -48), stp_off(X19, X20, SP, 16))
    E(mov_reg(X19, X0), mov_reg(X20, X1))
    E(bl(plt['stat'], a.pc()))
    a.jcbz(W0, 'st_out')              # stat succeeded -> pass through
    E(adrp(X8, a.pc(), g + 0x18))
    E(ldr_imm(X8, X8, (g + 0x18) & 0xFFF))
    a.jcbz(X8, 'st_out')              # fallback not active -> pass through
    # zero the 120-byte bionic struct stat, then fill st_size (offset 48) and
    # the adjacent pad (40) with the pack size
    E(mov_reg(X9, X20), movz(W10, 120))
    a.lbl('st_zero')
    E(strb_imm(XZR, X9, 0), add_imm(X9, X9, 1), sub_w_imm(W10, W10, 1))
    a.jcbnz(W10, 'st_zero')
    E(adrp(X8, a.pc(), g + 0x10), ldr_imm(X8, X8, (g + 0x10) & 0xFFF))
    E(str_imm(X8, X20, 40), str_imm(X8, X20, 48))
    E(movz(W0, 0))
    a.lbl('st_out')
    E(ldp_post(X29, X30, SP, 48), RET)

    # ---- load_config_full(path) -> FILE* or NULL
    # stack: fp/lr at [sp+0x400], x19/x20 at +0x410, x21/x22 at +0x420,
    # buffers below: +0x000 l1[260], +0x104 l2[64], +0x144 l3[64], +0x190 refpath[260]
    a.lbl('loadcfg')
    E(stp_pre(X29, X30, SP, -16))
    E(sub_imm64(SP, SP, 0x430))
    E(stp_off(X19, X20, SP, 0x400), stp_off(X21, X22, SP, 0x410))
    E(mov_reg(X19, X0))                          # path
    E(movz(W21, 0))                              # result = NULL
    # refpath = path + ".ref"
    E(mov_reg(X0, X19))
    a.call('strlen')
    E(mov_reg(X22, X1))                          # len
    E(add_imm(X0, SP, 0x190))                    # dst
    E(mov_reg(X1, X19))                          # src
    a.call('copy')
    E(add_imm(X8, SP, 0x190))                    # refpath
    E(add_reg(X8, X8, X22))                      # + len
    E(movz(W9, 0x722E), movk(W9, 0x6665, 1))     # ".ref"
    E(str_w_imm(W9, X8, 0))
    E(add_imm(X8, X8, 4), strb_imm(XZR, X8, 0))
    # fopen(refpath, "rb")
    E(add_imm(X0, SP, 0x190))
    E(adrp(X1, a.pc(), str_rb))
    E(add_imm(X1, X1, str_rb & 0xFFF))
    E(bl(plt['fopen'], a.pc()))
    a.jcbz(X0, 'lc_done')
    E(mov_reg(X20, X0))                          # cf
    E(add_imm(X0, SP, 0x000), movz(W1, 260), mov_reg(X2, X20))
    E(bl(plt['fgets'], a.pc()))
    E(add_imm(X0, SP, 0x104), movz(W1, 64), mov_reg(X2, X20))
    E(bl(plt['fgets'], a.pc()))
    E(add_imm(X0, SP, 0x144), movz(W1, 64), mov_reg(X2, X20))
    E(bl(plt['fgets'], a.pc()))
    E(mov_reg(X0, X20))
    E(bl(plt['fclose'], a.pc()))
    E(add_imm(X0, SP, 0x000))                    # strip \n from apk path line
    a.call('stripnl')
    # g_offset = parse_dec(l2); g_size = parse_dec(l3)
    E(add_imm(X0, SP, 0x104))
    a.call('pdec')
    E(adrp(X8, a.pc(), g + 0x08), str_imm(X0, X8, (g + 0x08) & 0xFFF))
    E(add_imm(X0, SP, 0x144))
    a.call('pdec')
    E(adrp(X8, a.pc(), g + 0x10), str_imm(X0, X8, (g + 0x10) & 0xFFF))
    # open the apk and seek to the embedded pack
    E(add_imm(X0, SP, 0x000))                    # l1 = apk path
    E(adrp(X1, a.pc(), str_rb))
    E(add_imm(X1, X1, str_rb & 0xFFF))
    E(bl(plt['fopen'], a.pc()))
    a.jcbz(X0, 'lc_done')
    E(mov_reg(X21, X0))
    E(adrp(X8, a.pc(), g + 0x08), ldr_imm(X1, X8, (g + 0x08) & 0xFFF))
    E(mov_reg(X0, X21), movz(W2, 0))             # fseek(f, offset, SEEK_SET)
    E(bl(plt['fseek'], a.pc()))
    E(adrp(X8, a.pc(), g + 0x18))
    E(str_imm(X21, X8, (g + 0x18) & 0xFFF))                    # g_apk_file = f
    E(movz(W9, 1), str_w_imm(W9, X8, 0x00))      # flags = 1
    E(mov_reg(W0, W21))
    a.lbl('lc_done')
    E(ldp_off(X21, X22, SP, 0x410), ldp_off(X19, X20, SP, 0x400))
    E(add_imm64(SP, SP, 0x430))
    E(ldp_post(X29, X30, SP, 16), RET)

    # ---- hook_fopen(x0=path, x1=mode)
    a.lbl('fopen')
    E(stp_pre(X29, X30, SP, -48), stp_off(X19, X20, SP, 16))
    E(mov_reg(X19, X0))
    E(bl(plt['fopen'], a.pc()))
    a.jcbnz(X0, 'fo_out')
    E(mov_reg(X0, X19))
    a.call('loadcfg')                            # -> FILE* or NULL in x0
    a.lbl('fo_out')
    E(ldp_off(X19, X20, SP, 16))
    E(ldp_post(X29, X30, SP, 48), RET)

    a.resolve()
    thunks = {k: a.labels[k] for k in ('fopen', 'fseek', 'stat', 'fclose')}
    return a.blob(), thunks


def assemble_cave(cave_addr, plt, g):
    """Two passes: code size is address-independent, string sits after code."""
    _build(cave_addr, plt, g, cave_addr)
    n = len(_build(cave_addr, plt, g, cave_addr)[0])
    str_addr = cave_addr + n
    code, thunks = _build(cave_addr, plt, g, str_addr)
    assert len(code) == n
    # labels are absolute already
    return code, thunks, b'rb\0'


def apply(lib_path, out_path, verbose=True):
    data = open(lib_path, 'rb').read()
    buf = bytearray(data)
    got = find_got_addrs(lib_path, {'fopen', 'fseek', 'stat', 'fclose', 'fgets'})
    missing = {'fopen', 'fseek', 'stat', 'fclose', 'fgets'} - set(got)
    assert not missing, f'missing imports: {missing}'
    plt = find_plt_stubs(lib_path, got)
    if verbose:
        print('plt:', {k: hex(v) for k, v in plt.items()})
    g = rw_globals_base(data)
    if verbose:
        print('globals at', hex(g))

    secs = derive_secs(lib_path)
    runs = so_patch.find_cave(data, secs, 0x800)
    merged = []
    for addr, off, n in runs:
        if merged and merged[-1][0] + merged[-1][2] == addr:
            merged[-1][2] += n
        else:
            merged.append([addr, off, n])
    cave_addr, cave_off, cave_len = max(merged, key=lambda r: r[2])
    if cave_addr % 4:                      # arm64 code must be 4-byte aligned
        pad = 4 - cave_addr % 4
        cave_addr += pad
        cave_off += pad
        cave_len -= pad
    if verbose:
        print(f'cave: {cave_addr:#x} ({cave_len} bytes)')

    code, thunks, strbytes = assemble_cave(cave_addr, plt, g)
    assert len(code) + len(strbytes) <= cave_len
    buf[cave_off:cave_off + len(code)] = code
    buf[cave_off + len(code):cave_off + len(code) + len(strbytes)] = strbytes

    for name in ('fopen', 'fseek', 'stat', 'fclose'):
        sites = find_bl_sites(lib_path, plt[name])
        assert sites, f'no call sites for {name}'
        for site in sites:
            o = so_patch._addr2off(secs, site)
            buf[o:o + 4] = struct.pack('<I', bl(thunks[name], site))
        if verbose:
            print(f'{name}: {len(sites)} sites -> {thunks[name]:#x}')

    open(out_path, 'wb').write(bytes(buf))
    if verbose:
        print('wrote', out_path)
    return out_path


if __name__ == '__main__':
    import sys
    apply(sys.argv[1], sys.argv[2])
