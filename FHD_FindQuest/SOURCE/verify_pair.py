#!/usr/bin/env python3
"""Check both overlay/load orders with ported QuestMarker 0.3.12.

Uses a baseline fixture derived from QuestMarker's compiled Main.dat with its
reset script removed; this is NOT a check against the complete vanilla Main.dat.
Native test reuses QuestMarker's synthetic Windows API loader, executes both real
DLL initializers and FindQuest Probe with a controlled offer generator.
Usage: verify_pair.py RANGERS_EXE QUESTMARKER_MOD_DIR
Requires Node.js, pefile and unicorn.
"""
from copy import deepcopy
from pathlib import Path
import struct
import sys
import tempfile
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes, ser_bp_block, Elem
from verify_compatibility import run as overlays
from verify_isolation import descend, named


def run(exe, quest_root, root):
    quest = parse_bp_raw(unpack_dat_bytes((quest_root/'CFG/Main.dat').read_bytes(), 0xB1E8C689))
    baseline = deepcopy(quest)
    panel = descend(baseline, 'ML', 'Galaxy', 'Panel')
    right_panel = [e.child for e in panel.elems if e.name == 'Panel'][1]
    reset = [e.child for e in right_panel.elems if e.name == 'GraphButton'][3]
    reset.elems.append(Elem('Name', value='ButDel'))
    reset.elems = [e for e in reset.elems if e.name != 'OnPressCode']
    with tempfile.TemporaryDirectory(prefix='findquest-pair-') as directory:
        path = Path(directory)/'baseline.raw'
        path.write_bytes(ser_bp_block(baseline))
        overlays(path, quest_root, root)
    print('PASS: pair overlay checks on a derived baseline fixture (not full vanilla Main.dat)')

    import pefile
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESP
    # Reuse the companion mod's actual PE loader/API fixture, not its test body.
    fixture = quest_root/'SOURCE/verify_exe_integration.py'
    source = fixture.read_text().split('\ncpu,s,exe=fresh()\n')[0]
    assert source.endswith("return cpu.reg_read(UC_X86_REG_EAX)\n"), 'Unexpected QuestMarker fixture'
    env = {'__file__': str(fixture), '__name__': 'pair_fixture'}
    exec(compile(source, str(fixture), 'exec'), env)
    for order in ('FindQuest first', 'QuestMarker first'):
        cpu, symbols, game = env['fresh']()
        pe = pefile.PE(str(root/'Native/FHDFindQuest.dll'))
        base = 0x15000000  # Both DLLs prefer 0x13000000; FindQuest must relocate.
        pe.relocate_image(base)
        image = pe.get_memory_mapped_image()
        cpu.mem_map(base, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
        cpu.mem_write(base, image)
        exports = {e.name.decode(): base+e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        call, put = env['call'], env['put']
        find_init = lambda: call(cpu, exports['FHDFindQuest_Init'])
        quest_init = lambda: call(cpu, symbols['FHDQuest_Init'])
        if order == 'FindQuest first':
            before = bytes(cpu.mem_read(0x400000, game.OPTIONAL_HEADER.SizeOfImage))
            assert find_init() == 0
            assert bytes(cpu.mem_read(0x400000, len(before))) == before
            assert quest_init() == 0
        else:
            assert quest_init() == 0
            before = bytes(cpu.mem_read(0x400000, game.OPTIONAL_HEADER.SizeOfImage))
            assert find_init() == 0
            assert bytes(cpu.mem_read(0x400000, len(before))) == before
        assert find_init() == 0 and quest_init() == 0
        sites = [0x400000+rva for rva, length in list(env['HOOKS'].values())[:4]] + [0x7a3ce4]
        saved_hooks = [bytes(cpu.mem_read(p, 16)) for p in sites]
        player, planet, star = 0x70010000, 0x70013000, 0x70014000
        put(cpu, 0x87c19c, player ^ 0xb1cd15d3)
        put(cpu, player+0x1c, 0x70015000); put(cpu, player+0x24, 0x70016000)
        cpu.mem_write(player+0x6ac, b'\x01')  # No PB selector in this controlled offer case.
        put(cpu, planet+0x18, star); put(cpu, 0x878008, 0x12345678)
        # Controlled Delphi-register generator: set message=0, kind=2, reward=12345;
        # change RNG so successful restoration is observable.
        stub = bytes.fromhex('c7 01 00 00 00 00 c6 02 02 c7 42 0c 39 30 00 00 c7 05')
        stub += struct.pack('<II', 0x878008, 0xabcdef01)
        stub += bytes.fromhex('b8 01 00 00 00 c3')
        cpu.mem_write(0x76332c, stub)
        put(cpu, env['STACK']+4, planet)
        assert call(cpu, exports['FHDFindQuest_Probe']) == 2
        assert call(cpu, exports['FHDFindQuest_Reward']) == 12345
        assert env['u32'](cpu, player+0x1c) == 0x70015000
        assert env['u32'](cpu, player+0x24) == 0x70016000
        assert env['u32'](cpu, 0x878008) == 0x12345678
        assert saved_hooks == [bytes(cpu.mem_read(p, 16)) for p in sites]
        print('PASS:', order, '- both real DLLs initialize; relocated FindQuest Probe preserves QuestMarker hooks and context')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    run(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(__file__).resolve().parent.parent)
