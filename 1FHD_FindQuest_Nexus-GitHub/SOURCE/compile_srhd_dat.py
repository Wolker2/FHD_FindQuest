from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re, struct, zlib, sys

@dataclass
class Elem:
    name:str
    value:str|None=None
    child:'Block|None'=None
@dataclass
class Block:
    sorted:bool=True
    elems:list[Elem]=field(default_factory=list)

def parse_blockpar(path:Path)->Block:
    lines=path.read_text(encoding='utf-8').splitlines()
    root=Block(True); stack=[root]
    i=0
    while i<len(lines):
        raw=lines[i]; i+=1
        line=raw.strip(' \t\r\n')
        if not line or line.startswith('//'): continue
        if '//' in line:
            line=line.split('//',1)[0].rstrip()
        if not line: continue
        if line.startswith('}'):
            if len(stack)==1: raise ValueError(f'unbalanced close line {i}')
            stack.pop(); continue
        # RScript entries can contain literal braces (including `NNN={`).
        # A numbered assignment is always a value, not a BlockPar child.
        if re.match(r'^\d+=', line):
            name,val=line.split('=',1)
            stack[-1].elems.append(Elem(name,value=val))
            continue
        if '{' in line:
            head=line.split('{',1)[0].rstrip()
            if head.endswith('^') or head.endswith('~'):
                stack[-1].sorted=head.endswith('^'); head=head[:-1].rstrip()
            name=head.split('=',1)[0].rstrip()
            child=Block(True)
            stack[-1].elems.append(Elem(name,child=child)); stack.append(child); continue
        if '=' in line:
            name,val=line.split('=',1); name=name.rstrip(); val=val.lstrip()
            if val.startswith('<<<'):
                buf=[]
                while i<len(lines):
                    rr=lines[i]; i+=1
                    if rr.lstrip(' \t').startswith('>>>'): break
                    buf.append(rr)
                val='\n'.join(buf).rstrip('\r\n')
            stack[-1].elems.append(Elem(name,value=val)); continue
    if len(stack)!=1: raise ValueError('unclosed block')
    return root

def ordered(block:Block):
    if not block.sorted:
        return list(block.elems)
    # stable sort by name matches RB tree duplicate chaining behavior
    return sorted(enumerate(block.elems), key=lambda p:(p[1].name,p[0]))

def wstr(s:str)->bytes: return s.encode('utf-16le')+b'\x00\x00'

def ser_bp_block(block:Block, include_header=True)->bytes:
    out=bytearray()
    if include_header:
        out+=struct.pack('<BI',1 if block.sorted else 0,len(block.elems))
    items=[e for _,e in ordered(block)] if block.sorted else list(block.elems)
    # counts per name for sorted blocks
    counts={}
    if block.sorted:
        for e in items: counts[e.name]=counts.get(e.name,0)+1
    seen={}
    for e in items:
        if block.sorted:
            idx=seen.get(e.name,0); cnt=counts[e.name]
            out+=struct.pack('<II',idx,cnt if idx==0 else 0)
            seen[e.name]=idx+1
        if e.child is None:
            out+=b'\x01'+wstr(e.name)+wstr(e.value or '')
        else:
            out+=b'\x02'+wstr(e.name)
            out+=struct.pack('<BI',1 if e.child.sorted else 0,len(e.child.elems))
            out+=ser_bp_block(e.child,include_header=False)
    return bytes(out)

def ser_cache_block(block:Block, include_header=True)->bytes:
    out=bytearray()
    if include_header: out+=struct.pack('<I',len(block.elems))
    # CacheData always sorted
    items=[e for _,e in sorted(enumerate(block.elems),key=lambda p:(p[1].name,p[0]))]
    for e in items:
        if e.child is None:
            out+=b'\x01'+wstr(e.name)+wstr(e.value or '')
        else:
            out+=b'\x02'+wstr(e.name)+struct.pack('<I',len(e.child.elems))+ser_cache_block(e.child,include_header=False)
    return bytes(out)

def cipher(buf:bytearray, seed:int, start=8):
    s=seed
    for i in range(start,len(buf)):
        hi,lo=divmod(s,0x1f31d)
        s=lo*0x41a7-hi*0xb14
        if s<1: s+=0x7fffffff
        rnd=s-1
        buf[i]^=rnd&255

def pack_dat(raw:bytes,key:int,seed=0x51A2C3D4)->bytes:
    compressed=b'ZL01'+struct.pack('<I',len(raw))+zlib.compress(raw,9)
    h=zlib.crc32(compressed)&0xffffffff
    out=bytearray(struct.pack('<II',h,(seed^key)&0xffffffff)+compressed)
    cipher(out,seed,8)
    return bytes(out)

def build_bp(src,out):
    raw=ser_bp_block(parse_blockpar(Path(src)))
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_bytes(pack_dat(raw,0xB1E8C689))
def build_cache(src,out):
    raw=ser_cache_block(parse_blockpar(Path(src)))
    Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_bytes(pack_dat(raw,0xEA8F3F37))

if __name__=='__main__':
    mode,src,out=sys.argv[1:4]
    (build_bp if mode=='bp' else build_cache)(src,out)


def unpack_dat_bytes(data:bytes,key:int):
    b=bytearray(data); h,enc=struct.unpack_from('<II',b,0); seed=(enc^key)&0xffffffff
    s=seed
    for i in range(8,len(b)):
        hi,lo=divmod(s,0x1f31d); s=lo*0x41a7-hi*0xb14
        if s<1:s+=0x7fffffff
        b[i]^=(s-1)&255
    comp=bytes(b[8:])
    assert (zlib.crc32(comp)&0xffffffff)==h
    assert comp[:4]==b'ZL01'
    n=struct.unpack_from('<I',comp,4)[0]; raw=zlib.decompress(comp[8:]); assert len(raw)==n
    return raw

def _read_wstr(raw,pos):
    start=pos
    while raw[pos:pos+2]!=b'\x00\x00': pos+=2
    return raw[start:pos].decode('utf-16le'),pos+2

def parse_bp_raw(raw:bytes):
    def rec(pos,header=True):
        if header:
            sort=bool(raw[pos]); pos+=1; count=struct.unpack_from('<I',raw,pos)[0]; pos+=4
        else: raise RuntimeError
        block=Block(sort)
        for _ in range(count):
            if sort: pos+=8
            typ=raw[pos]; pos+=1
            name,pos=_read_wstr(raw,pos)
            if typ==1:
                val,pos=_read_wstr(raw,pos); block.elems.append(Elem(name,value=val))
            elif typ==2:
                csort=bool(raw[pos]); pos+=1; ccount=struct.unpack_from('<I',raw,pos)[0]; pos+=4
                child=Block(csort)
                # parse child body inline
                def body(block,pos,count):
                    for _ in range(count):
                        if block.sorted: pos+=8
                        typ=raw[pos]; pos+=1
                        nm,pos=_read_wstr(raw,pos)
                        if typ==1:
                            vv,pos=_read_wstr(raw,pos); block.elems.append(Elem(nm,value=vv))
                        elif typ==2:
                            ss=bool(raw[pos]);pos+=1;cc=struct.unpack_from('<I',raw,pos)[0];pos+=4
                            ch=Block(ss); pos=body(ch,pos,cc); block.elems.append(Elem(nm,child=ch))
                        else: raise ValueError((typ,pos,nm))
                    return pos
                pos=body(child,pos,ccount); block.elems.append(Elem(name,child=child))
            else: raise ValueError((typ,pos,name))
        return block,pos
    return rec(0)[0]
