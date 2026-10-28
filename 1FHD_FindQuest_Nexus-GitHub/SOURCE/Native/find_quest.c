/* FindQuest scan bridge for supplied Rangers(3).exe 2.1.2500.
   TimeDateStamp 0x6ac53b97, SizeOfImage 0x461000; see README.md (executable compatibility).
   This module installs no hooks and writes no executable code.
   QuestMarker remains a separate mod and owns its own callbacks. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int i32;
typedef void *ptr;
#define STDCALL __attribute__((stdcall))
#define NAKED __attribute__((naked))
static u8 *game;
static int enabled;
static i32 boardReward;
static u32 boardTarget;
static int boardBusy;
/* Win32 x86 registration record. Cleanup runs only during stack unwind;
   exceptions continue to the game's existing handlers. */
typedef struct ProbeFrame {
    ptr previous;
    ptr handler;
    u8 *player;
    u8 *savedPlanet;
    u8 *savedStar;
    u32 *seed;
    u32 savedSeed;
    u16 **message;
    u8 *battleData;
    u32 *battleWeights;
    u32 battleCount;
} ProbeFrame;
NAKED static ptr pebAddress(void) {__asm__ volatile("movl %fs:0x30,%eax;ret");}
static void restoreContext(ProbeFrame *frame) {
    *(u8 **)(frame->player+0x1c)=frame->savedPlanet;
    *(u8 **)(frame->player+0x24)=frame->savedStar;
    *frame->seed=frame->savedSeed;
    for(u32 i=0;i<frame->battleCount;++i)
        *(u32 *)(frame->battleData+i*80+0x4c)=frame->battleWeights[i];
}
static void clearText(u16 **message) {
    if(!*message)return;
    register ptr textAddr __asm__("eax")=message;
    ptr clearWide=game+0x5d18;
    __asm__ volatile("call *%1" : "+a"(textAddr) : "m"(clearWide)
                     : "ecx","edx","memory","cc");
}
static int probeUnwind(u32 *exception,ProbeFrame *frame,ptr context,ptr dispatch) {
    (void)context;(void)dispatch;
    if(exception[1]&6) { /* EXCEPTION_UNWINDING | EXCEPTION_EXIT_UNWIND */
        restoreContext(frame);
        boardBusy=0;boardReward=0;boardTarget=0;
        clearText(frame->message);
    }
    return 1; /* ExceptionContinueSearch; do not swallow game exceptions. */
}
static int matches(const u8 *site,const u8 *bytes,u32 size) {
    for(u32 i=0;i<size;++i)if(site[i]!=bytes[i])return 0;
    return 1;
}
int FHDFindQuest_Init(void) {
    if(enabled)return 0;
    u8 *peb=(u8 *)pebAddress();
    if(!peb)return 1;
    game=*(u8 **)(peb+8);
    if(!game||*(u16 *)game!=0x5a4d)return 2;
    u8 *nt=game+*(u32 *)(game+0x3c);
    if(*(u32 *)nt!=0x4550||*(u16 *)(nt+24)!=0x10b)return 2;
    if(*(u32 *)(nt+24+56)!=0x461000||*(u32 *)(nt+8)!=0x6ac53b97)return 3;
    const u8 generatorBytes[]={0x55,0x8b,0xec,0x51,0xb9,0x68,0x00,0x00,0x00};
    const u8 clearWideBytes[]={0x8b,0x10,0x85,0xd2};
    const u8 battleSelectorBytes[]={0x55,0x8b,0xec,0x83,0xc4,0xe8,0x53};
    /* RVA is 0x322228. Objdump's .text+0x321228 is section-relative. */
    if(!matches(game+0x322228,generatorBytes,9)||!matches(game+0x5d18,clearWideBytes,4))return 4;
    if(!matches(game+0x351d90,battleSelectorBytes,7))return 4;
    enabled=1;
    return 0;
}
int FHDFindQuest_Probe(u8 *planet) {
    boardReward=0;boardTarget=0;
    if(!enabled||!game||boardBusy)return -2;
    if(!planet||!*(u8 **)(planet+0x18))return -1;
    /* FPeopleCnt can be positive on an uninhabited planet. The generator
       assumes a government screen and does not reject FOwner=None itself.
       Government dialogue also refuses offers outside coalition systems. */
    if((planet[0x74]>4 && planet[0x74]!=7) || (*(u8 **)(planet+0x18))[0x48]!=0)return -1;
    typedef ptr (*GetPlayer)(void);
    u8 *player=(u8 *)((GetPlayer)(game+0x347300))();
    if(!player)return -2;
    /* Gov's branch at 0x522194 chooses an available planetary battle before
       calling the ordinary generator. Selector 0x751d90 writes only scratch
       counters at +0x4c in the global 80-byte PB records; preserve them too. */
    int checkBattle=0;
    u8 *battleData=0;
    u32 battleCount=0;
    if(!player[0x6ac]) {
        i32 *forced=*(i32 **)(game+0x4132d8);
        if(!forced)return -2;
        checkBattle=(*forced<0);
        if(checkBattle) {
            u8 **slot=*(u8 ***)(game+0x413b08);
            if(!slot)return -2;
            battleData=*slot;
            if(battleData)battleCount=*(u32 *)(battleData-4);
            if(battleCount>4096)return -2;
        }
    }
    u32 battleWeights[battleCount?battleCount:1];
    for(u32 i=0;i<battleCount;++i)battleWeights[i]=*(u32 *)(battleData+i*80+0x4c);
    /* RelationToRanger resolves the registered object by pointer identity.
       A copied TRanger has no list entry and produces index -1. */
    u8 *savedPlanet=*(u8 **)(player+0x1c);
    u8 *savedStar=*(u8 **)(player+0x24);
    u8 offer[0x20]={0};
    u16 *message=0;
    u32 *seed=(u32 *)(game+0x409008), savedSeed=*seed;
    ProbeFrame frame;
    __asm__ volatile("movl %%fs:0,%0":"=r"(frame.previous));
    frame.handler=probeUnwind;frame.player=player;frame.savedPlanet=savedPlanet;
    frame.savedStar=savedStar;
    frame.seed=seed;frame.savedSeed=savedSeed;frame.message=&message;
    frame.battleData=battleData;frame.battleWeights=battleWeights;frame.battleCount=battleCount;
    boardBusy=1;
    __asm__ volatile("movl %0,%%fs:0"::"r"(&frame):"memory");
    *(u8 **)(player+0x1c)=planet;
    /* The original generator also uses player.FStar for nearby targets.
       Both pointers must describe the government being previewed. */
    *(u8 **)(player+0x24)=*(u8 **)(planet+0x18);
    int battle=-1;
    if(checkBattle) {
        register ptr arg __asm__("eax")=player;
        ptr selector=game+0x351d90;
        __asm__ volatile("call *%1" : "+a"(arg) : "m"(selector)
                         : "ecx","edx","memory","cc");
        battle=(i32)arg;
    }
    int found=0;
    if(battle<0) {
        register ptr arg __asm__("eax")=player;
        register ptr target __asm__("edx")=offer;
        register ptr result __asm__("ecx")=&message;
        ptr generator=game+0x322228;
        __asm__ volatile("call *%3" : "+a"(arg),"+d"(target),"+c"(result)
                         : "m"(generator) : "memory","cc");
        found=(u8)(u32)arg;
    }
    restoreContext(&frame);
    clearText(&message);
    __asm__ volatile("movl %0,%%fs:0"::"r"(frame.previous):"memory");
    boardBusy=0;
    if(battle>=0)return 5;
    if(!found || offer[0]>4)return -1;
    boardReward=*(i32 *)(offer+0xc);
    boardTarget=*(u32 *)(offer+0x10);
    return offer[0];
}

int FHDFindQuest_Reward(void) {return boardReward;}
int STDCALL DllMain(ptr module,u32 reason,ptr reserved) {
    (void)module;(void)reason;(void)reserved;return 1;
}
