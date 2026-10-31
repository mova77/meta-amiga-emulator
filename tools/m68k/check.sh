#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Runs the toolchain's correctness oracles against an installed toolchain.
#
#   oracle 1  encodings against the manual, backend assembler and disassembler
#             (oracle/check_encodings.py). Needs only the toolchain.
#   oracle 3  the built programs run under an independent 68000 CPU model
#             (oracle/observe_blob.py). Needs `pip install unicorn`; skipped, loudly,
#             when it is absent. It is an observation instrument, run as a black box.
#
# Usage: check.sh [<toolchain-bin-dir>]      exit 0 all ran and passed, 1 a failure,
#                                            77 oracle 3 could not run (CTest skip code)
#
# Oracle 2, the product owner's real PAL A500, cannot be scripted: SPIKE-S3 section 8 has
# the steps for it.

set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
bin=${1:-$work/install/bin}
out=${OUT:-$here/out}
py=${PYTHON:-python3}
fail=0

echo "== oracle 1: encodings"
"$py" -I "$here/oracle/check_encodings.py" --bin "$bin" --out "$out" || fail=1

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
