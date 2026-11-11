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
#   oracle 2 stand-in
#             colour-loop.adf boots in an existing Amiga emulator and its colour period is
#             read off the screen (oracle/boot_colour_loop.sh). Needs FS-UAE, Xvfb and ffmpeg;
#             skipped, loudly, when any is absent. Also an observation instrument, run as a
#             black box. The ROM is FS-UAE's built-in AROS unless KICKSTART names your own.
#
# Usage: check.sh [<llvm-bin-dir> [<binutils-bin-dir>]]
#   <llvm-bin-dir>      directory holding clang; default is build-toolchain.sh's install prefix
#   <binutils-bin-dir>  directory holding m68k-linux-gnu-as, -ld, -objcopy, -objdump, -nm;
#                       default is to find them on PATH (BINUTILS_BIN also sets it)
# Exit 0 all ran and passed, 1 a failure, 77 nothing failed but oracle 3 or the oracle 2
# stand-in could not run (CTest skip code).
#
# Oracle 2 proper, a real PAL A500, cannot be scripted: SPIKE-S3 section 8 has the steps for it.

set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
bin=${1:-$work/install/bin}
export BINUTILS_BIN=${2:-${BINUTILS_BIN:-}}
out=${OUT:-$here/out}
py=${PYTHON:-python3}
fail=0
skip=0

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
  skip=1
else
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
fi

echo "== oracle 2 stand-in: boot colour-loop.adf in an existing emulator, read the colour period"
"$here/oracle/boot_colour_loop.sh" "$out/colour-loop/colour-loop.adf" "$out/colour-loop/boot"
case $? in
  0) ;;
  77) skip=1 ;;
  *) fail=1 ;;
esac

if [ "$fail" != 0 ]; then echo "FAILURES"; exit 1; fi
if [ "$skip" != 0 ]; then echo "PASS, WITH SKIPS"; exit 77; fi
echo "ALL PASS"
exit 0
