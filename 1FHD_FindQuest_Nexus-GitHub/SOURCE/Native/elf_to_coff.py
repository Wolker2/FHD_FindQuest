#!/usr/bin/env python3
"""Convert freestanding GCC ELF32/i386 REL objects to COFF for GNU PE ld.
Only R_386_32 and R_386_PC32 are accepted; no ELF runtime/TLS/GOT support.
"""
import struct,sys,pathlib
source=pathlib.Path(sys.argv[1]).read_bytes()
assert source[:7]==b'\x7fELF\x01\x01\x01'
assert struct.unpack_from('<HH',source,16)==(1,3)
shoff=struct.unpack_from('<I',source,32)[0];shsize,shcount,shstrings=struct.unpack_from('<HHH',source,46)
sections=[struct.unpack_from('<10I',source,shoff+i*shsize) for i in range(shcount)]
strings_section=sections[shstrings];names=source[strings_section[4]:strings_section[4]+strings_section[5]]
def zstr(data,offset):return data[offset:data.index(b'\0',offset)]
selected=[i for i,s in enumerate(sections) if s[2]&2 and s[1] in (1,8)]
secmap={old:new+1 for new,old in enumerate(selected)}
pool=bytearray(b'\0\0\0\0')
def namefield(name):
 if len(name)<=8:return name.ljust(8,b'\0')
 off=len(pool);pool.extend(name+b'\0');return struct.pack('<II',0,off)
# Full ELF symbol table, including section symbols that objcopy would discard.
symsec=next(s for s in sections if s[1]==2);symstrings=sections[symsec[6]]
snames=source[symstrings[4]:symstrings[4]+symstrings[5]]
symbols=[];symmap={}
for i,o in enumerate(range(symsec[4],symsec[4]+symsec[5],16)):
 n,value,size,info,other,index=struct.unpack_from('<IIIBBH',source,o)
 if i==0:continue
 if index not in secmap and index not in (0,0xfff1):continue
 name=zstr(snames,n) if n else zstr(names,sections[index][0])
 symmap[i]=len(symbols)
 symbols.append(struct.pack('<8sIhHBB',namefield(name),value,secmap.get(index,0 if index==0 else -1),0x20 if info&15==2 else 0,2 if info>>4 else 3,0))
raw={i:bytearray(source[s[4]:s[4]+s[5]]) if s[1]!=8 else bytearray() for i in selected for s in [sections[i]]}
relocs={i:[] for i in selected}
for s in sections:
 if s[1]!=9 or s[7] not in secmap:continue
 target=s[7]
 for o in range(s[4],s[4]+s[5],8):
  addr,info=struct.unpack_from('<II',source,o);symbol=info>>8;kind=info&255
  assert kind in (1,2),(kind,hex(addr));assert symbol in symmap
  if kind==2:
   addend=struct.unpack_from('<I',raw[target],addr)[0];struct.pack_into('<I',raw[target],addr,(addend+4)&0xffffffff)
  relocs[target].append(struct.pack('<IIH',addr,symmap[symbol],6 if kind==1 else 0x14))
headers=[];payload=bytearray();base=20+40*len(selected)
for i in selected:
 s=sections[i];name=zstr(names,s[0]);namef=namefield(name)
 # Section long names are string-table references in slash-decimal form.
 if len(name)>8:namef=('/'+str(struct.unpack_from('<I',namef,4)[0])).encode().ljust(8,b'\0')
 rawptr=base+len(payload) if raw[i] else 0;payload.extend(raw[i]);relptr=base+len(payload) if relocs[i] else 0
 payload.extend(b''.join(relocs[i]));flags=0x60500020 if s[2]&4 else (0xc0500080 if s[1]==8 else (0xc0500040 if s[2]&1 else 0x40500040))
 headers.append(struct.pack('<8sIIIIIIHHI',namef,0,0,s[5],rawptr,relptr,0,len(relocs[i]),0,flags))
symptr=base+len(payload);struct.pack_into('<I',pool,0,len(pool))
out=struct.pack('<HHIIIHH',0x14c,len(selected),0,symptr,len(symbols),0,0)+b''.join(headers)+payload+b''.join(symbols)+pool
pathlib.Path(sys.argv[2]).write_bytes(out)
