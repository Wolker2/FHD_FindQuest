#!/usr/bin/env python3
"""Check the compiled UI for the empty-font crash seen on Galaxy.

Rangers 2.1.2500 creates a label whenever a GraphButton has a Caption
parameter, even when its value is empty. Such a label needs a Font.
This checks compiled DAT, rather than searching source text.
"""
from pathlib import Path
import re
import sys

from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes


def inspect(block, path=""):
    failures = []
    count = 0
    for element in block.elems:
        if element.child is None:
            continue
        child = element.child
        fields = {item.name: item.value for item in child.elems if item.child is None}
        location = path + "/" + element.name
        if fields.get("Name"):
            location += "[" + fields["Name"] + "]"
        if element.name == "GraphButton" and fields.get("Name"):
            count += 1
            if "Caption" in fields and not fields.get("Font"):
                failures.append(location + ": Caption creates a label without Font")
        found, subtotal = inspect(child, location)
        failures.extend(found)
        count += subtotal
    return failures, count


def run(root):
    tree = parse_bp_raw(unpack_dat_bytes((root / "CFG/Main.dat").read_bytes(), 0xB1E8C689))
    failures, count = inspect(tree)
    lang = parse_bp_raw(unpack_dat_bytes((root / "CFG/Rus/Lang.dat").read_bytes(), 0xB1E8C689))
    def descend(block, parts):
        for part in parts:
            hit = next((e.child for e in block.elems if e.name == part and e.child is not None), None)
            if hit is None:
                return None
            block = hit
        return block
    def script_values(block):
        for e in block.elems:
            if e.child is None:
                yield e.value or ""
            else:
                yield from script_values(e.child)
    script = descend(lang, ["Script"])
    referenced = set()
    for value in script_values(script):
        referenced.update(re.findall(r"ShipAddCustomShipInfo\([^,]+,\s*'([^']+)'", value))
    for name in referenced:
        if descend(lang, ["ShipInfo", "AddInfo", "CustomInfos", name]) is None:
            failures.append("ShipInfo.AddInfo.CustomInfos." + name + ": missing definition used by ShipAddCustomShipInfo")
    open_code = descend(lang, ["Script", "FHDFindQuest", "Open"])
    open_text = "".join(script_values(open_code))
    if "ImportedFunction('FHDFindQuestNative','Init')" not in open_text or "initResult==0 && s<GalaxyStars()" not in open_text:
        failures.append("FHDFindQuest.Open: native initialization must be confirmed before probing planets")
    if failures:
        print("FAIL: " + "\nFAIL: ".join(failures))
        return 1
    print(f"PASS: {count} named compiled buttons have no caption without a font")
    print(f"PASS: {len(referenced)} custom ship info types have compiled Lang definitions")
    print("PASS: planet scan checks native initialization")
    return 0


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
    raise SystemExit(run(root))
