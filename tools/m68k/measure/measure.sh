#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# The numbers behind SPIKE-S3 section 9: how much hand-written 68000 the C toolchain
# removes. Counts lines of code (no comments, no blanks) and instructions.
#
# Usage: measure.sh [<llvm-bin-dir> [<binutils-bin-dir>]]     (as for check.sh)

set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
m68k=$(dirname "$here")
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
bin=${1:-$work/install/bin}
export BINUTILS_BIN=${2:-${BINUTILS_BIN:-}}
out=${OUT:-$m68k/out/measure}
mkdir -p "$out"
gnu() { if [ -n "$BINUTILS_BIN" ]; then echo "$BINUTILS_BIN/m68k-linux-gnu-$1"; else command -v "m68k-linux-gnu-$1"; fi; }
as=$(gnu as); oc=$(gnu objcopy); od=$(gnu objdump)

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
# Instructions in an ELF's code from GNU objdump: a line with an address and a mnemonic.
# Alignment padding prints as "..." and is not counted.
insns() { "$od" -d --no-show-raw-insn "$1" | grep -cE '^\s+[0-9a-f]+:\s+[a-z]'; }

p=$m68k/programs
echo "== colour-loop"
"$m68k/build-program.sh" colour-loop "$bin" "$out/cl" >/dev/null
echo "C + assembly : $(loc "$p"/colour-loop/main.c) C lines, $(loc "$p"/colour-loop/start.s "$p"/colour-loop/delay.s) assembly lines"
"$as" -m68000 -o "$out/asm-only.o" "$here/colour-loop-asm-only.s"
echo "assembly only: 0 C lines, $(loc "$here/colour-loop-asm-only.s") assembly lines"
"$oc" -O binary -j .text "$out/asm-only.o" "$out/asm-only.bin"
echo "blob bytes   : C + assembly $(stat -c %s "$out/cl/colour-loop.bin"), assembly only $(stat -c %s "$out/asm-only.bin")"

echo "== selftest (what the compiler writes for you)"
for o in -Os -O2; do
  OPT=$o "$m68k/build-program.sh" selftest "$bin" "$out/st$o" >/dev/null
  echo "$o: $(loc "$p"/selftest/selftest.c) C lines -> $(insns "$out/st$o/selftest.elf") instructions, $(stat -c %s "$out/st$o/selftest.bin") bytes"
done
