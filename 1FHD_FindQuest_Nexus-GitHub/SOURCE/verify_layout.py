#!/usr/bin/env python3
"""Run compiled layout/pagination against controlled UI APIs (not game VM)."""
from pathlib import Path
import json
import re
import subprocess
import sys
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes
from verify_isolation import descend, named


def fields(block):
    return {e.name:e.value for e in block.elems if e.child is None}


def code(block):
    return re.sub(r'\b(unknown|int|dword|str|float)\s+(\w+)\s*=',r'let \2=',
                  '\n'.join(e.value for e in block.elems if e.child is None))


def run(root):
    main=parse_bp_raw(unpack_dat_bytes((root/'CFG/Main.dat').read_bytes(),0xB1E8C689))
    lang=parse_bp_raw(unpack_dat_bytes((root/'CFG/Rus/Lang.dat').read_bytes(),0xB1E8C689))
    form=descend(main,'ML','FHDFindQuestList')
    assert named(form,'ClearMark') is None, 'standalone reset button must be removed'
    controls={}
    def walk(block,parent=None):
        f=fields(block)
        name=f.get('Name')
        if name:
            controls[name]={'parent':parent, 'pos':[int(x) for x in f.get('Pos','0,0,0').split(',')],
                            'size':[int(x) for x in f.get('Size','0,0').split(',')],
                            'active':f.get('Active')!='False', 'type':'', 'text':f.get('Text','')}
            parent=name
        for e in block.elems:
            if e.child:
                walk(e.child,parent)
                child_name=fields(e.child).get('Name')
                if child_name: controls[child_name]['type']=e.name
    walk(form)
    layout=code(descend(form,'CodeBeforeRun'))
    fill=code(descend(lang,'Script','FHDFindQuest','Fill'))
    # Test the actual compiled pagination/navigation portion with a large list.
    open_code=code(descend(lang,'Script','FHDFindQuest','Open'))
    paging=open_code.split("ShipDeleteCustomShipInfo(Player(),'FHDFindQuestMenu');",1)[1]
    paging=re.sub(r'let pages=\(count\+capacity-1\)/capacity;',
                  'let pages=Math.trunc((count+capacity-1)/capacity);',paging)
    fixture=r'''
const assert=require('node:assert/strict');
const template=CONTROLS;
let controls,resolution=[1920,1080],resizeCalls=[],storage=new Map(),choices=[],opened=[],marked=[];
const min=Math.min,max=Math.max,sqrt=Math.sqrt;
const round=x=>{const n=Math.floor(x),f=x-n;return f===0.5?(n%2===0?n:n+1):Math.round(x);};
const GetGameOptions=key=>resolution[key==='ResolutionX'?0:1];
const find=n=>{assert(controls[n],'compiled code names a missing control: '+n);return controls[n];};
// Script APIs read integer arguments through VInt; image buttons retain native pixels.
const CustomInterfacePos=(n,x,y)=>{find(n).pos=[Math.trunc(x),Math.trunc(y),find(n).pos[2]];};
const CustomInterfaceSize=(n,w,h)=>{find(n).size=[Math.trunc(w),Math.trunc(h)];};
const CustomInterfaceState=(n,s)=>{if(s===2)find(n).disabled=true;else find(n).active=!!s;};
const CustomInterfaceText=(n,t)=>find(n).text=t;
const UICheckElement=(form,n,kind,path,mode)=>{
 assert.equal(form,'');assert.equal(find(n).type,'GraphBuf');assert.equal(kind,'Rescale');
 assert.equal(path,'GI,Bm.FHDFindQuest.HUD2');assert.equal(mode,'GI');resizeCalls.push(n);
};
const Player=()=>1,ShipFindCustomShipInfoByType=()=>0;
const ShipCustomShipInfoData=(p,m,k,v)=>v===undefined?storage.get('data'+k):storage.set('data'+k,v);
const ShipCustomShipInfoTextData=(p,m,k,v)=>v===undefined?storage.get('text'+k):storage.set('text'+k,v);
const ShipAddCustomShipInfo=()=>0,ShipDeleteCustomShipInfo=()=>{};
const GetParFromString=(s,sep,i)=>s.split(sep)[i];
const GenerateCodeStringFromBlock=p=>p;
const ExecuteCodeFromString=(p,k,star)=>{
 if(p==='Script.FHDFindQuest.Fill') {FILL;}
 else {assert.equal(p,'Script.FHDFindQuest.PlaceMark');assert.equal(k,'star');marked.push(star);}
};
const IdToPlanet=id=>id,PlanetToStar=id=>id;
const CloseCustomForm=()=>{throw Error('layout unexpectedly closed form');};
const capacityAt=()=>{const s=min(1,(resolution[0]-16)/1003,(resolution[1]-16)/711),pitch=max(27,round(32*s));return min(12,max(1,round((round(620*s)-106-round(114*s))/pitch-0.4999)));};
const init=()=>{controls=JSON.parse(JSON.stringify(template));resizeCalls=[];LAYOUT;};
const absolute=n=>{let c=find(n),x=c.pos[0],y=c.pos[1];while(c.parent){c=find(c.parent);x+=c.pos[0];y+=c.pos[1];}return [x,y];};
const active=n=>{let c=find(n);if(!c.active)return false;while(c.parent){c=find(c.parent);if(!c.active)return false;}return true;};
const inside=(n,parent)=>{
 const [x,y]=absolute(n),[px,py]=absolute(parent),[w,h]=find(n).size,[pw,ph]=find(parent).size;
 assert(x>=px&&y>=py&&x+w<=px+pw&&y+h<=py+ph,`${resolution}: ${n} outside ${parent}`);
};
const OpenCustomForm=()=>{
 init();
 const visible=storage.get('data1');
 for(let i=0;i<12;i++) assert.equal(find('Row'+i).active,i<visible);
 for(const n of Object.keys(controls)) if(active(n)&&!['MainPanel','BGBuf','BoardWindow'].includes(n)) inside(n,'BoardWindow');
 for(let i=0;i<visible;i++){
   assert.equal(find('Row'+i+'Distance').text,storage.get('text1').split('\n')[i].split('|')[5]);
   inside('Choose'+i,'Row'+i);
   const bottom=absolute('Row'+i)[1]+find('Row'+i).size[1];
   assert(bottom<=absolute('Hint')[1]-8,'rows overlap hint/footer');
 }
 assert(!active('HUD2Compact')||resizeCalls.length===1,'compact frame uses engine GI rescale');
 assert(active('HUD2')!==active('HUD2Compact'),'exactly one frame visible');
 assert.deepEqual(find('Cancel').size,[48,21],'close hitbox matches native sprite');
 opened.push({page:storage.get('data2'),pages:storage.get('data3'),visible,rows:storage.get('text1').split('\n')});
 return choices.shift()??1;
};
const testPaging=()=>{let count=31,rows=Array.from({length:count},(_,i)=>`Система ${i}|Планета ${i}|Квест|100 кр.|Отметить|${i} пк`),planets=Array.from({length:count},(_,i)=>i+1);PAGING;};
for(const pair of [[640,480],[800,600],[1024,600],[1024,768],[1280,720],[1366,768],[1920,1080],[2560,1440],[3440,1440],[3840,2160]]){
 resolution=pair;opened=[];marked=[];choices=Array(40).fill(3);testPaging();
 const capacity=capacityAt();
 assert.equal(opened.length,Math.ceil(31/capacity));
 assert.deepEqual(opened.flatMap(p=>p.rows),Array.from({length:31},(_,i)=>`Система ${i}|Планета ${i}|Квест|100 кр.|Отметить|${i} пк`),'pagination must not drop/duplicate rows');
 opened=[];choices=[3,5];testPaging();assert.deepEqual(marked,[capacity+2],'selection after next page uses responsive capacity');
 opened=[];marked=[];choices=[3,2,4];testPaging();assert.deepEqual(marked,[1],'previous page restores correct marker index');
 if(pair[0]===1920){assert.deepEqual(absolute('Window'),[480,230]);assert.deepEqual(absolute('Cancel'),[1360,806]);}
}
console.log('PASS: compiled responsive layout and pagination, 640x480 to 3840x2160; current API names, bounded visible controls, native hitboxes, close position and distances');
'''
    fixture=fixture.replace('CONTROLS',json.dumps(controls,ensure_ascii=False)).replace('FILL',fill).replace('LAYOUT',layout).replace('PAGING',paging)
    subprocess.run(['node','-e',fixture],check=True)


if __name__=='__main__':
    run(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent.parent)
