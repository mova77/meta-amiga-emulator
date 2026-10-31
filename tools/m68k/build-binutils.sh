#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Builds the pinned GNU binutils for the 68000 (m68k-linux-gnu-as, -ld, -objcopy, -objdump,
# -nm, -readelf) into an install prefix, entirely outside the source tree. It is for a
# distribution that does not package binutils for m68k at the pinned version; where one does
# (Ubuntu 24.04: binutils-m68k-linux-gnu), installing the package is cheaper and enough, and
# oracle 1 (check.sh) is what decides whether a given build is acceptable. Build-time tool
# only: nothing here is linked into the emulator (docs/spikes/SPIKE-S3-m68k-toolchain.md
# section 10).
#
# Usage: build-binutils.sh [--keep-build] [<prefix>]
#   <prefix>        install prefix; default $XDG_CACHE_HOME/meta-amiga/binutils-m68k/install
#   BINUTILS_WORK   overrides the work directory that holds the download and the build tree.
#
# It builds the release tarball named in toolchain.pin, checked against its SHA-256. The
# tarball, not a git checkout of the tag: a checkout lacks the generated lexer and parser
# sources and would need flex as well. This needs only gcc, make, xz and curl. Measured cost
# is in SPIKE-S3 section 5.

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=toolchain.pin
. "$here/toolchain.pin"

keep_build=0
if [ "${1:-}" = "--keep-build" ]; then keep_build=1; shift; fi

work=${BINUTILS_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/binutils-m68k}
prefix=${1:-$work/install}
src=$work/binutils-$BINUTILS_VERSION
bld=$work/build
jobs=${M68K_JOBS:-$(nproc)}

mkdir -p "$work"
start=$(date +%s)
stamp() { echo "$1: $(( $(date +%s) - start )) s since start"; }
fail() { echo "$1 failed; last lines of $2:" >&2; tail -30 "$2" >&2; exit 1; }

tarball=$work/binutils-$BINUTILS_VERSION.tar.xz
if [ ! -f "$tarball" ]; then
  curl -fsSL -o "$tarball.part" "$BINUTILS_URL" && mv "$tarball.part" "$tarball"
fi
echo "$BINUTILS_SHA256  $tarball" | sha256sum -c --quiet - \
  || { echo "$tarball does not match the SHA-256 in toolchain.pin" >&2; exit 1; }
stamp download
rm -rf "$src"; mkdir -p "$src"
tar -C "$src" --strip-components=1 -xf "$tarball"
stamp unpack

rm -rf "$bld"; mkdir -p "$bld"
# Only what a bare-metal 68000 flow uses. No gdb, simulators, profilers, gold, plugins,
# translations or documentation: they are the bulk of the tree and none is used here.
( cd "$bld" && "$src/configure" --target=m68k-linux-gnu --prefix="$prefix" \
    --disable-nls --disable-werror --disable-gdb --disable-gdbserver --disable-sim \
    --disable-gprof --disable-gprofng --disable-gold --disable-plugins --disable-multilib \
    --disable-libbacktrace --disable-readline --without-zstd --without-debuginfod \
    >"$work/configure.log" 2>&1 ) || fail configure "$work/configure.log"
stamp configure
make -C "$bld" -j "$jobs" MAKEINFO=true all-binutils all-gas all-ld \
  >"$work/build.log" 2>&1 || fail make "$work/build.log"
stamp compile
make -C "$bld" MAKEINFO=true install-strip-binutils install-strip-gas install-strip-ld \
  >"$work/install.log" 2>&1 || fail install "$work/install.log"
"$prefix/bin/m68k-linux-gnu-as" --version | head -1 | sed 's/^/built: /'
"$prefix/bin/m68k-linux-gnu-ld" --version | head -1 | sed 's/^/built: /'
[ "$keep_build" = 1 ] || rm -rf "$bld" "$src" "$tarball"
echo "wall: $(( $(date +%s) - start )) s"
