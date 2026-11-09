#!/usr/bin/env python3
"""Check native Ship outside-click exclusions after merging compiled DAT.

This is a configuration regression, not execution of the Windows renderer.
TfShip2.MainLeftButtonUp checks immediate children of TestHitPanels before
CloseClicked; GraphButton queues OnPressCode after the parent's callback.
"""
from copy import deepcopy
from pathlib import Path
from compile_srhd_dat import parse_bp_raw, unpack_dat_bytes
from verify_compatibility import merge, fields
from verify_isolation import descend, named


def run(root):
    compiled = parse_bp_raw(unpack_dat_bytes((root/'CFG/Main.dat').read_bytes(), 0xb1e8c689))
    overlay = descend(compiled, 'ML', 'Ship')
    vanilla = parse_bp_raw((root/'SOURCE/fixtures/vanilla_ship.raw').read_bytes())
    merged = merge(vanilla, overlay)
    main = named(merged, 'MainPanel')
    control = named(main, 'FHDFindQuestShipControl')
    button = named(control, 'FHDFindQuestShipButton')
    hit_parent = named(main, 'TestHitPanels')

    # Named grouping blocks are flattened by TObjectGI.LoadConfiguredChildren.
    def immediate_panels(block):
        for e in block.elems:
            if e.child is None:
                continue
            if e.name == 'Panel':
                yield e.child
            else:
                yield from immediate_panels(e.child)

    exclusions = list(immediate_panels(hit_parent))
    hit = next(p for p in exclusions if fields(p).get('Name') == 'FHDFindQuestShipHit')
    assert fields(hit)['Active'] == 'True'
    assert fields(hit)['MouseBlocking'] == fields(hit)['MouseBlockingTest'] == 'False'
    assert fields(button)['Kind'] == 'Normal' and fields(button)['MouseBlocking'] == 'True'
    assert fields(control)['Pos'] == '427,741,-150'
    assert fields(hit)['Pos'] == '427,741,0'
    assert fields(button)['Pos'] == '0,0,-1'
    assert descend(button, 'OnPressCode') == descend(named(descend(compiled, 'ML', 'StarMap'), 'FHDFindQuestButton'), 'OnPressCode')

    for panel in (control, hit):
        f = fields(panel)
        assert f['Size'] == '20,20'
        assert (f['PosAutoCorrection'], f['PosAutoCorrectionXCoef'], f['PosAutoCorrectionYCoef']) == ('True', '1', '1')
    assert fields(hit_parent).get('Pos', '0,0') == '0,0'
    for width, height in [(1024,768), (1280,720), (1366,768), (1920,1080), (2560,1440), (3440,1440), (3840,2160)]:
        x, y = 427+width-1024, 741+height-768
        # Every clickable pixel must survive native MainLeftButtonUp.
        def native_exclusion(px, py):
            return x <= px < x+20 and y <= py < y+20
        assert all(native_exclusion(x+dx, y+dy) for dx in range(20) for dy in range(20))
        assert not native_exclusion(x-1, y) and not native_exclusion(x+20, y)
        assert not native_exclusion(x, y-1) and not native_exclusion(x, y+20)
        assert x+50 == 477+width-1024 and y+20 <= height

    # Remove only our named additions: all original Ship definitions remain.
    preserved = deepcopy(merged)
    named(preserved, 'MainPanel').elems = [e for e in named(preserved, 'MainPanel').elems if e.name != 'FHDFindQuestShipControl']
    old_hits = named(preserved, 'TestHitPanels')
    old_hits.elems = [e for e in old_hits.elems if e.name != 'FHDFindQuestShipHit']
    assert preserved == vanilla
    print('PASS: native Ship exclusion contains the whole button at 7 resolutions; exact 50 px shift; vanilla controls preserved')


if __name__ == '__main__':
    run(Path(__file__).resolve().parent.parent)
