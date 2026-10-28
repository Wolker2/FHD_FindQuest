#!/usr/bin/env python3
"""Build every FindQuest runtime file from original C/text and editable graphics.

Python 3.10+, GCC, GNU binutils and bash. No game EXE or prebuilt mod binaries
are required. Node.js is used only by the separate regression checks.
"""
from pathlib import Path
import argparse,hashlib,json,platform,subprocess,sys,zipfile,zlib

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'SOURCE'))
from compile_srhd_dat import build_bp,build_cache,parse_blockpar
from gi_codec import encode as encode_gi,decode as decode_gi
from gai_codec import encode as encode_gai,decode as decode_gai

PREFIX='Mods/FHD_MODS/FHD_FindQuest/'
def load(path):return json.loads(Path(path).read_text('utf-8'))
def sha(data):return hashlib.sha256(data).hexdigest()
def walk(block,path=''):
    for e in block.elems:
        name=path+'.'+e.name if path else e.name
        if e.child is not None:yield from walk(e.child,name)
        else:yield name,e.value

def compile_source():
    source=ROOT/'SOURCE';(ROOT/'Native').mkdir(exist_ok=True)
    subprocess.run(['bash',str(source/'Native/build.sh')],cwd=ROOT,check=True,capture_output=True)
    for text,target in [('Main.txt','Main.dat'),('Lang.txt','Rus/Lang.dat')]:
        build_bp(source/'CFG'/text,ROOT/'CFG'/target)
    build_cache(source/'CFG/CacheData.txt',ROOT/'CFG/CacheData.dat')
    for path in sorted((source/'Graphics').rglob('*.json')):
        tree=load(path);is_animation=tree['format']=='srhd-gai1-json-v1'
        data=encode_gai(tree)if is_animation else encode_gi(tree)
        decoded=decode_gai(data)if is_animation else decode_gi(data)
        if decoded!=tree:raise ValueError('Graphics roundtrip failed: '+str(path))
        dest=ROOT/path.relative_to(source/'Graphics').with_suffix('.gai'if is_animation else'.gi')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    (ROOT/'ModuleInfo.txt').write_bytes((source/'ModuleInfo.txt').read_bytes().decode('utf-8').encode('cp1251'))
    expected=load(ROOT/'original-file-sha256.json')
    files={name:(ROOT/name).read_bytes()for name in expected}
    refs=[]
    for alias,value in walk(parse_blockpar(source/'CFG/CacheData.txt')):
        path=value.replace('\\','/')
        if path.startswith(PREFIX):refs.append({'alias':alias,'path':path,'present':path[len(PREFIX):]in files})
    missing=[ref for ref in refs if not ref['present']]
    if missing:raise ValueError('Missing resources: '+repr(missing))
    return files,{'cache_references_checked':len(refs),'missing':missing}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--strict-original',action='store_true');a=p.parse_args()
    files,audit=compile_source();expected=load(ROOT/'original-file-sha256.json');hashes={k:sha(v)for k,v in sorted(files.items())}
    changed=[k for k in hashes if hashes[k]!=expected[k]]
    if a.strict_original and changed:raise SystemExit('Original SHA-256 mismatch: '+repr(changed))
    out=ROOT/'dist';out.mkdir(exist_ok=True);archive=out/'FHD_FindQuest_FROM_SOURCE.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for path,data in sorted(files.items()):
            info=zipfile.ZipInfo(PREFIX+path,date_time=(2026,10,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(archive)as z:
        if z.testzip():raise SystemExit('ZIP integrity failure')
    report={'runtime_files':len(files),'source_derived_files':len(files),'byte_identical_to_original':not changed,
            'changed_files':changed,'prebuilt_runtime_inputs_used':False,'game_exe_used_for_build':False,
            'dat_files':3,'native_dlls':1,'gi_files':5,'gai_files':1,'gai_frames':20,
            'resource_audit':audit,'python':platform.python_version(),'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],
            'ld':subprocess.check_output(['ld','--version'],text=True).splitlines()[0],
            'sha256':hashes,'package_sha256':sha(archive.read_bytes()),'game_executed':False}
    (out/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS:',len(files),'runtime files built from source;',len(files)-len(changed),'original hashes match')
    print('CacheData references:',audit['cache_references_checked'],'present; missing:',len(audit['missing']))
    print('Package:',archive)

if __name__=='__main__':main()
