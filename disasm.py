"""Disassemble regions of an AArch64 ELF with symbol annotation."""
import sys, struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN


def load_elf(path):
    data = open(path, 'rb').read()
    # parse section headers
    e_shoff, = struct.unpack_from('<Q', data, 0x28)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from('<HHH', data, 0x3A)
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        name, stype, flags, addr, offset, size, link, info, align, entsize = struct.unpack_from('<IIQQQQIIQQ', data, off)
        sections.append(dict(name=name, type=stype, addr=addr, offset=offset, size=size, link=link, entsize=entsize))
    shstr = sections[e_shstrndx]
    for s in sections:
        n = data.index(b'\0', shstr['offset'] + s['name'])
        s['sname'] = data[shstr['offset'] + s['name']:n].decode()
    syms = {}
    for s in sections:
        if s['type'] in (2, 11):  # SYMTAB, DYNSYM
            strtab = sections[s['link']]
            n = s['size'] // 24
            for i in range(n):
                off = s['offset'] + i * 24
                st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from('<IBBHQQ', data, off)
                if st_name:
                    e = data.index(b'\0', strtab['offset'] + st_name)
                    nm = data[strtab['offset'] + st_name:e].decode()
                    syms.setdefault(st_value, nm)
    # resolve PLT: map plt stub addr -> symbol name via .rela.plt (1:1, stub i at plt+32+16*i)
    symtab = next((s for s in sections if s['type'] == 11), None)
    plt = next((s for s in sections if s['sname'] == '.plt'), None)
    if symtab and plt:
        strtab = sections[symtab['link']]
        for s in sections:
            if s['sname'] == '.rela.plt':
                for i in range(s['size'] // 24):
                    off = s['offset'] + i * 24
                    r_offset, r_info, r_addend = struct.unpack_from('<QQq', data, off)
                    sym_idx = r_info >> 32
                    if sym_idx:
                        eoff = symtab['offset'] + sym_idx * 24
                        st_name, = struct.unpack_from('<I', data, eoff)
                        e = data.index(b'\0', strtab['offset'] + st_name)
                        nm = data[strtab['offset'] + st_name:e].decode()
                        stub = plt['addr'] + 32 + 16 * i
                        syms.setdefault(stub, f"plt:{nm}")
    return data, sections, syms


def disasm(data, sections, syms, start, end, show_bytes=True):
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    md.detail = False
    # find section containing start
    for s in sections:
        if s['type'] != 8 and s['addr'] <= start < s['addr'] + s['size'] and s['sname'] not in ('.bss',):
            off = s['offset'] + (start - s['addr'])
            code = data[off:off + (end - start)]
            break
    else:
        raise SystemExit('addr not in a section')
    out = []
    for ins in md.disasm(code, start):
        line = f"{ins.address:08x}: {ins.mnemonic}\t{ins.op_str}"
        if show_bytes:
            line = f"{ins.address:08x}: {ins.bytes.hex():<12} {ins.mnemonic}\t{ins.op_str}"
        # annotate
        try:
            if ins.mnemonic in ('bl', 'b') or ins.mnemonic.startswith('b.') or ins.mnemonic == 'cbz' or ins.mnemonic == 'cbnz' or ins.mnemonic.startswith('tbz') or ins.mnemonic.startswith('tbnz'):
                for tok in ins.op_str.replace(',', ' ').split():
                    if tok.startswith('#'):
                        v = int(tok[1:], 0)
                    elif tok.lstrip('-').isdigit() or (tok.startswith('0x')):
                        v = int(tok, 0)
                    else:
                        continue
                    if v in syms:
                        line += f"   ; {syms[v]}"
        except Exception:
            pass
        if ins.mnemonic == 'adrp':
            # page address; try to resolve next add
            pass
        out.append(line)
    return "\n".join(out)


if __name__ == '__main__':
    path = sys.argv[1]
    start = int(sys.argv[2], 0)
    end = int(sys.argv[3], 0)
    data, sections, syms = load_elf(path)
    print(disasm(data, sections, syms, start, end))
