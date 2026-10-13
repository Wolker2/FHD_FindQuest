#!/usr/bin/env python3
"""Verify packaged PE exports and guarded function bytes against target EXE.
Usage: python SOURCE/verify_release.py /path/to/Rangers.exe
No Windows execution is performed.
"""
from pathlib import Path
import hashlib
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
EXE_SHA = '83300344af802bc51e64389c58f047e5afdf195c133048098be3881fae29ed98'

class PE:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        assert self.data[:2] == b'MZ'
        nt = self.u32(0x3c)
        assert self.data[nt:nt+4] == b'PE\0\0'
        self.machine, count = struct.unpack_from('<HH', self.data, nt+4)
        optional_size = struct.unpack_from('<H', self.data, nt+20)[0]
        self.opt = nt+24
        assert struct.unpack_from('<H', self.data, self.opt)[0] == 0x10b
        self.sections = []
        for i in range(count):
            p = self.opt+optional_size+40*i
            vsize, rva, rawsize, raw = struct.unpack_from('<IIII', self.data, p+8)
            self.sections.append((rva, max(vsize, rawsize), raw, rawsize, self.u32(p+36)))
    def u32(self, offset):
        return struct.unpack_from('<I', self.data, offset)[0]
    def offset(self, rva):
        for base, size, raw, rawsize, flags in self.sections:
            if base <= rva < base+size:
                assert rva-base < rawsize, 'Expected file-backed RVA'
                return raw+rva-base
        raise AssertionError(f'RVA not in sections: {rva:x}')
    def at(self, rva, count):
        off = self.offset(rva)
        return self.data[off:off+count]
    def directory(self, index):
        return struct.unpack_from('<II', self.data, self.opt+96+8*index)
    def exports(self):
        rva, size = self.directory(0)
        assert rva and size
        p = self.offset(rva)
        n = self.u32(p+24)
        names = self.offset(self.u32(p+32))
        result = set()
        for i in range(n):
            off = self.offset(self.u32(names+4*i))
            result.add(self.data[off:self.data.index(b'\0', off)].decode('ascii'))
        return result

def verify(exe_path):
    exe = PE(exe_path)
    assert hashlib.sha256(exe.data).hexdigest() == EXE_SHA, 'Different Rangers.exe'
    dll = PE(ROOT/'Native/FHDFindQuest.dll')
    assert dll.machine == 0x14c, 'DLL must be i386'
    entry = dll.u32(dll.opt+16)
    assert any(rva <= entry < rva+size and flags & 0x20000000
               for rva, size, raw, rawsize, flags in dll.sections), 'Invalid entry point'
    imports = dll.directory(1)
    if imports != (0, 0):
        # GNU ld can emit an empty import descriptor table.
        assert not any(dll.at(imports[0], imports[1])), 'Unexpected static imports'
    assert all(dll.directory(5)), 'Missing base relocations'
    definition = (ROOT/'SOURCE/Native/find_quest.def').read_text()
    expected = set(re.findall(r'^\s*(FHD\w+)=', definition, re.M))
    assert dll.exports() == expected, 'Export mismatch'
    guards = [(0x36332c, '55 8b ec 51 b9 6b 00 00 00'),
              (0x3980dc, '55 8b ec 83 c4 dc 53'), (0x5d18, '8b 10 85 d2')]
    for address, literal in guards:
        data = bytes.fromhex(literal)
        assert exe.at(address, len(data)) == data, f'Guard mismatch at {address:#x}'
    assert exe.u32(exe.opt+56) == 0x4d1000
    assert exe.u32(exe.opt-16) == 0x68eccc46
    print(f'PASS: i386 PE, entry, relocations, {len(expected)} exports, no static imports')
    print('PASS: exact EXE SHA-256, PE fingerprint and three native function guards')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    verify(sys.argv[1])
