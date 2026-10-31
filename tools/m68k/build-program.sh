#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Builds a test program from programs/<name>/ into a raw blob linked at a known address.
# C goes through clang; hand-written assembly (.s) goes through GNU as, and GNU ld links.
# The LLVM M68k assembler is not used: it lacks DBcc, ADDQ, SUBQ, TST, CLR, SWAP and STOP and
# mis-encodes MOVE to SR (SPIKE-S3 section 4), and lld has no M68k backend.
#
# Usage: build-program.sh <name> [<llvm-bin-dir>] [<out-dir>]
#   <name>          colour-loop (the hardware program) or selftest (C codegen check)
#   <llvm-bin-dir>  directory holding clang; default is the install prefix build-toolchain.sh
#                   produces. Pass /usr/bin to use a distro clang, which compiles this C
#                   correctly but is not the pinned compiler (SPIKE-S3 section 3).
#   BINUTILS_BIN    directory holding m68k-linux-gnu-as, -ld, -objcopy and -objdump; default
#                   is to find them on PATH (Ubuntu: apt install binutils-m68k-linux-gnu;
#                   otherwise build-binutils.sh).
#   LOAD_ADDR       link address, default 0x40000 (chip RAM, above anything a booting
#                   machine places low). CFLAGS_EXTRA adds compiler flags, e.g.
#                   -DDELAY_OUTER=1 for a short-period build.
#
# Produces <out-dir>/<name>.{elf,bin,lst}. The .bin is the bytes at LOAD_ADDR onward.
# For colour-loop it also wraps the blob in a boot block (colour-loop.bootblock and
# colour-loop.adf) for the real-hardware run; the .adf is a build product and is git-ignored
# (ADR-ROM-03 D1 keeps disk images out of the tree, and this one is generated, not committed).

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
name=${1:?usage: build-program.sh <name> [<llvm-bin-dir>] [<out-dir>]}
bin=${2:-$work/install/bin}
out=${3:-$here/out}
load=${LOAD_ADDR:-0x40000}
src=$here/programs/$name

# clang names itself with a version suffix on some distros; accept either.
cc=; for n in clang clang-18; do [ -x "$bin/$n" ] && { cc=$bin/$n; break; }; done
[ -n "$cc" ] || { echo "no clang in $bin" >&2; exit 1; }
gnu() {
  local n=m68k-linux-gnu-$1
  if [ -n "${BINUTILS_BIN:-}" ]; then [ -x "$BINUTILS_BIN/$n" ] && { echo "$BINUTILS_BIN/$n"; return; }
  elif command -v "$n" >/dev/null; then command -v "$n"; return; fi
  echo "missing $n (set BINUTILS_BIN, install binutils-m68k-linux-gnu or run build-binutils.sh)" >&2
  exit 1
}
as=$(gnu as); ld=$(gnu ld); oc=$(gnu objcopy); od=$(gnu objdump)

mkdir -p "$out"
cflags=(--target=m68k -mcpu=M68000 "${OPT:--Os}" -ffreestanding -fno-pic
        -fno-asynchronous-unwind-tables -fno-stack-protector -Wall -Wextra -Werror)

objs=()
for f in "$src"/*.c; do
  o=$out/$(basename "${f%.c}").o
  # shellcheck disable=SC2086
  "$cc" "${cflags[@]}" ${CFLAGS_EXTRA:-} -c "$f" -o "$o"; objs+=("$o")
done
for f in "$src"/*.s; do
  o=$out/$(basename "${f%.s}").s.o
  "$as" -m68000 -o "$o" "$f"; objs+=("$o")
done
# start.s holds the entry point, so it goes first; the rest follow in a fixed order.
start=$out/start.s.o
rest=(); for o in "${objs[@]}"; do [ "$o" = "$start" ] || rest+=("$o"); done

"$ld" --defsym=LOAD_ADDR="$load" -T "$here/link.ld" -e _start \
      -z noexecstack -o "$out/$name.elf" "$start" "${rest[@]}"
"$oc" -O binary "$out/$name.elf" "$out/$name.bin"
"$od" -d -r "$out/$name.elf" > "$out/$name.lst"

if [ "$name" = colour-loop ]; then
  # The boot block is position independent: the stub copies the blob that follows it to the
  # link address, so it needs the blob's length in words and the address, both as symbols.
  words=$(( ($(stat -c %s "$out/$name.bin") + 1) / 2 ))
  "$as" -m68000 --defsym LOAD_ADDR="$load" --defsym BLOB_WORDS="$words" \
        -o "$out/bootblock.o" "$here/bootblock/bootblock.s"
  "$oc" -O binary -j .text "$out/bootblock.o" "$out/bootblock.stub"
  cat "$out/bootblock.stub" "$out/$name.bin" > "$out/bootblock.bin"
  python3 "$here/bootblock/mkbootblock.py" "$out/bootblock.bin" "$out/$name.bootblock"
  python3 "$here/bootblock/mkbootblock.py" "$out/bootblock.bin" "$out/$name.adf" --adf
fi
printf 'blob: %s  %s bytes at %s\n' "$out/$name.bin" "$(stat -c %s "$out/$name.bin")" "$load"
