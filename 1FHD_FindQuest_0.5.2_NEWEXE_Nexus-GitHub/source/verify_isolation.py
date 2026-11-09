#!/usr/bin/env python3
"""Verify that FindQuest owns only its controls, scripts and native library."""
from pathlib import Path
import sys
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes


def descend(block, *parts):
    for part in parts:
        block = next((e.child for e in block.elems if e.name == part and e.child is not None), None)
        if block is None:
            return None
    return block


def named(block, name):
    if any(e.name == 'Name' and e.value == name for e in block.elems):
        return block
    for e in block.elems:
        if e.child is not None:
            found = named(e.child, name)
            if found is not None:
                return found
    return None


def run(root):
    main = parse_bp_raw(unpack_dat_bytes((root/'CFG/Main.dat').read_bytes(), 0xB1E8C689))
    lang = parse_bp_raw(unpack_dat_bytes((root/'CFG/Rus/Lang.dat').read_bytes(), 0xB1E8C689))
    ml = descend(main, 'ML')
    space = descend(ml, 'StarMap')
    failures = []
    if space is None or named(space, 'FHDFindQuestButton') is None:
        failures.append('The board button must be in StarMap (space)')
    galaxy = descend(ml, 'Galaxy')
    if galaxy is not None and named(galaxy, 'FHDFindQuestButton') is not None:
        failures.append('The board button must not remain in Galaxy')
    if space is not None:
        control = named(space, 'FHDFindQuestControl')
        fields = {e.name:e.value for e in control.elems if e.child is None} if control else {}
        if fields.get('PosAutoCorrection') != 'True' or fields.get('PosAutoCorrectionXCoef') != '1' or fields.get('PosAutoCorrectionYCoef') != '0':
            failures.append('Space button must follow the top right screen edge')
        if fields.get('Pos') != '990,8,-150' or fields.get('Size') != '20,20':
            failures.append('Space button must occupy the minimap top-right corner')
        for width, height in ((640, 480), (1024, 768), (1280, 720), (1920, 1080), (2560, 1440), (3440, 1440), (3840, 2160)):
            x, y = 990 + width - 1024, 8
            if width - x - 20 != 14 or y != 8 or x < 0 or x + 20 > width:
                failures.append(f'Button anchor failed at {width}x{height}')
    if descend(lang, 'Script', 'QuestMarker') is not None:
        failures.append('FindQuest must not redefine Script.QuestMarker')
    if descend(main, 'Data', 'ScriptLibs', 'FHDQuestNative') is not None:
        failures.append('FindQuest must not replace the QuestMarker native library')
    raw = (root/'SOURCE/CFG/Main.txt').read_text() + (root/'SOURCE/CFG/Lang.txt').read_text() + (root/'SOURCE/CFG/CacheData.txt').read_text()
    if any(token in raw for token in ['FHDQuestMarkV035', 'FHDQuestMarker', 'Script.QuestMarker', 'FHDQuestNative', 'OnMouseRightClick']):
        failures.append('QuestMarker resources, callbacks and scripts must be untouched')
    module = (root/'ModuleInfo.txt').read_bytes().decode('cp1251')
    if any(line.startswith('Conflict=') and 'FHD_QuestMarker_Preview' in line for line in module.splitlines()):
        failures.append('QuestMarker must not be declared as a conflicting mod')
    if failures:
        print('FAIL: ' + '\nFAIL: '.join(failures))
        return 1
    print('PASS: button is 14 px from screen right, 8 px from top at seven resolutions; QuestMarker untouched')
    return 0


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent.parent
    raise SystemExit(run(root))
