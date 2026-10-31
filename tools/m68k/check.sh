#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Runs the toolchain's correctness oracles against the installed tools: clang (the C compiler)
# and GNU binutils (assembler, linker, objcopy, objdump), both pinned in toolchain.pin.
#
#   oracle 1  assembled bytes against the manual (oracle/check_encodings.py). GNU as is the
#             gate; the LLVM assembler and disassembler are measured beside it and recorded.
#   oracle 3  the built programs run under an independent 68000 CPU model
#             (oracle/observe_blob.py). Needs `pip install unicorn`; skipped, loudly,
#             when it is absent. It is an observation instrument, run as a black box.
#
# Usage: check.sh [<llvm-bin-dir> [<binutils-bin-dir>]]
#   <llvm-bin-dir>      directory holding clang; default is build-toolchain.sh's install prefix
#   <binutils-bin-dir>  directory holding m68k-linux-gnu-as, -ld, -objcopy, -objdump, -nm;
#                       default is to find them on PATH (BINUTILS_BIN also sets it)
# Exit 0 all ran and passed, 1 a failure, 77 oracle 3 could not run (CTest skip code).
#
# Oracle 2, a real PAL A500, cannot be scripted: SPIKE-S3 section 8 has the steps for it.

set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
bin=${1:-$work/install/bin}
export BINUTILS_BIN=${2:-${BINUTILS_BIN:-}}
out=${OUT:-$here/out}
py=${PYTHON:-python3}
fail=0

echo "== oracle 1: encodings"
"$py" -I "$here/oracle/check_encodings.py" --bin "$bin" --out "$out" \
  ${BINUTILS_BIN:+--binutils "$BINUTILS_BIN"} || fail=1

echo "== build"
"$here/build-program.sh" colour-loop "$bin" "$out/colour-loop" || fail=1
for o in Os O2; do
  OPT=-$o "$here/build-program.sh" selftest "$bin" "$out/selftest-$o" || fail=1
done

echo "== oracle 3: black-box CPU model"
if ! "$py" -I -c 'import unicorn' 2>/dev/null; then
  echo "SKIP: the 'unicorn' package is not installed (pip install unicorn)"
  [ "$fail" = 0 ] && exit 77 || exit 1
fi
obs=("$py" -I "$here/oracle/observe_blob.py")
echo "-- kernel"
"${obs[@]}" kernel "$out/kernel.bin" 0x1000 --syms "$out/kernel.syms" || fail=1
for o in Os O2; do
  echo "-- selftest -$o"
  "${obs[@]}" selftest "$out/selftest-$o/selftest.bin" 0x40000 || fail=1
done
echo "-- colour-loop"
"${obs[@]}" colour-loop "$out/colour-loop/colour-loop.bin" 0x40000 || fail=1
echo "-- colour-loop via its boot block"
"${obs[@]}" colour-loop "$out/colour-loop/colour-loop.bin" 0x40000 \
  --bootblock "$out/colour-loop/colour-loop.bootblock" || fail=1

[ "$fail" = 0 ] && echo "ALL PASS" || echo "FAILURES"
exit "$fail"
