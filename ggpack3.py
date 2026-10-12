"""GGPack reader for Thimbleweed Park Android 1.0.10 (GGBJson table format) v3."""
import struct
import numpy as np

MAGIC = bytes([0x4F, 0xD0, 0xA0, 0xAC, 0x4A, 0x56, 0xB9, 0xE5,
               0x93, 0x79, 0x45, 0xA5, 0xC1, 0xCB, 0x31, 0x93])
LCG = 0x41C64E6D


def xor_decrypt(buf: bytes, magic: bytes = MAGIC) -> bytes:
    n = len(buf)
    out = bytearray(n)
    seed = n & 0xFF
    acc = 0
    for p in range(n):
        t = (acc ^ seed) & 0xFFFFFFFF
        acc = (acc + LCG) & 0xFFFFFFFF
        b = buf[p] ^ magic[p & 0x0F] ^ t
        out[p] = b & 0xFF
        seed ^= b & 0xFF
    return bytes(out)


class Reader:
    def __init__(self, d: bytes, pos=0):
        self.d = d
        self.pos = pos

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.pos)[0]
        self.pos += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.d, self.pos)[0]
        self.pos += 8
        return v

    def byte(self):
        v = self.d[self.pos]
        self.pos += 1
        return v

    def cstr(self, off):
        end = self.d.index(b"\x00", off)
        return self.d[off:end].decode("utf-8", "replace")


class Parser:
    def __init__(self, table: bytes):
        self.t = table
        self.symbols = None
        self.mode8 = None

    def value(self, r: Reader):
        t = r.byte()
        if t == 1:
            return None
        if t == 2:
            return self.dict(r)
        if t in (3, 14):
            n = r.u32()
            arr = [self.value(r) for _ in range(n)]
            close = r.byte()
            if close != t:
                raise ValueError(f"close {close} != {t} at {r.pos-1}")
            return arr
        if t == 4:
            return self.symbols[r.u32()]
        if t == 5:
            return int(self.symbols[r.u32()])
        if t == 6:
            return float(self.symbols[r.u32()])          # float string
        raise ValueError(f"unknown type {t} at {r.pos-1}")

    def dict(self, r: Reader):
        # marker already consumed
        n = r.u32()
        obj = {}
        for _ in range(n):
            idx = r.u32()
            key = self.symbols[idx] if idx < len(self.symbols) else f"sym{idx}"
            obj[key] = self.value(r)
        close = r.byte()
        if close != 2:
            raise ValueError(f"dict close {close} at {r.pos-1}")
        return obj


def parse_table(table: bytes):
    assert table[:4] == bytes([1, 2, 3, 4]), "bad sig"
    sym_off = struct.unpack_from("<I", table, 8)[0]
    assert table[sym_off] == 7, f"bad marker {table[sym_off]}"
    pos = sym_off + 1
    offs = []
    while True:
        v = struct.unpack_from("<I", table, pos)[0]
        pos += 4
        if v == 0xFFFFFFFF:
            break
        offs.append(v)
    p = Parser(table)
    r = Reader(table)
    p.symbols = [r.cstr(o) for o in offs]
    d = Reader(table, 12)
    d.byte()  # dict marker
    root = p.dict(d)
    return p, root


class GGPack:
    def __init__(self, path: str):
        self.f = open(path, "rb")
        self.entries_offset, self.entries_size = struct.unpack("<II", self.f.read(8))
        self.f.seek(self.entries_offset)
        self.table = xor_decrypt_fast(self.f.read(self.entries_size))
        p, root = parse_table(self.table)
        self.parser = p
        self.root = root
        self.entries = {}
        for e in root["files"]:
            self.entries[e["filename"]] = (int(e["offset"]), int(e["size"]))

    def read(self, name: str) -> bytes:
        off, size = self.entries[name]
        self.f.seek(off)
        return xor_decrypt_fast(self.f.read(size))


if __name__ == "__main__":
    import sys, collections
    pack = GGPack(sys.argv[1])
    print(f"OK: {len(pack.entries)} entries, {len(pack.parser.symbols)} symbols, type8={pack.parser.mode8}")
    files = pack.root["files"]
    e0 = files[0]
    print("first:", e0)
    # consistency: sorted by offset, offset+size == next offset
    by_off = sorted(files, key=lambda e: int(e["offset"]))
    bad = 0
    for a, b in zip(by_off, by_off[1:]):
        if int(a["offset"]) + int(a["size"]) != int(b["offset"]):
            bad += 1
    print("chain breaks:", bad, "of", len(by_off) - 1)
    exts = collections.Counter()
    for name in pack.entries:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "(none)"
        exts[ext] += 1
    for ext, c in exts.most_common(30):
        print(f"{c:8d}  .{ext}")


# ---- numpy-accelerated XOR stream (validated against scalar reference) ----
_NP_MAGIC = np.frombuffer(MAGIC, dtype=np.uint8)


def _terms(buf):
    a = np.frombuffer(buf, dtype=np.uint8)
    n = len(a)
    p = np.arange(n, dtype=np.uint64)
    A = ((p * np.uint64(0x41C64E6D)) & np.uint64(0xFF)).astype(np.uint8)
    M = _NP_MAGIC[np.arange(n) & 0xF]
    return a, (a ^ M ^ A), n


def xor_decrypt_fast(buf: bytes) -> bytes:
    C, D, n = _terms(buf)
    out = np.empty(n, dtype=np.uint8)
    out[0] = D[0] ^ np.uint8(n & 0xFF)
    if n > 1:
        out[1:] = D[1:] ^ D[:-1]
    return out.tobytes()


def xor_encrypt_fast(plain: bytes) -> bytes:
    P, D, n = _terms(plain)
    px = np.bitwise_xor.accumulate(P)
    S = np.empty(n, dtype=np.uint8)
    S[0] = n & 0xFF
    if n > 1:
        S[1:] = px[:-1] ^ np.uint8(n & 0xFF)
    return (D ^ S).tobytes()
