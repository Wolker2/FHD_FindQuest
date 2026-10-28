"""Lossless source for GAI v1 raw-GI frames and named timing sequences.

The original FindQuest animation uses 20 raw GI2 frames and one sequence.
Every frame is editable GI JSON; frame indices/delays and header fields are
explicit. No original GAI or opaque auxiliary payload is a build input.
"""
import struct
from gi_codec import decode as decode_gi,encode as encode_gi

def decode(data):
    if len(data)<48 or data[:4]!=b'gai\0':raise ValueError('Not a GAI file')
    h=struct.unpack_from('<11I',data,4)
    version,x,y,width,height,count,reserved,aux_offset,aux_size,res1,res2=h
    if version!=1 or aux_offset!=48+count*8:raise ValueError('Unsupported GAI layout')
    auxiliary=data[aux_offset:aux_offset+aux_size]
    sequence_count=struct.unpack_from('<I',auxiliary)[0];sequences=[]
    for index in range(sequence_count):
        name_offset,timeline=struct.unpack_from('<II',auxiliary,4+index*8)
        end=name_offset
        while auxiliary[end:end+2]!=b'\0\0':
            end+=2
            if end>=len(auxiliary):raise ValueError('Sequence name not terminated')
        name=auxiliary[name_offset:end].decode('utf-16le')
        steps=struct.unpack_from('<I',auxiliary,timeline)[0]
        entries=[]
        for step in range(steps):
            frame,delay=struct.unpack_from('<II',auxiliary,timeline+4+8*step)
            if frame>=count:raise ValueError('Sequence frame out of range')
            entries.append({'frame':frame,'delay_ms':delay})
        sequences.append({'name':name,'steps':entries})
    frames=[];expected=aux_offset+aux_size
    for index in range(count):
        offset,size=struct.unpack_from('<II',data,48+8*index)
        if offset!=expected or not size:raise ValueError('Unsupported GAI frame layout')
        frames.append(decode_gi(data[offset:offset+size]));expected+=size
    if expected!=len(data):raise ValueError('Unparsed GAI remainder')
    source={'format':'srhd-gai1-json-v1','version':version,'origin':[x,y],
            'width':width,'height':height,'reserved':[reserved,res1,res2],
            'sequences':sequences,'frames':frames}
    if encode(source)!=data:raise ValueError('GAI is not losslessly represented by this source profile')
    return source

def encode(source):
    if source['format']!='srhd-gai1-json-v1':raise ValueError('Unknown GAI source format')
    frames=[encode_gi(frame)for frame in source['frames']];sequences=source['sequences']
    auxiliary=bytearray(struct.pack('<I',len(sequences))+bytes(8*len(sequences)))
    for index,sequence in enumerate(sequences):
        name_offset=len(auxiliary);name=sequence['name']
        if '\0'in name:raise ValueError('Embedded NUL in sequence name')
        auxiliary.extend(name.encode('utf-16le')+b'\0\0');timeline=len(auxiliary)
        auxiliary.extend(struct.pack('<I',len(sequence['steps'])))
        for step in sequence['steps']:
            if not 0<=step['frame']<len(frames):raise ValueError('Sequence frame out of range')
            auxiliary.extend(struct.pack('<II',step['frame'],step['delay_ms']))
        struct.pack_into('<II',auxiliary,4+index*8,name_offset,timeline)
    count=len(frames);aux_offset=48+8*count;offset=aux_offset+len(auxiliary)
    directory=bytearray()
    for frame in frames:directory.extend(struct.pack('<II',offset,len(frame)));offset+=len(frame)
    r0,r1,r2=source['reserved']
    header=struct.pack('<4s11I',b'gai\0',source['version'],*source['origin'],source['width'],source['height'],count,r0,aux_offset,len(auxiliary),r1,r2)
    return header+directory+auxiliary+b''.join(frames)
