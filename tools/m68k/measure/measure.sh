#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# The numbers behind SPIKE-S3 section 9: how much hand-written 68000 the C toolchain
# removes. Counts lines of code (no comments, no blanks) and instructions.
#
# Usage: measure.sh [<toolchain-bin-dir>]

set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
m68k=$(dirname "$here")
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
bin=${1:-$work/install/bin}
out=${OUT:-$m68k/out/measure}
mkdir -p "$out"

# Lines of code: strip /* ... */ spans (single or multi line) and // comments, drop blanks.
loc() { python3 -I - "$@" <<'PY'
import re, sys
n = 0
for path in sys.argv[1:]:
    text = re.sub(r"/\*.*?\*/", "", open(path).read(), flags=re.S)
    n += sum(1 for l in text.splitlines() if l.strip() and not l.strip().startswith("//"))
print(n)
PY
}
# Instructions in an ELF's .text from the disassembler. Alignment padding prints as
# <unknown> and is not counted.
insns() { "$bin/llvm-objdump" -d --no-show-raw-insn "$1" | grep -E '^\s+[0-9a-f]+:' | grep -vc unknown; }

p=$m68k/programs
echo "== colour-loop"
"$m68k/build-program.sh" colour-loop "$bin" "$out/cl" >/dev/null
echo "C + assembly : $(loc "$p"/colour-loop/main.c) C lines, $(loc "$p"/colour-loop/start.s "$p"/colour-loop/delay.s) assembly lines"
"$bin/clang" --target=m68k -mcpu=M68000 -c "$here/colour-loop-asm-only.s" -o "$out/asm-only.o"
echo "assembly only: 0 C lines, $(loc "$here/colour-loop-asm-only.s") assembly lines"
"$bin/llvm-objcopy" -O binary -j .text "$out/asm-only.o" "$out/asm-only.bin"
echo "blob bytes   : C + assembly $(stat -c %s "$out/cl/colour-loop.bin"), assembly only $(stat -c %s "$out/asm-only.bin")"

echo "== selftest (what the compiler writes for you)"
for o in -Os -O2; do
  OPT=$o "$m68k/build-program.sh" selftest "$bin" "$out/st$o" >/dev/null
  echo "$o: $(loc "$p"/selftest/selftest.c) C lines -> $(insns "$out/st$o/selftest.elf") instructions, $(stat -c %s "$out/st$o/selftest.bin") bytes"
done
