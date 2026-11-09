#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
gcc -m32 -std=c11 -O2 -ffreestanding -fno-builtin -fno-stack-protector -fno-asynchronous-unwind-tables -fno-pic -fno-pie -c find_quest.c -o find_quest.o
python3 elf_to_coff.py find_quest.o find_quest.coff
ld -m i386pe --no-leading-underscore --shared --entry DllMain --subsystem console --image-base 0x13000000 --disable-auto-import --no-insert-timestamp find_quest.coff find_quest.def -o ../../Native/FHDFindQuest.dll
