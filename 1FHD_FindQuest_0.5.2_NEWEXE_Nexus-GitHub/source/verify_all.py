#!/usr/bin/env python3
"""Build and verify this release. Usage: verify_all.py RANGERS_EXE"""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent.parent
exe=Path(sys.argv[1]).resolve()
subprocess.run(['bash',str(root/'SOURCE/Native/build.sh')],check=True)
for script,args in [
    ('build_dat.py',[]),
    ('verify_release.py',[str(exe)]),
    ('verify_native.py',[str(exe)]),
    ('verify_script_identifiers.py',[str(exe)]),
    ('verify_button_anchor.py',[str(exe)]),
    ('verify_reset.py',[]),
]:
    print('\nVERIFY:',script,flush=True)
    subprocess.run([sys.executable,'-B',str(root/'SOURCE'/script),*args],check=True)
print('\nPASS: release checks complete (emulation/configuration; no Windows gameplay run)')
