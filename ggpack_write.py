"""Write side for Thimbleweed Park GGPack (GGBJson table format).

Table layout (matches libThimbleweedPark.so quickParseGGBJsonWithSymbolDict):
  [0] u32 0x04030201 (bytes 01 02 03 04)
  [4] u32 = 1  (skipped by parser)
  [8] u32 offset of symbol region
  [12..] root dictionary stream: 02, u32 nPairs, (u32 symIdx, value)*, 02
  [symRegionOffset] byte 0x07, then u32 string offsets until 0xFFFFFFFF
Strings are null-terminated, stored inline in a blob; each unique string gets
one offsets entry. Value types: 1 null, 2 dict, 3 array, 4 string(symIdx),
5 int(symIdx numeric string), 6 double(symIdx numeric string).
"""
import struct
from ggpack3 import xor_decrypt, MAGIC, xor_encrypt_fast


def xor_encrypt(plain: bytes, magic: bytes = MAGIC) -> bytes:
    """Produce bytes that xor_decrypt() will turn back into `plain`.

    The stream feedback accumulates the PLAINTEXT bytes (that is what the
    engine's decryptor has available as it goes), not the cipher output.
    """
    n = len(plain)
    out = bytearray(n)
    seed = n & 0xFF
    acc = 0
    for p in range(n):
        t = (acc ^ seed) & 0xFFFFFFFF
        acc = (acc + 0x41C64E6D) & 0xFFFFFFFF
        out[p] = (plain[p] ^ magic[p & 0x0F] ^ t) & 0xFF
        seed ^= plain[p]
    return bytes(out)


class TableWriter:
    def __init__(self):
        self.strings = []
        self.index = {}
        self.buf = bytearray()

    def sym(self, s):
        if isinstance(s, int) and not isinstance(s, bool):
            s = str(s)
        elif isinstance(s, float):
            s = repr(s)
        if not isinstance(s, str):
            raise TypeError(f"bad symbol {s!r}")
        if s in self.index:
            return self.index[s]
        idx = len(self.strings)
        self.index[s] = idx
        self.strings.append(s)
        return idx

    def write_value(self, v):
        if v is None:
            self.buf.append(1)
        elif isinstance(v, dict):
            self.buf.append(2)
            self.buf += struct.pack("<I", len(v))
            for k, val in v.items():
                self.buf += struct.pack("<I", self.sym(k))
                self.write_value(val)
            self.buf.append(2)
        elif isinstance(v, list):
            self.buf.append(3)
            self.buf += struct.pack("<I", len(v))
            for item in v:
                self.write_value(item)
            self.buf.append(3)
        elif isinstance(v, str):
            self.buf.append(4)
            self.buf += struct.pack("<I", self.sym(v))
        elif isinstance(v, int):
            self.buf.append(5)
            self.buf += struct.pack("<I", self.sym(v))
        elif isinstance(v, float):
            self.buf.append(6)
            self.buf += struct.pack("<I", self.sym(v))
        else:
            raise TypeError(f"cannot serialize {type(v)}")

    def serialize(self, root) -> bytes:
        self.buf = bytearray()
        self.buf.append(2)
        self.buf += struct.pack("<I", len(root))
        for k, v in root.items():
            self.buf += struct.pack("<I", self.sym(k))
            self.write_value(v)
        self.buf.append(2)
        string_blob = bytearray()
        base = 12 + len(self.buf)
        positions = []
        for s in self.strings:
            while len(string_blob) % 4:
                string_blob.append(0)
            positions.append(base + len(string_blob))
            string_blob.extend(s.encode("utf-8") + b"\x00")
        sym_region_off = base + len(string_blob)
        off = bytearray([0x07])
        for p in positions:
            off += struct.pack("<I", p)
        off += struct.pack("<I", 0xFFFFFFFF)
        table = bytearray()
        table += struct.pack("<I", 0x04030201)
        table += struct.pack("<I", 1)
        table += struct.pack("<I", sym_region_off)
        table += self.buf
        table += string_blob
        table += off
        return bytes(table)


class GGPackWriter:
    """Append new entries to an existing pack; existing entry data is untouched."""

    def __init__(self, path: str):
        self.path = path
        self.f = open(path, "rb")
        self.entries_offset, self.entries_size = struct.unpack("<II", self.f.read(8))
        self.table = xor_decrypt(self._read_at(self.entries_offset, self.entries_size))
        from ggpack3 import Parser, Reader
        p = Parser(self.table)
        sym_off = struct.unpack_from("<I", self.table, 8)[0]
        pos = sym_off + 1
        offs = []
        while True:
            v = struct.unpack_from("<I", self.table, pos)[0]
            pos += 4
            if v == 0xFFFFFFFF:
                break
            offs.append(v)
        rd = Reader(self.table)
        p.symbols = [rd.cstr(o) for o in offs]
        r = Reader(self.table, 12)
        r.byte()
        self.root = p.dict(r)
        self.data_end = self.entries_offset  # data occupies [8, entries_offset)
        self.pending = []

    def _read_at(self, off, size):
        self.f.seek(off)
        return self.f.read(size)

    def add_entry(self, filename: str, data: bytes):
        self.pending.append((filename, data))

    def write(self, out_path: str):
        files = list(self.root["files"])
        for e in files:
            assert int(e["offset"]) + int(e["size"]) <= self.entries_offset, e
        # The new table shifts the data start, which changes the offset numbers,
        # which can change the table size. Iterate to a fixed point.
        table_size = len(self.table)
        for _ in range(8):
            data_start = self.entries_offset + table_size
            newfiles = list(files)
            cursor = data_start
            for (name, data) in self.pending:
                newfiles.append({"filename": name, "offset": cursor, "size": len(data)})
                cursor += len(data)
            w = TableWriter()
            table = w.serialize({"files": newfiles})
            if len(table) == table_size:
                break
            table_size = len(table)
        else:
            raise RuntimeError("table size did not converge")
        with open(out_path, "wb") as out:
            self.f.seek(0)
            remaining = self.entries_offset
            while remaining:
                chunk = self.f.read(min(1 << 22, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
            out.write(xor_encrypt_fast(table))
            for (name, data) in self.pending:
                out.write(xor_encrypt_fast(data))
            out.seek(0)
            out.write(struct.pack("<II", self.entries_offset, len(table)))
        return out_path
