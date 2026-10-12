"""Full end-to-end verification of the patched cave.

Emulates: cave -> real GGVSPrintf (via its PLT, with strnlen + %@-vtable hooks)
and asserts the final lookup filename for every language. This validates the
actual arguments of the stringWithFormat call (the bug that escaped the earlier
cave-only test).
"""
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_LITTLE_ENDIAN, UcError, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_X28, UC_ARM64_REG_W20, UC_ARM64_REG_SP, UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
)
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
import unicorn.arm64_const as ac

from disasm import load_elf
import so_locate

# caller-saved integer regs a real callee may trash (x0-x18); x19-x28 callee-saved
REGS_TO_TRASH = [getattr(ac, f'UC_ARM64_REG_X{i}') for i in range(1, 19)]

STACK = 0x80000000
HEAP = 0x90000000
RET_STOP = 0x40000000


class Harness:
    def __init__(self, so_path):
        self.data, self.sections, self.syms = load_elf(so_path)
        e_phoff, = struct.unpack_from('<Q', self.data, 0x20)
        e_phentsize, e_phnum = struct.unpack_from('<HH', self.data, 0x36)
        self.mu = mu = Uc(UC_ARCH_ARM64, UC_MODE_LITTLE_ENDIAN)
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, _ = \
                struct.unpack_from('<IIQQQQQQ', self.data, off)
            if p_type == 1:
                base = p_vaddr & ~0xFFF
                size = (p_vaddr + p_memsz - base + 0xFFF) & ~0xFFF
                try:
                    mu.mem_map(base, size)
                except UcError:
                    pass
                mu.mem_write(p_vaddr, self.data[p_offset:p_offset + p_filesz])
        mu.mem_map(STACK, 0x100000)
        mu.mem_map(HEAP, 0x400000)
        mu.mem_map(RET_STOP, 0x1000)

        self.strnlen = next(a for a, n in self.syms.items()
                            if n == 'plt:strnlen')
        # fake vtable for fake GGString objects: slot 0x38 -> ret stub
        self.vt = HEAP + 0x600
        self.ret_stub = HEAP + 0x700
        mu.mem_write(self.vt + 0x38, struct.pack('<Q', self.ret_stub))
        mu.mem_write(self.ret_stub, b'\xc0\x03\x5f\xd6')  # ret
        self.alloc_ptr = HEAP + 0x1000

    def info_syms(self):
        return self.syms

    def alloc(self, n):
        p = (self.alloc_ptr + 15) & ~15
        self.alloc_ptr = p + n
        return p

    def cstr(self, s):
        p = self.alloc(len(s) + 1)
        self.mu.mem_write(p, s.encode() + b'\x00')
        return p

    def ggstring(self, s):
        obj = self.alloc(0x40)
        c = self.cstr(s)
        self.mu.mem_write(obj, struct.pack('<Q', self.vt))
        self.mu.mem_write(obj + 0x18, struct.pack('<Q', c))
        return obj

    def read_cstr(self, addr, maxlen=64):
        raw = self.mu.mem_read(addr, maxlen)
        return raw.split(b'\0')[0].decode('latin-1')


def run(so_path, orig_path, cave, lang, verbose=False):
    h = Harness(so_path)
    h.info = so_locate.derive(orig_path)
    mu = h.mu
    # language global -> fake GGString with buffer
    lang_obj = h.ggstring(lang)
    mu.mem_write(h.info['lang_global'], struct.pack('<Q', lang_obj))
    # talkie key / id as sayLine would have them
    key_obj = h.ggstring("RAY")
    mu.reg_write(UC_ARM64_REG_X28, key_obj)
    mu.reg_write(UC_ARM64_REG_W20, 1234)

    events = {'strstr': [], 'fmt': None}
    STRW = h.info['strstr']
    FMT_PLT = h.info['fmt_plt']
    GGVSP = next(a for a, n in h.syms.items() if n == '_Z10GGVSPrintfPciPKcSt9__va_list')

    def hook(uc, address, size, ud):
        if address == STRW:
            x0 = uc.reg_read(UC_ARM64_REG_X0)
            c = uc.mem_read(x0, 8).split(b'\0')[0].decode()
            events['strstr'].append(c)
            # return a fresh fake GGString wrapping that cstr
            uc.reg_write(UC_ARM64_REG_X0, h.ggstring(c))
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
        elif address == FMT_PLT:
            x0 = uc.reg_read(UC_ARM64_REG_X0)
            x1 = uc.reg_read(UC_ARM64_REG_X1)
            x2 = uc.reg_read(UC_ARM64_REG_X2)
            x3 = uc.reg_read(UC_ARM64_REG_X3)
            fmt = bytes(uc.mem_read(x0, 24)).split(b'\0')[0].decode()
            # record and REDIRECT into the real GGVSPrintf with these args
            events['fmt'] = (fmt, x1, x2, x3)
            # GGVSPrintf(buf, size, fmt, va_list) — rearrange args
            gr = h.alloc(64)
            uc.mem_write(gr, struct.pack('<QQQ', x1, x2, x3))
            va = h.alloc(64)
            uc.mem_write(va + 0, struct.pack('<Q', 0))          # __stack
            uc.mem_write(va + 8, struct.pack('<Q', gr + 24))    # __gr_top
            uc.mem_write(va + 16, struct.pack('<Q', gr + 24))   # __vr_top
            uc.mem_write(va + 24, struct.pack('<i', -24))       # __gr_offs
            uc.mem_write(va + 28, struct.pack('<i', 0))
            outbuf2 = h.alloc(0x200)
            uc.reg_write(UC_ARM64_REG_X0, outbuf2)
            uc.reg_write(UC_ARM64_REG_X1, 0x2000)
            uc.reg_write(UC_ARM64_REG_X2, x0)   # fmt cstr
            uc.reg_write(UC_ARM64_REG_X3, va)
            events['outbuf'] = outbuf2
            uc.reg_write(UC_ARM64_REG_LR, RET_STOP)
            uc.reg_write(UC_ARM64_REG_PC, GGVSP)
        elif address == h.strnlen:
            x0 = uc.reg_read(UC_ARM64_REG_X0)
            n = 0
            while uc.mem_read(x0 + n, 1) != b'\x00':
                n += 1
            uc.reg_write(UC_ARM64_REG_X0, n)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
    mu.hook_add(UC_HOOK_CODE, hook)

    # output buffer
    outbuf = h.alloc(0x200)
    mu.reg_write(UC_ARM64_REG_SP, STACK + 0x80000)
    mu.reg_write(UC_ARM64_REG_X0, outbuf)
    mu.reg_write(UC_ARM64_REG_X1, 0x2710)
    mu.emu_start(cave, RET_STOP, count=500000)
    ob = events.get('outbuf', outbuf)
    out = bytes(mu.mem_read(ob, 64)).split(b'\0')[0].decode()
    return out, events


if __name__ == '__main__':
    import sys
    so = sys.argv[1] if len(sys.argv) > 1 else 'patched_arm64.so'
    orig = sys.argv[2] if len(sys.argv) > 2 else 'apk_extracted/lib/arm64-v8a/libThimbleweedPark.so'
    import so_patch
    info = so_locate.derive(orig)
    # cave targets: branch instruction at each site in the PATCHED lib
    data, sections, _ = load_elf(so)
    from so_patch import _addr2off
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    caves = {}
    for tag, site in (('audio', info['sites']['audio'][0]), ('lipsync', info['sites']['lip'][0])):
        o = _addr2off(sections, site)
        ins = next(md.disasm(data[o:o + 4], site))
        caves[tag] = int(ins.op_str.lstrip('#'), 0)
    print("caves:", {k: hex(v) for k, v in caves.items()})
    ok = True
    for tag, cave in caves.items():
        ext = '.lip' if tag == 'lipsync' else '.ogg'
        expect = {'en': 'RAY_01234' + ext, 'de': 'RAY_01234_de' + ext,
                  'es': 'RAY_01234_es' + ext, 'fr': 'RAY_01234_fr' + ext,
                  'it': 'RAY_01234_it' + ext, 'ru': 'RAY_01234_ru' + ext,
                  'zz': 'RAY_01234' + ext}
        for lang, exp in expect.items():
            out, ev = run(so, orig, cave, lang)
            status = 'OK' if out == exp else f'FAIL exp {exp}'
            if out != exp:
                ok = False
            print(f"{tag:8s} {lang!r:6} -> {out!r:22} {status}   strstr={ev['strstr']}")
    print("END-TO-END:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)