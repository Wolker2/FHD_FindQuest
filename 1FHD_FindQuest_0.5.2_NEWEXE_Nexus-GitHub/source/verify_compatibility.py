#!/usr/bin/env python3
"""Compare both overlay orders against vanilla + standalone QuestMarker.

Usage: verify_compatibility.py VANILLA_MAIN_RAW QUESTMARKER_MOD_DIR
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import json
import re
import subprocess
import sys
from compile_srhd_dat import Block, parse_bp_raw, unpack_dat_bytes
from verify_isolation import descend, named


def merge(base, overlay):
    out = deepcopy(base)
    seen = defaultdict(int)
    for e in overlay.elems:
        if e.child is not None:
            index = seen[e.name]
            seen[e.name] += 1
            slots = [i for i, item in enumerate(out.elems) if item.name == e.name and item.child is not None]
            if index < len(slots):
                i = slots[index]
                out.elems[i].child = merge(out.elems[i].child, e.child)
            else:
                out.elems.append(deepcopy(e))
        else:
            out.elems = [item for item in out.elems if not (item.name == e.name and item.child is None)]
            out.elems.append(deepcopy(e))
    return out


def fields(block):
    return {e.name: e.value for e in block.elems if e.child is None}


def exercise_reset(button, clear_code, with_quest):
    code = '\n'.join(e.value for e in descend(button,'OnPressCode').elems if e.child is None)
    code = re.sub(r'\bunknown\s+(\w+)\s*=', r'let \1=', code)
    script = r'''
const assert=require('node:assert/strict');
const withQuest=WITH_QUEST;
let routeCleared=0;
const ImportedFunction=(lib,name)=>{assert.equal(lib,'FHDQuestNative');assert.equal(name,'FHD_RouteClear');return ()=>routeCleared++;};
const states=new Map([['FHDFindQuestMark',1],['FHDQuestMarkV035',1]]);
const positions=new Map([['FHDFindQuestMark',[100,200,0]],['FHDQuestMarkV035',[300,400,0]]]);
const InterfaceState=(form,name,state)=>{assert.equal(form,'Galaxy');assert.equal(state,-1);states.delete(name);};
const InterfacePos=(form,name,x,y,z)=>{assert.equal(form,'Galaxy');assert.deepEqual([x,y,z],[0,0,0]);positions.delete(name);};
const GenerateCodeStringFromBlock=path=>{assert.equal(path,'Script.FHDFindQuest.ClearMark');return CLEAR_CODE;};
const ExecuteCodeFromString=source=>eval(source);
for(let i=0;i<2;i++) {
eval(RESET_CODE);
assert.equal(routeCleared,withQuest?i+1:0,'QuestMarker route reset must survive');
assert(!states.has('FHDFindQuestMark')&&!positions.has('FHDFindQuestMark'),'FindQuest marker must be cleared');
assert.equal(states.has('FHDQuestMarkV035'),!withQuest,'QuestMarker own handler must be retained');
assert.equal(positions.has('FHDQuestMarkV035'),!withQuest);
}
'''.replace('WITH_QUEST',json.dumps(with_quest)).replace('CLEAR_CODE',json.dumps(clear_code)).replace('RESET_CODE',json.dumps(code))
    subprocess.run(['node','-e',script],check=True)


def run(vanilla, quest_root, gov_root):
    base = parse_bp_raw(vanilla.read_bytes())
    quest = parse_bp_raw(unpack_dat_bytes((quest_root/'CFG/Main.dat').read_bytes(), 0xB1E8C689))
    gov = parse_bp_raw(unpack_dat_bytes((gov_root/'CFG/Main.dat').read_bytes(), 0xB1E8C689))
    lang = parse_bp_raw(unpack_dat_bytes((gov_root/'CFG/Rus/Lang.dat').read_bytes(), 0xB1E8C689))
    clear = descend(lang,'Script','FHDFindQuest','ClearMark')
    clear_code = '\n'.join(e.value for e in clear.elems if e.child is None)
    standalone = named(descend(merge(base,gov),'ML','Galaxy'),'ButDel')
    assert fields(standalone) == fields(named(descend(base,'ML','Galaxy'),'ButDel'))
    exercise_reset(standalone,clear_code,False)
    reference = merge(base, quest)
    for label, overlays in [('QuestMarker -> FindQuest', [quest, gov]), ('FindQuest -> QuestMarker', [gov, quest])]:
        combined = base
        for overlay in overlays:
            combined = merge(combined, overlay)
        galaxy = descend(combined, 'ML', 'Galaxy')
        old_galaxy = descend(reference, 'ML', 'Galaxy')
        for name in ['FHDQuestMarkV035']:
            assert named(galaxy, name) == named(old_galaxy, name), label + ': QuestMarker control changed: ' + name
        reset = named(galaxy,'ButDel')
        old_reset = named(old_galaxy,'ButDel')
        assert fields(reset) == fields(old_reset), label + ': shared reset changed its appearance or native identity'
        reset_code = descend(reset,'OnPressCode')
        old_code = descend(old_reset,'OnPressCode')
        assert all(fields(reset_code).get(key) == value for key, value in fields(old_code).items()), label + ': QuestMarker reset was replaced'
        assert fields(reset_code).get('03') == "ExecuteCodeFromString(GenerateCodeStringFromBlock('Script.FHDFindQuest.ClearMark'));", label + ': FindQuest reset missing from standard button'
        exercise_reset(reset,clear_code,True)
        for form in ['Gov', 'EquipmentShop', 'GoodsShop', 'Hangar', 'Info', 'Journal', 'Planet', 'PlanetNO', 'Rating', 'RuinsTalk', 'Ship']:
            assert descend(combined, 'ML', form) == descend(reference, 'ML', form), label + ': modified QuestMarker form ' + form
        assert descend(combined, 'Data', 'ScriptLibs', 'FHDQuestNative') == descend(reference, 'Data', 'ScriptLibs', 'FHDQuestNative')
        assert named(galaxy, 'FHDFindQuestButton') is None
        assert named(galaxy, 'FHDFindQuestMark') is not None
        space = descend(combined, 'ML', 'StarMap')
        control = named(space, 'FHDFindQuestControl')
        assert control is not None
        position = fields(control)['Pos'].split(',')
        for width, height in [(1024,768),(1280,720),(1920,1080),(2560,1440),(3840,2160)]:
            x = int(position[0]) + width - 1024
            y = int(position[1])
            assert width - (x + 20) == 14 and y == 8
        print('PASS:', label, '- standard reset keeps QuestMarker handler and clears FindQuest; button occupies minimap top-right corner')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: verify_compatibility.py VANILLA_MAIN_RAW QUESTMARKER_MOD_DIR')
    run(Path(sys.argv[1]), Path(sys.argv[2]), Path(__file__).resolve().parent.parent)
