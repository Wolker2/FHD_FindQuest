#!/usr/bin/env python3
"""Run the bridge's real x86 code against a section-mapped Rangers.exe.

The x86 harness substitutes only the Windows PEB accessor. Init checks the
actual EXE bytes. Probe uses controlled Delphi-register stubs, not a running
game; this checks addressing, ABI, outputs and restoration, not quest content.
Requires gcc with -m32 support and Python unicorn.
Usage: verify_native.py RANGERS_EXE [MOD_DIR]
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def mapped_pe(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    optional = pe + 24
    image = bytearray(struct.unpack_from('<I', data, optional + 56)[0])
    headers = struct.unpack_from('<I', data, optional + 60)[0]
    image[:headers] = data[:headers]
    sections = optional + struct.unpack_from('<H', data, pe + 20)[0]
    for i in range(struct.unpack_from('<H', data, pe + 6)[0]):
        _, rva, size, raw = struct.unpack_from('<IIII', data, sections + i * 40 + 8)
        if size:
            image[rva:rva + size] = data[raw:raw + size]
    return image


def execute_x86(binary):
    try:
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_INTR
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ESP
    except ImportError:
        raise SystemExit('Install Python unicorn to emulate the Win32 x86 harness')
    data = binary.read_bytes()
    entry, phoff = struct.unpack_from('<II', data, 24)
    phsize, phcount = struct.unpack_from('<HH', data, 42)
    segments = []
    for i in range(phcount):
        kind, offset, address, _, size, memory, _, _ = struct.unpack_from('<8I', data, phoff + i*phsize)
        if kind == 1:
            segments.append((offset, address, size, memory))
    low = min(s[1] for s in segments) & ~4095
    high = (max(s[1]+s[3] for s in segments)+4095) & ~4095
    emulator = Uc(UC_ARCH_X86, UC_MODE_32)
    emulator.mem_map(0,4096)  # Win32 FS:0 exception-chain head for the harness.
    emulator.mem_map(low, high-low)
    for offset, address, size, _ in segments:
        emulator.mem_write(address, data[offset:offset+size])
    emulator.mem_map(0x20000000, 0x10000)
    emulator.reg_write(UC_X86_REG_ESP, 0x2000fff0)
    status = []

    def syscall(uc, number, _):
        assert number == 0x80 and uc.reg_read(UC_X86_REG_EAX) == 1, 'Unexpected x86 interrupt'
        status.append(uc.reg_read(UC_X86_REG_EBX))
        uc.emu_stop()

    emulator.hook_add(UC_HOOK_INTR, syscall)
    emulator.emu_start(entry, high, timeout=10_000_000, count=5_000_000)
    assert status, 'x86 harness did not exit'
    return status[0]


def verify_dll_init(exe, dll):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP
    game_image = mapped_pe(exe)
    original = mapped_pe(dll)
    pe = struct.unpack_from('<I', original, 0x3c)[0]
    optional = pe + 24
    preferred = struct.unpack_from('<I', original, optional+28)[0]
    exports = struct.unpack_from('<I', original, optional+96)[0]
    count = struct.unpack_from('<I', original, exports+24)[0]
    functions, names, ordinals = struct.unpack_from('<III', original, exports+28)
    exported = {}
    for i in range(count):
        name = struct.unpack_from('<I', original, names+i*4)[0]
        end = original.index(0, name)
        ordinal = struct.unpack_from('<H', original, ordinals+i*2)[0]
        exported[bytes(original[name:end])] = struct.unpack_from('<I', original, functions+ordinal*4)[0]
    init_rva = exported.get(b'FHDFindQuest_Init')
    assert init_rva is not None, 'DLL Init export missing'
    for base in (preferred, preferred+0x02000000):
        image = bytearray(original)
        if base != preferred:
            reloc, length = struct.unpack_from('<II', image, optional+96+5*8)
            assert reloc and length, 'DLL must support relocation beside QuestMarker'
            cursor = reloc
            while cursor < reloc+length:
                page, size = struct.unpack_from('<II', image, cursor)
                assert size >= 8
                for offset in range(cursor+8, cursor+size, 2):
                    item = struct.unpack_from('<H', image, offset)[0]
                    if item >> 12 == 3:
                        address = page+(item & 4095)
                        value = struct.unpack_from('<I', image, address)[0]
                        struct.pack_into('<I', image, address, (value+base-preferred)&0xffffffff)
                    else:
                        assert item >> 12 == 0, 'Unexpected PE32 relocation'
                cursor += size
        for variant, expected in [('vanilla', 0), ('questmarker', 0), ('bad-generator', 4), ('bad-battle-selector', 4)]:
            emulator = Uc(UC_ARCH_X86, UC_MODE_32)
            for address, size in [(0,4096),(0x10000,4096),(0x400000,len(game_image)),
                                  (base,len(image)),(0x20000000,0x10000),(0x30000000,4096)]:
                emulator.mem_map(address, (size+4095)&~4095)
            emulator.mem_write(0x400000, bytes(game_image))
            emulator.mem_write(base, bytes(image))
            emulator.mem_write(0x30, struct.pack('<I',0x10000))
            emulator.mem_write(0x10008, struct.pack('<I',0x400000))
            if variant == 'questmarker':
                for site in (0x1276ec,0x129e34,0x12b518,0x12b810):
                    emulator.mem_write(0x400000+site, b'\xe9\0\0\0\0')
                emulator.mem_write(0x7a3ce4, struct.pack('<I',0x12001000))
            elif variant == 'bad-generator':
                emulator.mem_write(0x76332c, b'\x90')
            elif variant == 'bad-battle-selector':
                emulator.mem_write(0x7980dc, b'\x90')
            stack = 0x2000ffec
            emulator.mem_write(stack, struct.pack('<I',0x30000000))
            emulator.reg_write(UC_X86_REG_ESP,stack)
            emulator.emu_start(base+init_rva,0x30000000,timeout=1_000_000,count=100_000)
            result = emulator.reg_read(UC_X86_REG_EAX)
            assert result == expected, f'Compiled DLL {variant} at {base:#x}: Init={result}, expected {expected}'
        # Exercise the actual DLL -> actual TPlanet.RelationToRanger chain.
        # Only the offer generator is restricted to this relation check and
        # a deterministic offer. The Delphi cast, list lookup, relation getter,
        # player getter and string cleanup all run from the real EXE.
        emulator.mem_write(0x400000, bytes(game_image))
        emulator.mem_write(base, bytes(image))

        def invoke(rva, argument=None):
            emulator.mem_write(stack, struct.pack('<I',0x30000000))
            if argument is not None:
                emulator.mem_write(stack+4, struct.pack('<I',argument))
            emulator.reg_write(UC_X86_REG_ESP,stack)
            try:
                emulator.emu_start(base+rva,0x30000000,timeout=1_000_000,count=100_000)
            except Exception:
                from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EBP
                print('Emulator fault:',hex(emulator.reg_read(UC_X86_REG_EIP)), 'eax',hex(emulator.reg_read(UC_X86_REG_EAX)), 'edx',hex(emulator.reg_read(UC_X86_REG_EDX)), 'ecx',hex(emulator.reg_read(UC_X86_REG_ECX)), 'esp',hex(emulator.reg_read(UC_X86_REG_ESP)), 'edi',hex(emulator.reg_read(UC_X86_REG_EDI)), 'ebp',hex(emulator.reg_read(UC_X86_REG_EBP)))
                raise
            return emulator.reg_read(UC_X86_REG_EAX)

        assert invoke(init_rva) == 0
        emulator.mem_map(0x10000000,0x10000)

        def put(address, value):
            emulator.mem_write(address,struct.pack('<I',value))

        player, planet, star = 0x10001000,0x10003000,0x10004000
        galaxy_slot, galaxy, rangers, ranger_items = 0x10005000,0x10005100,0x10005200,0x10005300
        relations, relation_items = 0x10006000,0x10006200
        put(player,struct.unpack_from('<I',game_image,0x34fe5c)[0])  # TRanger VMT
        emulator.mem_write(player+0x10,b'\x01')                  # registered ranger kind
        put(player+0x1c,0x10007000)
        put(0x882b08,0x10009300);put(0x10009300,0x10009404)
        put(0x10009400,2)  # Delphi dynamic-array length before data
        put(0x10009404+0x4c,7);put(0x10009404+80+0x4c,11)
        put(0x8822d8,0x10009310);put(0x10009310,0xffffffff)
        battle_selector=0x10009600
        battle_stub=bytes.fromhex('c7 05')+struct.pack('<I',0x10009404+0x4c)+struct.pack('<I',99)
        battle_stub+=bytes.fromhex('b8 ff ff ff ff c3')
        emulator.mem_write(battle_selector,battle_stub)
        emulator.mem_write(0x7980dc,b'\xe9'+struct.pack('<i',battle_selector-0x7980e1))
        put(planet+0x18,star)
        put(planet+0x10c,relations)
        put(0x87c19c,player ^ 0xb1cd15d3)                       # native GetPlayer
        put(0x88263c,galaxy_slot);put(galaxy_slot,galaxy)
        put(galaxy+0x3c,rangers);put(rangers+4,ranger_items);put(rangers+8,113)
        put(ranger_items+111*4,player)
        put(relations+4,relation_items);put(relations+8,113);put(relation_items+111*4,50)
        put(0,0x10009000)  # caller's existing Win32 exception-chain frame
        generator=0x10008000
        # push ebx; mov ebx,edx; push ecx; mov edx,eax;
        # mov eax,[eax+1c]; call TPlanet.RelationToRanger; fill offer; ret.
        stub=bytearray.fromhex('53 89 d3 51 89 c2 8b 40 1c e8')
        stub+=struct.pack('<i',0x77d484-(generator+len(stub)+4))
        stub+=bytes.fromhex('59 c7 01 00 00 00 00 c6 03 02 c7 43 0c 39 30 00 00 b8 01 00 00 00 5b c3')
        emulator.mem_write(generator,bytes(stub))
        emulator.mem_write(0x76332c,b'\xe9'+struct.pack('<i',generator-0x763331))
        put(0x878008,0x12345678)
        invalid_index=[]
        def list_get(uc, address, size, _):
            if uc.reg_read(UC_X86_REG_EDX)&0x80000000:
                invalid_index.append(-1);uc.emu_stop()

        emulator.hook_add(UC_HOOK_CODE,list_get,begin=0x416368,end=0x416368)
        generated=[]
        def generator_context(uc, address, size, _):
            generated.append((bytes(uc.mem_read(player+0x1c,4)), bytes(uc.mem_read(player+0x24,4))))
        emulator.hook_add(UC_HOOK_CODE,generator_context,begin=generator,end=generator)
        for owner in (5,6,8):
            emulator.mem_write(planet+0x74,bytes([owner]))
            assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff, \
                f'Planet owner {owner} has no government offer'
            assert invoke(exported[b'FHDFindQuest_Reward']) == 0 and not generated
        emulator.mem_write(planet+0x74,b'\x02')
        for owner in (1,2):
            emulator.mem_write(star+0x48,bytes([owner]))
            assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff and not generated
        emulator.mem_write(star+0x48,b'\0')
        put(player+0x24,0x10007100)
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 2 and not invalid_index, \
            f'Actual RelationToRanger received an unregistered ranger: {invalid_index}'
        assert generated == [(struct.pack('<I',planet),struct.pack('<I',star))], 'Remote offer must use the issuing planet AND system'
        assert invoke(exported[b'FHDFindQuest_Reward']) == 12345
        assert bytes(emulator.mem_read(player+0x1c,4)) == struct.pack('<I',0x10007000)
        assert bytes(emulator.mem_read(player+0x24,4)) == struct.pack('<I',0x10007100)
        assert bytes(emulator.mem_read(0x10009404+80+0x4c,4)) == struct.pack('<I',11)
        assert bytes(emulator.mem_read(0x878008,4)) == struct.pack('<I',0x12345678)
        assert bytes(emulator.mem_read(0,4)) == struct.pack('<I',0x10009000)
        assert bytes(emulator.mem_read(0x10009404+0x4c,4)) == struct.pack('<I',7)
        assert bytes(emulator.mem_read(0x10009404+0x4c,4)) == struct.pack('<I',7)
        # Run the REAL generator's active-quest and relation gates. Only its
        # localized refusal text is replaced by an empty string. Stop offer
        # construction after those gates, leaving the real cleanup intact.
        emulator.mem_write(0x76332c,bytes(game_image[0x36332c:0x36332c+9]))
        emulator.ctl_remove_cache(0x76332c,0x763335)
        emulator.mem_write(0x7df080,bytes.fromhex('c7 01 00 00 00 00 c3'))
        put(player+0x520,0x1000a000)
        put(0x1000a004,0x1000a100);put(0x1000a008,1)
        put(0x1000a100,0x1000a200);put(0x1000a204,planet)
        allowed=[]
        def reached_generation(uc, address, size, _):
            allowed.append(True)
            uc.reg_write(UC_X86_REG_EIP,0x766189)
        emulator.hook_add(UC_HOOK_CODE,reached_generation,begin=0x763501,end=0x763501)
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff and not allowed, 'Accepted quest at issuing planet must be unavailable'
        put(0x1000a008,0);put(relation_items+111*4,10)
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff and not allowed, 'Poor player relations must suppress offers'
        put(relation_items+111*4,80)
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff and allowed, 'Eligible planet must reach offer generation'
        assert bytes(emulator.mem_read(player+0x1c,4)) == struct.pack('<I',0x10007000)
        assert bytes(emulator.mem_read(player+0x24,4)) == struct.pack('<I',0x10007100)
        assert bytes(emulator.mem_read(0,4)) == struct.pack('<I',0x10009000)
        assert bytes(emulator.mem_read(0x10009404+0x4c,4)) == struct.pack('<I',7), 'PB scratch counters must be restored'
        emulator.mem_write(0x76332c,b'\xe9'+struct.pack('<i',generator-0x763331))
        emulator.ctl_remove_cache(0x76332c,0x763335)
        # Government chooses the available PB before its ordinary offer.
        emulator.mem_write(battle_selector+len(battle_stub)-6,b'\xb8\x2a\0\0\0\xc3')
        emulator.ctl_remove_cache(battle_selector,battle_selector+len(battle_stub))
        generated.clear()
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 5
        assert not generated and invoke(exported[b'FHDFindQuest_Reward']) == 0
        assert bytes(emulator.mem_read(0x10009404+0x4c,4)) == struct.pack('<I',7)
        assert bytes(emulator.mem_read(player+0x1c,4)) == struct.pack('<I',0x10007000)
        assert bytes(emulator.mem_read(player+0x24,4)) == struct.pack('<I',0x10007100)
        emulator.mem_write(battle_selector,battle_stub)
        emulator.ctl_remove_cache(battle_selector,battle_selector+len(battle_stub))
        # Call the compiled cleanup handler with the unwind flag. This is a
        # controlled callback invocation, not Windows RtlUnwind emulation.
        exception=0x10009200
        put(exception+4,2)
        unwind_stub=bytes.fromhex('c7 05 08 80 87 00 01 ef cd ab 64 a1 00 00 00 00 6a 00 6a 00 50 68')
        unwind_stub+=struct.pack('<I',exception)
        unwind_stub+=bytes.fromhex('ff 50 04 83 c4 10 31 c0 c3')
        emulator.mem_write(generator,unwind_stub)
        emulator.ctl_remove_cache(generator,generator+len(stub))
        assert invoke(exported[b'FHDFindQuest_Probe'],planet) == 0xffffffff
        assert invoke(exported[b'FHDFindQuest_Reward']) == 0
        assert bytes(emulator.mem_read(player+0x1c,4)) == struct.pack('<I',0x10007000)
        assert bytes(emulator.mem_read(player+0x24,4)) == struct.pack('<I',0x10007100)
        assert bytes(emulator.mem_read(0x878008,4)) == struct.pack('<I',0x12345678)
        assert bytes(emulator.mem_read(0,4)) == struct.pack('<I',0x10009000)
    print('PASS: compiled PE32 DLL Init on actual EXE, QuestMarker patch sites and relocated DLL; invalid generator remains rejected')
    print('PASS: compiled DLL Probe calls actual EXE RelationToRanger with a registered player (113 rangers); reward and context restored')
    print('PASS: compiled DLL unwind cleanup callback restores location, RNG, reward and exception-chain head, including relocated DLL')
    print('PASS: actual EXE generator rejects accepted quests and poor relations; compiled bridge excludes uninhabited/occupied owners and gives planetary battle priority without changing PB counters')


HARNESS = r'''
extern u8 testImage[];
static u8 player[0x700], planet[0x100], star[0x100];
static u32 rangerList[4];
static u8 *rangerItems[113];
static int cleared, calls, badArgs, answer=1, kind=2, simulateUnwind;
static u16 dummyText;
static ptr getPlayerStub(void) {return player;}
__attribute__((used,noinline)) static void clearStub(u16 **message) {
    if(*message!=&dummyText)badArgs=1;
    *message=0;cleared++;
}
__attribute__((used,noinline)) static int probeStub(u8 *ranger,u8 *offer,u16 **message) {
    calls++;
    /* Real Delphi TList.IndexOf from the EXE: copying a TRanger cannot
       preserve its identity in the galaxy's registered-ranger list. */
    register ptr list __asm__("eax")=rangerList;
    register ptr wanted __asm__("edx")=ranger;
    ptr indexOf=testImage+0x163c4;
    __asm__ volatile("call *%2":"+a"(list),"+d"(wanted):"m"(indexOf):"ecx","memory","cc");
    if((i32)list!=111 || ranger!=player || *(u8 **)(ranger+0x1c)!=planet || *(u8 **)(ranger+0x24)!=star)badArgs=1;
    for(u32 i=0;i<sizeof(player);++i)
        if((i<0x1c || i>=0x20) && (i<0x24 || i>=0x28) && ranger[i]!=(u8)i)badArgs=1;
    if(FHDFindQuest_Probe(planet)!=-2)badArgs=1; /* no nested scan */
    *(u32 *)(game+0x478008)=0xabcdef01;
    *message=&dummyText;
    offer[0]=(u8)kind;
    *(i32 *)(offer+0xc)=12345;
    if(simulateUnwind) {
        ptr *frame;
        __asm__ volatile("movl %%fs:0,%0":"=r"(frame));
        if(!frame || !frame[1])badArgs=1;
        else {
            typedef int (*Handler)(u32 *,ptr,ptr,ptr);
            Handler handler=(Handler)frame[1];
            u32 exception[2]={0,0};
            if(handler(exception,frame,0,0)!=1 || *(u8 **)(player+0x1c)!=planet)badArgs=1;
            exception[1]=2;
            if(handler(exception,frame,0,0)!=1 || *(u32 *)(player+0x1c)!=0x1f1e1d1c || *(u32 *)(game+0x478008)!=0x12345678 || boardBusy || *message)badArgs=1;
        }
        return 0;
    }
    return answer;
}
NAKED static void probeRegisterStub(void) {
    __asm__ volatile("pushl %ecx;pushl %edx;pushl %eax;call probeStub;addl $12,%esp;ret");
}
NAKED static void clearRegisterStub(void) {
    __asm__ volatile("pushl %eax;call clearStub;addl $4,%esp;ret");
}
static void jumpTo(u8 *site,ptr target) {
    site[0]=0xe9;*(i32 *)(site+1)=(i32)((u8 *)target-site-5);
}
static int resetInit(void) {enabled=0;return FHDFindQuest_Init();}
static int tests(void) {
    *(u8 **)(testPeb+8)=testImage;
    if(FHDFindQuest_Probe(planet)!=-2)return 9;
    if(resetInit()!=0)return 10; /* screenshot's code 4 regression */
    u8 saved=testImage[0x36332c];testImage[0x36332c]^=1;
    if(resetInit()!=4)return 11;
    testImage[0x36332c]=saved;
    saved=testImage[0x5d18];testImage[0x5d18]^=1;
    if(resetInit()!=4)return 12;
    testImage[0x5d18]=saved;
    u8 *nt=testImage+*(u32 *)(testImage+0x3c);
    u32 timestamp=*(u32 *)(nt+8);*(u32 *)(nt+8)^=1;
    if(resetInit()!=3)return 13;
    *(u32 *)(nt+8)=timestamp;
    /* The standalone QuestMarker 0.3.8 patches these separate code sites. */
    jumpTo(testImage+0x1276ec,probeRegisterStub);
    jumpTo(testImage+0x129e34,probeRegisterStub);
    jumpTo(testImage+0x12b518,probeRegisterStub);
    jumpTo(testImage+0x12b810,probeRegisterStub);
    *(u32 *)(testImage+0x3a3ce4)=(u32)probeRegisterStub;
    if(resetInit()!=0)return 14;
    /* Controlled calls only: never execute the game generator in this test. */
    jumpTo(testImage+0x38c078,getPlayerStub);
    jumpTo(testImage+0x36332c,probeRegisterStub);
    jumpTo(testImage+0x5d18,clearRegisterStub);
    for(u32 i=0;i<sizeof(player);++i)player[i]=(u8)i;
    rangerList[1]=(u32)rangerItems;rangerList[2]=113;rangerItems[111]=player;
    *(u8 **)(planet+0x18)=star;
    *(u32 *)(game+0x478008)=0x12345678;
    if(FHDFindQuest_Probe(planet)!=2 || FHDFindQuest_Reward()!=12345)return 15;
    if(*(u32 *)(game+0x478008)!=0x12345678 || cleared!=1 || calls!=1 || badArgs)return 16;
    for(u32 i=0;i<sizeof(player);++i)if(player[i]!=(u8)i)return 17;
    for(kind=0;kind<=4;++kind)
        if(FHDFindQuest_Probe(planet)!=kind || FHDFindQuest_Reward()!=12345)return 18;
    answer=0;
    if(FHDFindQuest_Probe(planet)!=-1 || FHDFindQuest_Reward()!=0)return 19;
    answer=1;kind=5;
    if(FHDFindQuest_Probe(planet)!=-1 || FHDFindQuest_Reward()!=0)return 20;
    if(FHDFindQuest_Probe(0)!=-1)return 21;
    *(u8 **)(planet+0x18)=0;
    if(FHDFindQuest_Probe(planet)!=-1)return 22;
    if(*(u32 *)(game+0x478008)!=0x12345678 || cleared!=8 || calls!=8 || badArgs)return 23;
    *(u8 **)(planet+0x18)=star;
    simulateUnwind=1;
    if(FHDFindQuest_Probe(planet)!=-1 || cleared!=9 || calls!=9 || badArgs)return 24;
    for(u32 i=0;i<sizeof(player);++i)if(player[i]!=(u8)i)return 25;
    ptr chain;
    __asm__ volatile("movl %%fs:0,%0":"=r"(chain));
    if(chain)return 26;
    return 0;
}
void _start(void) {
    int result=tests();
    __asm__ volatile("int $0x80"::"a"(1),"b"(result):"memory");
    __builtin_unreachable();
}
'''


def run(exe, root):
    verify_dll_init(exe, root/'Native/FHDFindQuest.dll')
    source = (root/'SOURCE/Native/find_quest.c').read_text()
    accessor = 'NAKED static ptr pebAddress(void) {__asm__ volatile("movl %fs:0x30,%eax;ret");}'
    assert source.count(accessor) == 1, 'Update the test PEB adapter for this source'
    source = source.replace(accessor, 'static u8 testPeb[32]; static ptr pebAddress(void) {return testPeb;}')
    with tempfile.TemporaryDirectory(prefix='findquest-native-') as directory:
        temp = Path(directory)
        fixture = temp/'mapped.bin'
        fixture.write_bytes(mapped_pe(exe))
        harness = temp/'harness.c'
        image_asm = '__asm__(".section .testimage,\\\"awx\\\",@progbits\\n.global testImage\\ntestImage:\\n.incbin \\\"' + str(fixture) + '\\\"\\n.previous");\n'
        harness.write_text(source + '\n' + image_asm + HARNESS)
        binary = temp/'test'
        subprocess.run(['gcc', '-m32', '-std=c11', '-O2', '-ffreestanding', '-fno-builtin',
                        '-fno-stack-protector', '-fno-pic', '-fno-pie', '-nostdlib', '-no-pie',
                        '-Wl,--build-id=none', '-Wl,-e,_start', str(harness), '-o', str(binary)], check=True)
        result = execute_x86(binary)
        assert result == 0, f'Native regression failed at case {result}'
    print('PASS: actual EXE Init, guarded rejection, QuestMarker patch sites; x86 Probe ABI, registered identity, kinds, rewards, RNG/player restoration, reentrancy and controlled unwind callbacks')


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        raise SystemExit('Usage: verify_native.py RANGERS_EXE [MOD_DIR]')
    root = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else Path(__file__).resolve().parent.parent
    run(Path(sys.argv[1]).resolve(), root)
