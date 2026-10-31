#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Builds a test program from programs/<name>/ into a raw blob linked at a known address.
#
# Usage: build-program.sh <name> [<toolchain-bin-dir>] [<out-dir>]
#   <name>               colour-loop (the hardware program) or selftest (C codegen check)
#   <toolchain-bin-dir>  directory holding clang, llvm-objcopy and llvm-objdump; default is the
#                        install prefix build-toolchain.sh produces. Pass /usr/bin to use
#                        a distro LLVM instead (see SPIKE-S3 for why that is a comparison
#                        only and not the supported toolchain).
#   LD                   the m68k linker, default m68k-linux-gnu-ld from binutils. lld cannot
#                        be used: it has no M68k backend (SPIKE-S3 section 4).
#   LOAD_ADDR            link address, default 0x40000 (chip RAM, above anything a booting
#                        machine places low). CFLAGS_EXTRA adds compiler flags, e.g.
#                        -DDELAY_OUTER=1 for a short-period build.
#
# Produces <out-dir>/<name>.{elf,bin,lst}. The .bin is the bytes at LOAD_ADDR onward.
# For colour-loop it also wraps the blob in a boot block (colour-loop.bootblock and
# colour-loop.adf) for the real-hardware run; the .adf is a build product and is git-ignored (ADR-ROM-03 D1 keeps
# disk images out of the tree, and this one is generated, not committed).

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
name=${1:?usage: build-program.sh <name> [<toolchain-bin-dir>] [<out-dir>]}
bin=${2:-$work/install/bin}
out=${3:-$here/out}
load=${LOAD_ADDR:-0x40000}
src=$here/programs/$name

# LLVM 18 names its tools with a version suffix on some distros; accept either.
pick() { for n in "$@"; do [ -x "$bin/$n" ] && { echo "$bin/$n"; return; }; done
         echo "missing $1 in $bin" >&2; exit 1; }
cc=$(pick clang clang-18)
oc=$(pick llvm-objcopy llvm-objcopy-18)
od=$(pick llvm-objdump llvm-objdump-18)

mkdir -p "$out"
cflags=(--target=m68k -mcpu=M68000 "${OPT:--Os}" -ffreestanding -fno-pic
        -fno-asynchronous-unwind-tables -fno-stack-protector -Wall -Wextra -Werror)
asflags=(--target=m68k -mcpu=M68000)

objs=()
for f in "$src"/*.c; do
  o=$out/$(basename "${f%.c}").o
  # shellcheck disable=SC2086
  "$cc" "${cflags[@]}" ${CFLAGS_EXTRA:-} -c "$f" -o "$o"; objs+=("$o")
done
for f in "$src"/*.s; do
  o=$out/$(basename "${f%.s}").s.o
  "$cc" "${asflags[@]}" -c "$f" -o "$o"; objs+=("$o")
done
# start.s holds the entry point, so it goes first; the rest follow in a fixed order.
start=$out/start.s.o
rest=(); for o in "${objs[@]}"; do [ "$o" = "$start" ] || rest+=("$o"); done

"${LD:-m68k-linux-gnu-ld}" --defsym=LOAD_ADDR="$load" -T "$here/link.ld" -e _start \
      -z noexecstack -o "$out/$name.elf" "$start" "${rest[@]}"
"$oc" -O binary "$out/$name.elf" "$out/$name.bin"
"$od" -d -r "$out/$name.elf" > "$out/$name.lst"

if [ "$name" = colour-loop ]; then
  # The boot block is position independent and carries the blob after its copy loop.
  "$cc" "${asflags[@]}" -DBLOB="\"$out/$name.bin\"" -DLOAD_ADDR="$load" \
        -c "$here/bootblock/bootblock.S" -o "$out/bootblock.o"
  "$oc" -O binary -j .text "$out/bootblock.o" "$out/bootblock.bin"
  python3 "$here/bootblock/mkbootblock.py" "$out/bootblock.bin" "$out/$name.bootblock"
  python3 "$here/bootblock/mkbootblock.py" "$out/bootblock.bin" "$out/$name.adf" --adf
fi
printf 'blob: %s  %s bytes at %s\n' "$out/$name.bin" "$(stat -c %s "$out/$name.bin")" "$load"
