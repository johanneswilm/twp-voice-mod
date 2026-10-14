"""Unicorn harness for the OBB-fallback thunks (see so_patch_obb.py).

Emulates the patched library's executable segment, intercepts the PLT stubs
with Python fakes for fopen/fgets/fclose/fseek/stat, and checks:
  1. hook_fopen: real fopen fails + <path>.ref parses -> APK handle returned,
     g_offset/g_size/g_apk_file set, initial seek performed
  2. hook_fseek: SEEK_SET adjusted by offset for the fallback handle only,
     SEEK_END -> offset+size, other handles untouched
  3. hook_stat: stat failure with active fallback -> synthetic buffer with
     st_size at bionic offset 48
  4. hook_fclose: fallback handle clears the globals
"""
import os
import struct
import sys

import so_patch
import so_patch_obb
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM
import capstone
from unicorn import *
from unicorn.arm64_const import *

import so_patch_obb as _spo
_stubs = _spo.find_plt_stubs('/tmp/engine_step2.so',
                             _spo.find_got_addrs('/tmp/engine_step2.so',
                                                 {'fopen', 'fseek', 'stat', 'fclose', 'fgets', 'open', 'write', 'close'}))
PLT = {'fopen': _stubs['fopen'], 'fseek': _stubs['fseek'], 'stat': _stubs['stat'],
       'fclose': _stubs['fclose'], 'fgets': _stubs['fgets'],
       'open': _stubs['open'], 'write': _stubs['write'], 'close': _stubs['close']}
G = _spo.rw_globals_base(open('/tmp/engine_step2.so', 'rb').read())
CAVE = 0x1df1c4

LIB = sys.argv[1] if len(sys.argv) > 1 else '/tmp/engine_step2.so'


class FakeLibc:
    def __init__(self):
        self.files = {}         # path -> bytes
        self.next_handle = 0x100
        self.handles = {}       # handle -> {'data': bytes, 'pos': int, 'name': str}
        self.log = []           # (op, args...)

    def open(self, path, _mode):
        self.log.append(('fopen', path))
        if path in self.files:
            h = self.next_handle
            self.next_handle += 4
            self.handles[h] = {'data': self.files[path], 'pos': 0, 'name': path}
            return h
        return 0

    def fgets(self, h, maxlen):
        f = self.handles[h]
        data = f['data']
        idx = f['pos']
        nl = data.find(b'\n', idx)
        end = nl + 1 if nl >= 0 else len(data)
        line = data[idx:min(end, idx + maxlen - 1)]
        if not line:
            return None
        f['pos'] += len(line)
        self.log.append(('fgets', f['name'], line))
        return line

    def close(self, h):
        self.log.append(('fclose', self.handles[h]['name']))
        del self.handles[h]
        return 0

    def fseek(self, h, off, whence):
        self.log.append(('fseek', self.handles[h]['name'] if h in self.handles else h, off, whence))
        if whence == 0 and h in self.handles:
            self.handles[h]['pos'] = off
        return 0

    def stat(self, path, _buf):
        self.log.append(('stat', path))
        return -1


def make_uc(fake):
    lib = open(LIB, 'rb').read()
    uc = Uc(UC_ARCH_ARM64, UC_MODE_LITTLE_ENDIAN)
    seg_sz = 0x5f43b0
    uc.mem_map(0, (seg_sz + 0xFFF) & ~0xFFF, UC_PROT_ALL)
    uc.mem_write(0, lib[:seg_sz])
    uc.mem_map(G & ~0xFFF, 0x2000, UC_PROT_ALL)
    STACK = 0x7000000
    uc.mem_map(STACK, 0x100000, UC_PROT_ALL)
    SCRATCH = 0x8000000
    uc.mem_map(SCRATCH, 0x10000, UC_PROT_ALL)
    MAGIC_RET = 0x9000000
    uc.mem_map(MAGIC_RET, 0x1000)

    def hook_plt(uc, address, size, user_data):
        name = [k for k, a in PLT.items() if a == address]
        if not name:
            return
        name = name[0]
        x0 = uc.reg_read(UC_ARM64_REG_X0)
        x1 = uc.reg_read(UC_ARM64_REG_X1)
        x2 = uc.reg_read(UC_ARM64_REG_X2)
        lr = uc.reg_read(UC_ARM64_REG_LR)
        if name == 'fopen':
            path = bytes(uc.mem_read(x0, 300)).split(b'\0')[0].decode()
            uc.reg_write(UC_ARM64_REG_X0, fake.open(path, 'rb'))
        elif name == 'fgets':
            line = fake.fgets(x2, x1)
            if line is None:
                uc.reg_write(UC_ARM64_REG_X0, 0)
            else:
                uc.mem_write(x0, line)
                uc.reg_write(UC_ARM64_REG_X0, x0)
        elif name == 'fclose':
            uc.reg_write(UC_ARM64_REG_X0, fake.close(x0))
        elif name == 'fseek':
            uc.reg_write(UC_ARM64_REG_X0, fake.fseek(x0, x1, x2 & 0xFFFFFFFF))
        elif name == 'stat':
            path = bytes(uc.mem_read(x0, 300)).split(b'\0')[0].decode()
            uc.reg_write(UC_ARM64_REG_X0, fake.stat(path, x1) & 0xFFFFFFFFFFFFFFFF)
        elif name == 'open':
            uc.reg_write(UC_ARM64_REG_X0, 0)   # trace file not emulated
        elif name == 'write':
            uc.reg_write(UC_ARM64_REG_X0, x2)
        elif name == 'close':
            uc.reg_write(UC_ARM64_REG_X0, 0)
        uc.reg_write(UC_ARM64_REG_PC, lr)

    uc.hook_add(UC_HOOK_CODE, hook_plt, begin=0x1408c0, end=0x1408c0 + 0x16160)

    seen = []
    uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u: seen.append(a))

    def call(addr, args):
        seen.clear()
        for i, v in enumerate(args):
            uc.reg_write(UC_ARM64_REG_X0 + i, v)
        # callee-saved canaries: thunks must preserve x19-x28
        for i, r in enumerate((UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X22,
                               UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X25, UC_ARM64_REG_X26,
                               UC_ARM64_REG_X27, UC_ARM64_REG_X28)):
            uc.reg_write(r, 0xC0FFEE0000000000 + i)
        uc.reg_write(UC_ARM64_REG_SP, STACK + 0x80000)
        uc.reg_write(UC_ARM64_REG_LR, MAGIC_RET)
        uc.emu_start(addr, MAGIC_RET)
        for i, r in enumerate((UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X22,
                               UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X25, UC_ARM64_REG_X26,
                               UC_ARM64_REG_X27, UC_ARM64_REG_X28)):
            v = uc.reg_read(r)
            assert v == 0xC0FFEE0000000000 + i, f'callee-saved x{19+i} clobbered: {v:#x}'
        if os.environ.get('TWP_TRACE'):
            print('  pcs:', [hex(p) for p in seen[:40]])

    return uc, call, SCRATCH


def run():
    code, thunks, _ = so_patch_obb.assemble_cave(CAVE, PLT, G)
    print('thunks:', {k: hex(v) for k, v in thunks.items()})
    ok = []

    # --- 1. hook_fopen fallback
    fake = FakeLibc()
    fake.files['/data/app/base.apk'] = b'PK\x03\x04' + b'A' * 200
    fake.files['/storage/obb/main.65.pkg.obb.ref'] = b'/data/app/base.apk\n4096\n12345678\n'
    uc, call, SCRATCH = make_uc(fake)
    refpath = b'/storage/obb/main.65.pkg.obb\0'
    uc.mem_write(SCRATCH, refpath)
    call(thunks['fopen'], [SCRATCH, 0])
    x0 = uc.reg_read(UC_ARM64_REG_X0)
    print('  fake.log:', fake.log)
    print('  x0:', hex(x0), 'globals:',
          hex(struct.unpack('<Q', uc.mem_read(G + 8, 8))[0]),
          hex(struct.unpack('<Q', uc.mem_read(G + 0x10, 8))[0]),
          hex(struct.unpack('<Q', uc.mem_read(G + 0x18, 8))[0]))
    assert x0 == 0x104, f'fopen fallback returned {x0:#x}'
    off = struct.unpack('<Q', uc.mem_read(G + 8, 8))[0]
    size = struct.unpack('<Q', uc.mem_read(G + 0x10, 8))[0]
    apkf = struct.unpack('<Q', uc.mem_read(G + 0x18, 8))[0]
    assert (off, size, apkf) == (4096, 12345678, 0x104), (off, size, apkf)
    print('  fake.log:', fake.log)
    print('  globals:', hex(struct.unpack('<Q', uc.mem_read(G + 8, 8))[0]),
          hex(struct.unpack('<Q', uc.mem_read(G + 0x10, 8))[0]),
          hex(struct.unpack('<Q', uc.mem_read(G + 0x18, 8))[0]))
    seeks = [e for e in fake.log if e[0] == 'fseek']
    assert ('fseek', '/data/app/base.apk', 4096, 0) in seeks, seeks
    ok.append('hook_fopen fallback + config parse + initial seek')

    # --- 2. hook_fseek adjustments (same uc/globals as test 1)
    fake.log.clear()
    call(thunks['fseek'], [0x104, 5, 0])
    assert ('fseek', '/data/app/base.apk', 4096 + 5, 0) in fake.log, fake.log
    call(thunks['fseek'], [0x777, 5, 0])
    assert ('fseek', 0x777, 5, 0) in fake.log, fake.log
    call(thunks['fseek'], [0x104, 77, 1])
    assert ('fseek', '/data/app/base.apk', 77, 1) in fake.log, fake.log
    call(thunks['fseek'], [0x104, 0, 2])
    assert ('fseek', '/data/app/base.apk', 4096 + 12345678, 0) in fake.log, fake.log
    ok.append('hook_fseek SEEK_SET/CUR/END')

    # --- 3. hook_stat synthesis
    fake.log.clear()
    buf = SCRATCH + 0x1000
    call(thunks['stat'], [SCRATCH, buf])
    w0 = uc.reg_read(UC_ARM64_REG_X0)
    st_size = struct.unpack('<Q', uc.mem_read(buf + 48, 8))[0]
    assert w0 == 0 and st_size == 12345678, (w0, st_size)
    ok.append('hook_stat synthetic st_size')

    # --- 4. hook_fclose clears
    call(thunks['fclose'], [0x104])
    apkf = struct.unpack('<Q', uc.mem_read(G + 0x18, 8))[0]
    assert apkf == 0, apkf
    ok.append('hook_fclose clears globals')

    # --- 5. pass-through when no fallback (fresh uc)
    fake2 = FakeLibc()
    uc2, call2, SCRATCH2 = make_uc(fake2)
    fake2.log.clear()
    call2(thunks['fseek'], [0x777, 9, 1])
    assert ('fseek', 0x777, 9, 1) in fake2.log
    call2(thunks['stat'], [SCRATCH2, SCRATCH2 + 0x1000])
    w0 = uc2.reg_read(UC_ARM64_REG_X0)
    assert w0 == 0xFFFFFFFFFFFFFFFF, hex(w0)
    ok.append('pass-through without fallback')

    print('PASS:')
    for line in ok:
        print('  \u2713', line)


if __name__ == '__main__':
    run()
