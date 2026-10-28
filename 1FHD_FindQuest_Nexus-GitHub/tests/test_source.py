from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile,unittest,zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from build import compile_source,load,PREFIX
from gai_codec import encode as encode_gai,decode as decode_gai

class SourceTests(unittest.TestCase):
    def test_all_original_hashes_and_resource_references(self):
        files,audit=compile_source();expected=load(ROOT/'original-file-sha256.json')
        self.assertEqual({k:hashlib.sha256(v).hexdigest()for k,v in files.items()},expected)
        self.assertEqual(len(files),11)
        self.assertEqual(audit,{'cache_references_checked':5,'missing':[]})

    def test_gai_frame_pixels_and_timing_are_editable(self):
        path=ROOT/'SOURCE/Graphics/Data/Image/GNPoQ.json';tree=load(path)
        self.assertEqual(len(tree['frames']),20)
        self.assertEqual(len(tree['sequences'][0]['steps']),20)
        tree['sequences'][0]['steps'][0]['delay_ms']=51
        packet=next(c for layer in tree['frames'][0]['layers']for c in layer['commands']if 'pixels'in c)
        packet['pixels'][0]^=1
        rebuilt=encode_gai(tree)
        self.assertEqual(decode_gai(rebuilt),tree)
        self.assertNotEqual(hashlib.sha256(rebuilt).hexdigest(),load(ROOT/'original-file-sha256.json')['Data/Image/GNPoQ.gai'])

    def test_existing_code_ui_and_layout_regressions(self):
        compile_source()
        for script in ['verify_script_identifiers.py','verify_ui.py','verify_isolation.py','verify_offers.py','verify_layout.py']:
            result=subprocess.run([sys.executable,str(ROOT/'SOURCE'/script)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,script+'\n'+result.stdout+result.stderr)

    def test_complete_build_without_mod_binaries_or_game_exe(self):
        with tempfile.TemporaryDirectory()as folder:
            target=Path(folder)
            shutil.copytree(ROOT/'SOURCE',target/'SOURCE',ignore=shutil.ignore_patterns('*.o','*.coff','__pycache__'))
            for name in ['build.py','original-file-sha256.json']:shutil.copy2(ROOT/name,target/name)
            self.assertFalse(any(p.suffix.lower()in('.exe','.dll','.gi','.gai','.dat','.o','.coff')for p in target.rglob('*')if p.is_file()))
            result=subprocess.run([sys.executable,str(target/'build.py'),'--strict-original'],cwd=target,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            expected=load(ROOT/'original-file-sha256.json')
            with zipfile.ZipFile(target/'dist/FHD_FindQuest_FROM_SOURCE.zip')as z:
                self.assertIsNone(z.testzip());self.assertEqual(len(z.namelist()),11)
                for name,digest in expected.items():self.assertEqual(hashlib.sha256(z.read(PREFIX+name)).hexdigest(),digest)

if __name__=='__main__':unittest.main()
