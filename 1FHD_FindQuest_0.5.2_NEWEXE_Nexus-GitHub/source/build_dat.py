#!/usr/bin/env python3
"""Build mod DAT files with the bundled BlockPar compiler."""
from pathlib import Path
from compile_srhd_dat import build_bp, build_cache, unpack_dat_bytes, parse_bp_raw
root=Path(__file__).resolve().parent.parent
build_bp(root/'SOURCE/CFG/Main.txt',root/'CFG/Main.dat')
build_bp(root/'SOURCE/CFG/Lang.txt',root/'CFG/Rus/Lang.dat')
build_cache(root/'SOURCE/CFG/CacheData.txt',root/'CFG/CacheData.dat')
for p in [root/'CFG/Main.dat',root/'CFG/Rus/Lang.dat']:
    tree=parse_bp_raw(unpack_dat_bytes(p.read_bytes(),0xB1E8C689))
    print(p.relative_to(root),[e.name for e in tree.elems])
from verify_script_identifiers import run as verify_script_identifiers
verify_script_identifiers(root)
from verify_ui import run
if run(root):
    raise SystemExit('Invalid button caption/font configuration')
from verify_isolation import run as verify_isolation
if verify_isolation(root):
    raise SystemExit('FindQuest must not modify QuestMarker')
from verify_offers import run as verify_offers
verify_offers(root)
from verify_layout import run as verify_layout
verify_layout(root)
