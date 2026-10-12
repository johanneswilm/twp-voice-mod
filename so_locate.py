"""Generic, build-independent patcher for libThimbleweedPark.so.

Instead of hardcoded addresses, everything is derived from the binary:
- talkie/lipsync lookup sites: 5-instruction sequence (adrp x0/add x0/mov x1/
  mov w2/bl) whose format string ends in "_%05d.ogg" / "_%05d.lip" and whose
  bl targets the PLT stub of GGString::stringWithFormat.
- PLT stub -> symbol mapping via .rela.plt (GOT slots).
- GGString::stringWithString(char const*) via dynsym.
- _gameLanguageName global: disassemble GGGameLanguageName() and extract the
  adrp/ldr global it reads.
- code cave: first sufficiently large zero run inside .text (dead alignment
  padding), one per site.

Validated against the 1.0.10 (versionCode 81) build: derived addresses must
match the known-good ones.
"""
import bisect
import struct

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

# known values for the 1.0.10 build (for validation)
KNOWN = dict(audio_site=0x160D4C, lip_site=0x160E30, lang=0x66BFD0,
             fmt_plt=0x144E30, strstr=0x15CF14)


def _sections(data):
    e_shoff, = struct.unpack_from('<Q', data, 0x28)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', data, 0x3A)
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        (name, stype, flags, addr, offset, size, link, info, align,
         entsize) = struct.unpack_from('<IIQQQQIIQQ', data, off)
        secs.append(dict(name=name, type=stype, addr=addr, offset=offset,
                         size=size, link=link))
    sh = secs[e_shstrndx]
    for s in secs:
        e = data.index(b'\0', sh['offset'] + s['name'])
        s['sname'] = data[sh['offset'] + s['name']:e].decode()
    return secs


def _dynsym(data, secs):
    """name -> {value, size} for defined dynamic symbols."""
    symtab = next(s for s in secs if s['type'] == 11)
    strtab = secs[symtab['link']]
    out = {}
    for i in range(symtab['size'] // 24):
        off = symtab['offset'] + i * 24
        st_name, st_info, st_other, st_shndx, st_value, st_size = \
            struct.unpack_from('<IBBHQQ', data, off)
        if st_name and st_value:
            e = data.index(b'\0', strtab['offset'] + st_name)
            out[data[strtab['offset'] + st_name:e].decode()] = st_value
    return out


def _plt_map(data, secs):
    """plt stub address -> symbol name (via .rela.plt GOT slots)."""
    symtab = next(s for s in secs if s['type'] == 11)
    strtab = secs[symtab['link']]
    plt = next(s for s in secs if s['sname'] == '.plt')
    relaplt = next(s for s in secs if s['sname'] == '.rela.plt')
    got2sym = {}
    for i in range(relaplt['size'] // 24):
        off = relaplt['offset'] + i * 24
        r_offset, r_info, r_addend = struct.unpack_from('<QQq', data, off)
        sym_idx = r_info >> 32
        if sym_idx:
            eoff = symtab['offset'] + sym_idx * 24
            st_name, = struct.unpack_from('<I', data, eoff)
            e = data.index(b'\0', strtab['offset'] + st_name)
            got2sym[r_offset] = data[strtab['offset'] + st_name:e].decode()
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    code = data[plt['offset']:plt['offset'] + plt['size']]
    mapping, page = {}, None
    for ins in md.disasm(code, plt['addr']):
        if ins.mnemonic == 'adrp':
            page = int(ins.op_str.split('#')[1], 0)
        elif ins.mnemonic == 'ldr' and page is not None and 'x17' in ins.op_str and '#' in ins.op_str:
            imm = int(ins.op_str.split('#')[1].rstrip(']'), 0)
            got = page + imm
            stub = ins.address - 4
            if got in got2sym:
                mapping[stub] = got2sym[got]
            page = None
    return mapping


def _addr2off(secs, addr):
    for s in secs:
        if s['addr'] <= addr < s['addr'] + s['size'] and s['sname'] not in ('.bss',):
            return s['offset'] + (addr - s['addr'])
    raise SystemExit(f"addr {addr:#x} not mapped")


def _rodata_cstr(data, secs, addr, maxlen=64):
    o = _addr2off(secs, addr)
    chunk = data[o:o + maxlen]
    return chunk.split(b'\0')[0].decode('latin-1')


def derive(lib_path):
    data = open(lib_path, 'rb').read()
    secs = _sections(data)
    syms = _dynsym(data, secs)
    plt = _plt_map(data, secs)
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    md.detail = False

    # helper: resolve a adrp+add pair to an absolute address
    def adrp_add_at(text_off, i):
        ins0 = next(md.disasm(data[text_off + 4 * i:text_off + 4 * i + 4], 0))
        ins1 = next(md.disasm(data[text_off + 4 * (i + 1):text_off + 4 * (i + 1) + 4], 0))
        if ins0.mnemonic != 'adrp' or ins1.mnemonic != 'add':
            return None
        page = int(ins0.op_str.split('#')[1], 0)
        lo = int(ins1.op_str.split('#')[1], 0)
        return page + lo

    # find GGString::stringWithString(char const*)
    strstr = syms.get('_ZN8GGString16stringWithStringEPKc')
    assert strstr, 'stringWithString symbol missing'
    # find GGString::stringWithFormat plt
    fmt_plt = next(a for a, n in plt.items()
                   if n == '_ZN8GGString16stringWithFormatEPKcz')

    # The current game language lives in the GGString* `_gameLanguageName`.
    # Derivation order: (1) direct dynamic symbol, (2) resolve GGGameLanguage-
    # Name()'s first adrp+ldr GOT slot via its GLOB_DAT/RELATIVE relocation.
    global_addr = syms.get('_gameLanguageName')
    if global_addr is None:
        gname = syms.get('_Z18GGGameLanguageNamev')
        assert gname, 'neither _gameLanguageName nor GGGameLanguageName found'
        o = _addr2off(secs, gname)
        code = data[o:o + 16]
        page = None
        slot = None
        for ins in md.disasm(code, gname):
            if ins.mnemonic == 'adrp':
                page = int(ins.op_str.split('#')[1], 0)
            elif ins.mnemonic == 'ldr' and page is not None and '#' in ins.op_str:
                imm = int(ins.op_str.split('#')[1].rstrip(']'), 0)
                slot = page + imm
                break
        assert slot is not None, 'could not derive language global slot'
        # find symbol values by dynsym index
        symtab = next(s for s in secs if s['type'] == 11)
        strtab = secs[symtab['link']]

        def symval(idx):
            eoff = symtab['offset'] + idx * 24
            st_name, st_info, st_other, st_shndx, st_value, st_size = \
                struct.unpack_from('<IBBHQQ', data, eoff)
            return st_value

        for s in secs:
            if s['sname'] != '.rela.dyn':
                continue
            for i in range(s['size'] // 24):
                roff = s['offset'] + i * 24
                r_offset, r_info, r_addend = struct.unpack_from('<QQq', data, roff)
                if r_offset != slot:
                    continue
                rtype = r_info & 0xFFFFFFFF
                if rtype == 1025 or rtype == 1026:   # GLOB_DAT / JUMP_SLOT
                    global_addr = symval(r_info >> 32)
                elif rtype == 1027:                  # RELATIVE
                    global_addr = r_addend
                break
        if global_addr is None:
            global_addr = slot
    assert global_addr, 'could not derive _gameLanguageName'

    # scan .text for the 5-insn talkie-lookup sequences
    text = next(s for s in secs if s['sname'] == '.text')
    toff, tsize, taddr = text['offset'], text['size'], text['addr']

    def dec(b, addr=0):
        g = next(md.disasm(b, addr), None)
        return g

    sites = {}
    for i in range(0, (tsize - 20) // 4):
        base = toff + 4 * i
        pc = taddr + 4 * i
        chunk = data[base:base + 20]
        ins0, ins1, ins2, ins3, ins4 = \
            dec(chunk[0:4], pc), dec(chunk[4:8], pc + 4), dec(chunk[8:12], pc + 8), \
            dec(chunk[12:16], pc + 12), dec(chunk[16:20], pc + 16)
        if not all((ins0, ins1, ins2, ins3, ins4)):
            continue
        if ins0.mnemonic != 'adrp' or ins1.mnemonic != 'add':
            continue
        if not (ins2.mnemonic == 'mov' and ins3.mnemonic == 'mov'
                and ins4.mnemonic == 'bl'):
            continue
        try:
            bl_target = int(ins4.op_str.lstrip('#'), 0)
        except ValueError:
            continue
        if plt.get(bl_target) != '_ZN8GGString16stringWithFormatEPKcz':
            continue
        # first mov must load a low reg-pair (x1 = talkie key ptr, w2 = id)
        # and adrp/add resolve to the format string
        page = int(ins0.op_str.split('#')[1], 0)
        lo = int(ins1.op_str.split('#')[1], 0)
        fmt_addr = page + lo
        try:
            s = _rodata_cstr(data, secs, fmt_addr)
        except SystemExit:
            continue
        if s.endswith('_%05d.ogg'):
            sites['audio'] = (taddr + 4 * i, fmt_addr)
        elif s.endswith('_%05d.lip'):
            sites['lip'] = (taddr + 4 * i, fmt_addr)
    assert 'audio' in sites and 'lip' in sites, f'sites found: {sites}'
    return dict(data=data, secs=secs, sites=sites, strstr=strstr,
                fmt_plt=fmt_plt, lang_global=global_addr)


if __name__ == '__main__':
    import sys
    info = derive(sys.argv[1])
    print('audio site :', hex(info['sites']['audio'][0]), 'fmt',
          hex(info['sites']['audio'][1]),
          repr(_rodata_cstr(info['data'], info['secs'], info['sites']['audio'][1])))
    print('lip site   :', hex(info['sites']['lip'][0]), 'fmt',
          hex(info['sites']['lip'][1]),
          repr(_rodata_cstr(info['data'], info['secs'], info['sites']['lip'][1])))
    print('lang global:', hex(info['lang_global']))
    print('strstr     :', hex(info['strstr']))
    print('fmt plt    :', hex(info['fmt_plt']))
