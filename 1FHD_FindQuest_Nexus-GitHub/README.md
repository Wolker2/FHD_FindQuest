# FHD_FindQuest 0.5.2 — source for Nexus Mods review

**Verified on 28 October 2026: all 11 runtime files build from editable source and reproduce the original SHA-256 hashes.** This includes the C DLL, three DATs, five GI images, the 20-frame GAI animation and ModuleInfo.

The source-only build was repeated without any original mod binary or game EXE. `Rangers.exe` from the upload was used separately for compatibility verification and is not redistributed in this project.

## Contents

| Path | Purpose |
| --- | --- |
| `SOURCE/CFG/*.txt` | Original editable Main, Lang and CacheData source |
| `SOURCE/Native/` | Original C source, export definition, build script and ELF-to-COFF tool |
| `SOURCE/compile_srhd_dat.py` | Supplied standard-library DAT compiler |
| `SOURCE/Graphics/*.json` recursively | Lossless GI and GAI sources |
| `SOURCE/gi_codec.py`, `gai_codec.py` | Independent lossless image/animation encoders |
| `SOURCE/ModuleInfo.txt` | UTF-8 metadata, emitted as original CP1251 |
| `SOURCE/verify_*.py` | Retained relevant code/UI/native verification tools |
| `build.py`, `tests/` | Complete build, original hashes and source-only regression checks |
| `original-file-sha256.json`, `build-verification.json` | Reference hashes and completed results |
| `.github/workflows/build.yml` | Automated GitHub build/check workflow |

No game EXE, original runtime binary, duplicate checksum list or historical README is included. No SCR was present, so no RSON recovery is required. The executable mod code is visible in the original C and configuration text sources. Those supplied authoring sources were compiled and verified against the actual release files.

## Build and test

Requirements: Linux, Python 3.10+, GCC with `-m32` object generation, GNU binutils and bash. Node.js is used by regression checks, not the source build. No Python packages, Windows programs or game installation are needed for rebuilding the mod.

```sh
python3 build.py --strict-original
python3 -m unittest discover -s tests -v
```

Outputs: `dist/FHD_FindQuest_FROM_SOURCE.zip` and `dist/build-report.json`. The ZIP installs at `Mods/FHD_MODS/FHD_FindQuest`. For intentional source edits, omit `--strict-original`; differing hashes are listed in the report.

Verified environment: Python 3.12.14, zlib 1.3.2, GCC 13.3.0, GNU ld 2.42 and Node.js 24.22.1. GitHub hosted execution was not performed during preparation.

Four Python tests passed: all eleven hashes/resource references, source-only rebuilding, the existing code/UI/layout regressions, and editable GAI frame pixels/timing. The retained checks cover 69 RScript variable declarations, 16 named buttons, custom-info definitions, scan initialization, standalone namespace isolation, offer ordering/filtering, responsive geometry and pagination. JavaScript adapters exercise extracted script expressions; they are not the game's complete RScript VM.

## Native bridge and supplied EXE compatibility

The module credits **Prolog_D** and declares no dependencies or conflicts. Its DLL exports `FHDFindQuest_Init`, `FHDFindQuest_Probe` and `FHDFindQuest_Reward`. It previews the game's offer logic using the registered player and temporarily substitutes location/context; source code restores player location, RNG and battle-selection counters. Controlled unwind cleanup is visible in C. No executable-code hooks are installed by this module.

The following target was supplied and checked:

| Fingerprint | Value |
| --- | --- |
| EXE SHA-256 | `e43a4b15503c705eebe2d8ce5778c2a2fb090db515a3fd86d319e5c5aa692ebf` |
| EXE file bytes | 4,533,760 |
| PE timestamp | `0x6AC53B97` |
| SizeOfImage | `0x461000` |
| ImageBase | `0x400000` |
| Resource version label | 2.1.2500; this label alone does not identify the build |

The original supplied compatibility notes identify these RVA bindings, also used in source/tests:

| Binding | RVA |
| --- | --- |
| Quest generator | `0x322228` |
| Planetary battle selector | `0x351D90` |
| Registered player accessor | `0x347300` |
| Forced-battle pointer slot | `0x4132D8` |
| Battle-array pointer slot | `0x413B08` |
| RNG state | `0x409008` |
| WideString cleanup | `0x005D18` |

DLL initialization checks the PE fingerprint and three function-byte signatures; the separate verification also checks the full EXE hash. Neither the filename nor the resource-version label is used as a substitute for the fingerprint.

Extended checks were run against the supplied EXE with Unicorn 2.1.4. They verify guarded/relocated DLL initialization, registered-player identity, selected real EXE routines, bridge ABI/results, context/RNG restoration, controlled unwind cleanup and the numeric-identifier recognizer. For reproducibility, the original test tools and `requirements-native-tests.txt` are included:

```sh
python3 SOURCE/verify_release.py /path/to/the/matching/Rangers.exe
python3 SOURCE/verify_native.py /path/to/the/matching/Rangers.exe
python3 SOURCE/verify_script_identifiers.py /path/to/the/matching/Rangers.exe
```

These optional checks require a separately available matching EXE; it is not a build dependency. Full quest generation, the actual battle selector and Windows RtlUnwind are controlled substitutes in parts of the emulator tests. No Windows game session or complete paired-mod runtime test was performed.

## Graphics and provenance

The five GI sources retain explicit headers, geometry, RGB565 colors, alpha and RLE packets. `GNPoQ.json` additionally contains all 20 editable frame trees and the named sequence table with frame indices/delays. The original sequence uses 50 ms delays. Frame tables, offsets and auxiliary timing data are generated from these fields; no original GI/GAI blob is a build input.

The original C, `.def`, build tools and configuration texts were supplied in the archive. Only a C comment's documentation pointer was updated to this README; the resulting DLL remains byte-identical. Graphical source recovery and packaging automation were added during preparation. Existing author credits and licensing are not changed.

GAI sequence handling was checked against the supplied [SpaceRangersHD_decomp](https://github.com/pakompom/SpaceRangersHD_decomp) `EC_CacheGAI.pas`; image structure was checked with the supplied [SRHD-XenoModKit](https://github.com/Xenomorphchyma/SRHD-XenoModKit). The independent GI codec and the bundled DAT compiler require no external editor binaries.

Input ZIP SHA-256: `04ca017dcab11d6dde627d46339d9a4ddad29f591d7fad33b31232ed7a421b81`. Its integrity checks passed. Source reproduction and emulator results do not establish live gameplay correctness, antivirus status or Nexus moderation approval.
