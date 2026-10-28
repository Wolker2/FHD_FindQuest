#!/usr/bin/env python3
"""Exercise compiled Open's collection/sort code on controlled galaxy fixtures.

The tested RScript subset uses the same expression and loop syntax as JS;
only variable declarations and game APIs are adapted. This is not the game VM.
Native availability is tested separately by verify_native.py.
"""
from pathlib import Path
import re
import subprocess
import sys
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes


def run(root):
    tree = parse_bp_raw(unpack_dat_bytes((root/'CFG/Rus/Lang.dat').read_bytes(),0xB1E8C689))
    for name in ('Script','FHDFindQuest','Open'):
        tree = next(e.child for e in tree.elems if e.name == name and e.child)
    code = '\n'.join(e.value for e in tree.elems if e.child is None)
    code = code.split("ShipDeleteCustomShipInfo(Player(),'FHDFindQuestMenu');",1)[0]
    code = re.sub(r'\b(unknown|int|dword|str|float)\s+(\w+)\s*=',r'let \2=',code)
    fixture = r'''
const assert=require('node:assert/strict');
let calls=[];
const planet=(id,name,owner,available=true)=>({id,name,owner,population:100,available});
const star=(name,distance,visible,planets,owner=0)=>({name,distance,visible,planets,owner});
const bellatrix=star('Беллатрикс',0,true,[planet(1,'Язаны',2),planet(2,'Хотташи',0),planet(3,'Аммарок',4),planet(4,'Эйманаполон',6),planet(5,'Асасот',6)]);
const hidden=star('Альтаир',10,false,[planet(6,'Скрытая',2)]);
const far=star('Антарес',36,true,[planet(7,'Дальняя',2)]);
const edge=star('Вега',35,true,[planet(8,'Граница',2),planet(9,'Уже принято',2,false)]);
const near=star('Альдебаран',12,true,[planet(10,'Ближняя',1)]);
const occupied=star('Арктур',5,true,[planet(11,'Захваченная',5)],1);
const pirate=star('Бетельгейзе',20,true,[planet(12,'Клан',7)],2);
let stars=[edge,far,bellatrix,hidden,occupied,near,pirate];
const ImportedFunction=(module,name)=>({Init:()=>0,Probe:p=>{calls.push(p.id);return p.available?(p.battle?5:2):-1;},Reward:()=>12345})[name];
const newarray=n=>Array(n),ArrayAdd=(a,x)=>a.push(x);
const GalaxyStars=()=>stars.length,GalaxyStar=i=>stars[i];
const Player=()=>({star:bellatrix}),ShipStar=p=>p.star;
const SectorVisible=s=>s.visible,StarToCon=s=>s,StarOwner=s=>s.owner;
const Dist2Star=(a,b)=>(a.distance-b.distance)**2,round=Math.round,sqrt=Math.sqrt;
const StarPlanets=(s,i)=>i===undefined?s.planets.length:s.planets[i];
const PlanetPopulation=p=>p.population,PlanetOwner=p=>p.owner;
const StarName=s=>s.name,PlanetName=p=>p.name,Id=p=>p.id;
const GetParFromString=(s,separator,index)=>s.split(separator)[index];
// The published RScript min(str,str) contract compares strings; ArraySort
// compares VInt and therefore cannot sort system names.
const min=(a,b)=>a<b?a:b;
const collect=()=>{COLLECTION;return {rows,planets,count};};
let actual=collect();
assert.equal(actual.rows.filter(r=>r.startsWith('Беллатрикс|')).length,3,'five planets, only three inhabited');
assert.deepEqual(actual.rows.map(r=>r.split('|')[0]),['Беллатрикс','Беллатрикс','Беллатрикс','Альдебаран','Вега']);
assert.deepEqual(actual.planets,[3,2,1,10,8],'sort must preserve mark/planet correspondence');
assert.equal(actual.count,5);
assert.deepEqual(actual.rows.map(r=>r.split('|')[5]),['0 пк','0 пк','0 пк','12 пк','35 пк'],'displayed distances use the same inclusive game distance as the radius filter');
assert(!calls.includes(4)&&!calls.includes(5),'uninhabited planets must never be probed');
assert(!calls.includes(6)&&!calls.includes(7)&&!calls.includes(11)&&!calls.includes(12),'hidden/distant/occupied systems must never be probed');
assert(calls.includes(8),'35 pc boundary included');
edge.planets[0].battle=true;actual=collect();
assert(actual.rows.find(r=>r.startsWith('Вега|')).includes('|Планетарный бой|-|'),'PB takes one row and has no invented reward');
bellatrix.visible=false;actual=collect();
assert.equal(actual.rows.filter(r=>r.startsWith('Беллатрикс|')).length,3,'current system included even without map flag');
bellatrix.planets[1].available=false;
actual=collect();assert.equal(actual.count,4,'accepted/unavailable offer disappears when reopened');
for(const s of stars)for(const p of s.planets)p.available=false;
actual=collect();assert.deepEqual(actual.planets,[0]);assert(actual.rows[0].includes('Нет доступных заданий'));
stars=[star('Aa',20,true,[planet(20,'Prefix long',2)]),star('A',20,true,[planet(21,'Prefix short',2)])];
actual=collect();assert.deepEqual(actual.planets,[21,20],'compare system names themselves, without table separators');
console.log('PASS: compiled collection code: Bellatrix 5 planets / 3 inhabited, current system, opened maps, inclusive 35 pc, alphabetical systems and matching markers, unavailable offers and reopen');
'''
    script = fixture.replace('COLLECTION',code)
    subprocess.run(['node','-e',script],check=True)


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent.parent)
