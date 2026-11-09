"""Regression for the real compiled reset handlers in both mod load orders.
Uses actual companion button definitions in bounded fixtures.
No Windows gameplay execution. Requires Node.js. Run: python SOURCE/verify_reset.py
"""
from pathlib import Path
from copy import deepcopy
import json,re,subprocess,sys

HERE=Path(__file__).resolve().parent
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else HERE.parent
sys.path.insert(0,str(ROOT/'SOURCE'))
from compile_srhd_dat import parse_bp_raw,unpack_dat_bytes,parse_blockpar
from verify_compatibility import merge,fields
from verify_isolation import descend,named

WORKSPACE=HERE.parent
def read(root,part):
    return parse_bp_raw(unpack_dat_bytes((root/'CFG'/part).read_bytes(),0xB1E8C689))
def code(block):return '\n'.join(e.value for e in block.elems if e.child is None)
def js(source):return re.sub(r'\b(?:unknown|int|dword|str|float)\s+(\w+)\s*=',r'let \1=',source)

base=parse_blockpar(HERE/'fixtures/vanilla_galaxy.txt')
find=read(ROOT,'Main.dat');lang=read(ROOT,'Rus/Lang.dat')
clear=code(descend(lang,'Script','FHDFindQuest','ClearMark'))
quests={
    'original QuestMarker':HERE/'fixtures/quest_reset_original.dat',
    'AMod QuestMarker':HERE/'fixtures/quest_reset_amod.dat'
}
cases=[('FindQuest standalone',[find],False)]
for title,p in quests.items():
    quest=parse_bp_raw(unpack_dat_bytes(p.read_bytes(),0xB1E8C689))
    cases.extend([(title+' -> FindQuest',[quest,find],True),('FindQuest -> '+title,[find,quest],True)])
for title,order,has_quest in cases:
    cfg=base
    for overlay in order:cfg=merge(cfg,overlay)
    galaxy=descend(cfg,'ML','Galaxy');button=named(galaxy,'ButDel')
    action=descend(button,'OnPressCode');reset=code(action)
    assert 'Script.FHDFindQuest.ClearMark' in reset,title+': FindQuest reset was overwritten'
    reference=merge(base,next(o for o in order if o is not find)) if has_quest else base
    assert fields(button)==fields(named(descend(reference,'ML','Galaxy'),'ButDel')),title+': button appearance changed'
    if has_quest:assert 'FHD_RouteClear' in reset,title+': native QuestMarker route reset was overwritten'
    fixture=r'''
const assert=require('node:assert/strict');
const active=new Map([['FHDFindQuestMark',false],['FHDQuestMarkV035',false]]);
const original=new Map(active),positions=new Map();
const pending=new Set(['FHDFindQuestMarkerState']);
let routeClears=0;
const Player=()=>1;
const ShipDeleteCustomShipInfo=(p,n)=>{assert.equal(p,1);pending.delete(n);};
const InterfaceState=(f,n,state)=>{assert.equal(f,'Galaxy');active.set(n,state===-1?(original.get(n)||false):state===1);};
const InterfacePos=(f,n,x,y,z)=>{assert.equal(f,'Galaxy');if(x===0&&y===0&&z===0)positions.delete(n);else positions.set(n,[x,y,z]);};
const ImportedFunction=(lib,n)=>{assert.equal(lib,'FHDQuestNative');assert.equal(n,'FHD_RouteClear');return ()=>routeClears++;};
const GenerateCodeStringFromBlock=p=>{assert.equal(p,'Script.FHDFindQuest.ClearMark');return CLEAR;};
const ExecuteCodeFromString=s=>eval(s);
for(let i=0;i<2;i++){
 active.set('FHDFindQuestMark',true);active.set('FHDQuestMarkV035',true);
 positions.set('FHDFindQuestMark',[200,300,0]);positions.set('FHDQuestMarkV035',[400,500,0]);
 pending.add('FHDFindQuestMarkerState');
 eval(RESET);
 assert(!active.get('FHDFindQuestMark'),'FindQuest mark remains visible after reset');
 assert(!positions.has('FHDFindQuestMark'),'old marker position remains');
 assert(!pending.has('FHDFindQuestMarkerState'),'saved target can restore the marker after reopening');
 assert.equal(active.get('FHDQuestMarkV035'),!HAS_QUEST);
 assert.equal(routeClears,HAS_QUEST?i+1:0);
 // Reopening cannot restore the target once its service state is removed.
 if(pending.has('FHDFindQuestMarkerState'))active.set('FHDFindQuestMark',true);
 assert(!active.get('FHDFindQuestMark'),'mark reappeared on reopen');
}
'''.replace('CLEAR',json.dumps(js(clear))).replace('RESET',json.dumps(js(reset))).replace('HAS_QUEST',json.dumps(has_quest))
    subprocess.run(['node','-e',fixture],check=True)
    print('PASS:',title,'- reset, repeated reset, reopen, companion route reset')
