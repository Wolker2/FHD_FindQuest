#!/usr/bin/env python3
"""Lossless GI type-2 <-> editable JSON: RGB565 samples and 6-bit alpha runs.

No encoded binary blobs are stored in JSON. All layer bounds, color samples,
RLE commands and reserved fields are explicit. PNGs are convenient previews;
layer JSON is the lossless source for byte-identical builds.
"""
import argparse,json,struct
from pathlib import Path

MAGIC=b'gi\0\0'

def decode(data):
    if len(data)<160 or data[:4]!=MAGIC:raise ValueError('Not a GI image')
    header=list(struct.unpack_from('<15I',data,4))
    if header[9:11]!=[2,3]:raise ValueError('Only GI type 2 with three layers is supported')
    result={'format':'srhd-gi2-json-v1','version':header[0],
            'bounds':header[1:5],'masks':header[5:9],
            'reserved':header[11:15],'layers':[]}
    consumed=160
    for index in range(3):
        offset,size,*desc=struct.unpack_from('<8I',data,64+index*32)
        layer={'bounds':desc[:4],'reserved':desc[4:],
               'pixel_format':'rgb565' if index<2 else 'transparency6',
               'empty_offset':offset if not size else 0,'commands':[]}
        if size:
            if offset!=consumed:raise ValueError('Unexpected layer placement')
            payload=data[offset:offset+size]
            encoded,width,height,flags=struct.unpack_from('<4I',payload)
            if encoded!=size-16:raise ValueError('RLE size mismatch')
            layer.update(width=width,height=height,rle_reserved=flags)
            pos=16;pixel_size=2 if index<2 else 1
            while pos<len(payload):
                command=payload[pos];pos+=1
                if command in (0,128):layer['commands'].append({'end_row':command})
                elif command<128:layer['commands'].append({'skip':command})
                else:
                    count=command-128
                    values=list(struct.unpack_from('<'+('H' if pixel_size==2 else 'B')*count,payload,pos))
                    pos+=count*pixel_size;layer['commands'].append({'pixels':values})
            if pos!=len(payload):raise ValueError('RLE payload mismatch')
            consumed+=size
        result['layers'].append(layer)
    if consumed!=len(data):raise ValueError('Unexpected trailing GI data')
    return result

def encode(source):
    if source['format']!='srhd-gi2-json-v1' or len(source['layers'])!=3:raise ValueError('Unknown GI source format')
    header=struct.pack('<4s15I',MAGIC,source['version'],*source['bounds'],*source['masks'],2,3,*source['reserved'])
    descriptors=[];payloads=[];offset=160
    for index,layer in enumerate(source['layers']):
        stream=bytearray();fmt='H' if index<2 else 'B'
        for command in layer['commands']:
            if 'end_row' in command:
                value=command['end_row']
                if value not in (0,128):raise ValueError('Invalid row marker')
                stream.append(value)
            elif 'skip' in command:
                value=command['skip']
                if not 1<=value<=127:raise ValueError('Invalid transparent run')
                stream.append(value)
            elif 'pixels' in command:
                values=command['pixels']
                if not 1<=len(values)<=127:raise ValueError('Invalid literal run')
                if index==2 and any(v>63 or v<0 for v in values):raise ValueError('Alpha sample outside 0..63')
                stream.append(128+len(values));stream.extend(struct.pack('<'+fmt*len(values),*values))
            else:raise ValueError('Unknown RLE command')
        payload=struct.pack('<4I',len(stream),layer['width'],layer['height'],layer['rle_reserved'])+stream if stream else b''
        descriptors.append(struct.pack('<8I',offset if payload else layer['empty_offset'],len(payload),*layer['bounds'],*layer['reserved']))
        payloads.append(payload);offset+=len(payload)
    return header+b''.join(descriptors)+b''.join(payloads)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('operation',choices=['decode','encode']);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.operation=='decode':a.output.write_text(json.dumps(decode(a.input.read_bytes()),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:a.output.write_bytes(encode(json.loads(a.input.read_text('utf-8'))))
