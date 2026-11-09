#!/usr/bin/env python3
"""Reject RScript variable names parsed as numeric literals, not identifiers.

Optional Rangers.exe argument checks the actual x86 hex/binary recognizer at
0x45ffa0 in build 2.1.2500. This is not a full RScript compilation test.
"""
from pathlib import Path
import re
import struct
import sys
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes


def declarations(root):
    def walk(block, path):
        for entry in block.elems:
            name = path + '.' + entry.name
            if entry.child is not None:
                yield from walk(entry.child, name)
            else:
                # Ignore quoted text and comments before inspecting declarations.
                code = re.sub(r"'(?:''|[^'])*'|//[^\n]*|/\*.*?\*/", ' ', entry.value,
                              flags=re.S)
                for match in re.finditer(r'\b(?:int|dword|float|str|unknown)\s+(\w+)\s*=', code):
                    yield name, match.group(1)
    for file in ('CFG/Main.dat', 'CFG/Rus/Lang.dat'):
        tree = parse_bp_raw(unpack_dat_bytes((root/file).read_bytes(), 0xB1E8C689))
        yield from walk(tree, file)


def numeric_name(name):
    return bool(re.fullmatch(r'[0-9a-fA-F]+[hH]|[01]+[bB]', name))


def native_recognizer(exe):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ESP
    from verify_native import mapped_pe
    image = mapped_pe(exe)
    assert image[0x45ffa0-0x400000:0x45ffa0-0x400000+6] == bytes.fromhex('53565783c4f8')
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (len(image)+4095)&~4095)
    vm.mem_write(0x400000, bytes(image))
    vm.mem_map(0x10000000, 0x10000)
    vm.mem_map(0x20000000, 0x10000)
    def recognize(name):
        token, cursor, output, string = 0x10000000, 0x10000100, 0x10000200, 0x10000400
        vm.mem_write(token, bytes(32))
        vm.mem_write(token+12, b'\x26')
        vm.mem_write(token+24, struct.pack('<I', string))
        vm.mem_write(cursor, struct.pack('<I', token))
        encoded = name.encode('utf-16le')
        vm.mem_write(string-4, struct.pack('<I', len(encoded)))
        vm.mem_write(string, encoded+b'\0\0')
        stack = 0x2000FFF0
        vm.mem_write(stack, struct.pack('<I', 0x1000F000))
        vm.reg_write(UC_X86_REG_ESP, stack)
        vm.reg_write(UC_X86_REG_EAX, cursor)
        vm.reg_write(UC_X86_REG_EDX, output)
        vm.emu_start(0x45ffa0, 0x1000F000, count=10000)
        accepted = bool(vm.reg_read(UC_X86_REG_EAX)&255)
        value = struct.unpack('<I', vm.mem_read(output, 4))[0]
        return accepted, value
    return recognize


def run(root, exe=None):
    names = list(declarations(root))
    if exe is not None:
        recognize = native_recognizer(exe)
        assert recognize('fh') == (True, 15), 'reproduce the old numeric-name collision'
        assert recognize('frameHeight')[0] is False
        assert recognize('10b') == (True, 2)
        for _, name in names:
            assert recognize(name)[0] == numeric_name(name), name
        print('PASS: real Rangers.exe numeric recognizer parses fh as 15; replacement is an identifier')
    invalid = [(path, name) for path, name in names if numeric_name(name)]
    assert not invalid, 'RScript interprets these variable names as numeric literals: '+repr(invalid)
    print(f'PASS: {len(names)} compiled RScript declarations have no hex/binary literal collisions')


if __name__ == '__main__':
    run(Path(__file__).resolve().parent.parent,
        Path(sys.argv[1]) if len(sys.argv)>1 else None)
