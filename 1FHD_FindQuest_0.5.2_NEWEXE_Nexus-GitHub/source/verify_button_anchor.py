#!/usr/bin/env python3
"""Check minimap-relative placement using the target EXE layout code.
This does not execute the UI renderer or prove in-game visibility.
Usage: verify_button_anchor.py RANGERS_EXE
"""
from pathlib import Path
import struct
import sys
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes
from verify_isolation import descend, named
from verify_native import mapped_pe
from verify_compatibility import merge, fields

def run(exe,root):
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_32
    from unicorn.x86_const import UC_X86_REG_EAX,UC_X86_REG_ESP
    tree=parse_bp_raw(unpack_dat_bytes((root/'CFG/Main.dat').read_bytes(),0xb1e8c689))
    star=descend(tree,'ML','StarMap')
    panel=descend(star,'Panel','Panel','FHDFindQuestControl','Panel')
    assert panel is not None,'The button must share MainPanel with the minimap, like Autopilot'
    assert panel is not None and fields(panel)['Name']=='FHDFindQuestControl'
    button=descend(panel,'GraphButton')
    assert button is not None and fields(button)['Name']=='FHDFindQuestButton'
    image=mapped_pe(exe)
    method=0x4bdea0
    assert image[method-0x400000:method-0x400000+6]==bytes.fromhex('55 8b ec 83 c4 f8')
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    vm.mem_map(0x400000,(len(image)+4095)&~4095);vm.mem_write(0x400000,bytes(image))
    vm.mem_map(0x10000000,0x10000);vm.mem_map(0x20000000,0x10000)
    parent,child,vmt,stop=0x10001000,0x10002000,0x10003000,0x1000f000
    main_obj,map_obj=0x10004000,0x10005000
    frame=0x20008000
    from unicorn.x86_const import UC_X86_REG_EBP
    # Actual StarMap layout fragments set MainPanel to (W/2,H/2), then
    # move MapPanel by (+DX/2,-DY/2). Its inactive position setter is real.
    fixture=parse_bp_raw((root/'SOURCE/fixtures/vanilla_starmap.raw').read_bytes())
    vanilla_main=named(fixture,'MainPanel');vanilla_map=named(fixture,'MapPanel')
    def put(a,v):vm.mem_write(a,struct.pack('<I',v&0xffffffff))
    put(vmt+0xc,0x4bb944)
    def init_obj(obj,definition):
        f=fields(definition);pos=f['Pos'].split(',');pos=[int(pos[0]),int(pos[1]),int(pos[2]) if len(pos)>2 and pos[2].lstrip('-').isdigit() else 0];size=list(map(int,f['Size'].split(',')))
        vm.mem_write(obj,bytes(0x200))
        put(obj,vmt)
        put(obj+0x20,pos[0]);put(obj+0x24,pos[1])
        # +0x28/+0x2c hold WIDTH/HEIGHT, not the third Pos component.
        put(obj+0x28,size[0]);put(obj+0x2c,size[1])
        vm.mem_write(obj+0x38,struct.pack('<d',pos[2]))
        vm.mem_write(obj+0x48,bytes([f.get('PosAutoCorrection')=='True']))
        vm.mem_write(obj+0x4c,struct.pack('<f',float(f.get('PosAutoCorrectionXCoef','0'))))
        vm.mem_write(obj+0x50,struct.pack('<f',float(f.get('PosAutoCorrectionYCoef','0'))))
    dx=struct.unpack_from('<I',image,0x4836c8)[0]
    dy=struct.unpack_from('<I',image,0x483584)[0]
    sizes=[(640,480),(800,600),(1024,600),(1920,1080),(1024,768),(1280,720),(1366,768),(1600,900),
           (1920,1080),(2560,1080),(2560,1440),(3440,1440),(3840,2160),(1024,768),(1920,1080)]
    for w,h in sizes:
        init_obj(parent,panel);init_obj(child,button)
        init_obj(main_obj,vanilla_main);init_obj(map_obj,vanilla_map)
        put(parent+4,child);put(vmt+0xc4,method)
        put(dx,w-1024);put(dy,h-768)
        put(0x889ee8,w);put(0x889eec,h)
        put(0x2000fff0,stop);vm.reg_write(UC_X86_REG_ESP,0x2000fff0);vm.reg_write(UC_X86_REG_EAX,parent)
        vm.emu_start(method,stop,count=10000)
        pxy=struct.unpack('<ii',vm.mem_read(parent+0x20,8))
        cxy=struct.unpack('<ii',vm.mem_read(child+0x20,8))
        # Execute the exact EXE centering and minimap-relocation code.
        put(frame-8,main_obj);put(frame-0x14,map_obj)
        vm.reg_write(UC_X86_REG_EBP,frame)
        vm.reg_write(UC_X86_REG_ESP,0x20007000)
        vm.emu_start(0x6a4e43,0x6a4e6f,count=10000)
        vm.emu_start(0x6a4f80,0x6a4fc6,count=10000)
        mxy=struct.unpack('<ii',vm.mem_read(main_obj+0x20,8))
        mapxy=struct.unpack('<ii',vm.mem_read(map_obj+0x20,8))
        screen=(mxy[0]+pxy[0]+cxy[0],mxy[1]+pxy[1]+cxy[1])
        assert screen==(w-260,162) and cxy==(0,0),(w,h,screen,pxy,cxy,mxy,mapxy)
        assert (pxy[0]-mapxy[0]+74,pxy[1]-mapxy[1]+74)==(-100,151), 'Stable position relative to the actual minimap'
        for obj,depth in [(parent,-150),(child,-1)]:
            assert struct.unpack('<ii',vm.mem_read(obj+0x28,8))==(20,20)
            assert struct.unpack('<d',vm.mem_read(obj+0x38,8))[0]==depth
        assert w-(screen[0]+20)==240
    # Preserve vanilla native layout fields and the entire existing button.
    combined=merge(fixture,star)
    assert fields(named(combined,'MainPanel'))==fields(named(fixture,'MainPanel'))
    assert named(combined,'MapPanel')==named(fixture,'MapPanel')
    native_main=named(combined,'MainPanel')
    assert named(native_main,'FHDFindQuestControl')==panel
    baseline=parse_bp_raw((root/'SOURCE/fixtures/button_visible_baseline.raw').read_bytes())
    assert button==named(baseline,'FHDFindQuestButton')
    assert fields(panel)['MoveWorld']=='False'
    print('PASS: actual EXE panel centering, minimap relocation and XY correction at 12 resolutions; button remains at the original screen position and minimap offset; original child button retained (renderer not executed)')

if __name__=='__main__':
    run(Path(sys.argv[1]).resolve(),Path(__file__).resolve().parent.parent)
