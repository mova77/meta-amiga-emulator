#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Builds the pinned Clang and LLVM binutils with the experimental M68k backend into an
# install prefix, entirely outside the source tree. It is a build-time tool only: nothing here is
# linked into the emulator (docs/spikes/SPIKE-S3-m68k-toolchain.md section 10).
#
# Usage: build-toolchain.sh [--keep-build] [<prefix>]
#   <prefix>  install prefix; default $XDG_CACHE_HOME/meta-amiga/llvm-m68k/install
#   M68K_WORK overrides the work directory that holds the clone and the build tree.
#
# The shallow, sparse clone fetches only the directories this configuration builds, so the
# download and checkout are a fraction of the full tree. --keep-build skips deleting the
# clone and the build tree afterwards. Measured cost is in SPIKE-S3 section 5.
#
# lld is deliberately not built: it has no M68k backend (SPIKE-S3 section 4), so it would
# cost build time and ship a linker that cannot link the one target we build for. Linking
# is done by binutils' m68k ld (see build-program.sh).

set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=toolchain.pin
. "$here/toolchain.pin"

keep_build=0
if [ "${1:-}" = "--keep-build" ]; then keep_build=1; shift; fi

work=${M68K_WORK:-${XDG_CACHE_HOME:-$HOME/.cache}/meta-amiga/llvm-m68k}
prefix=${1:-$work/install}
src=$work/llvm-project
bld=$work/build
jobs=${M68K_JOBS:-$(nproc)}

mkdir -p "$work"
start=$(date +%s)

if [ ! -d "$src/.git" ]; then
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch "$LLVM_TAG" \
    https://github.com/llvm/llvm-project.git "$src"
  git -C "$src" sparse-checkout set llvm clang cmake third-party
fi
got=$(git -C "$src" describe --tags --exact-match 2>/dev/null || true)
echo "clone: $(( $(date +%s) - start )) s"
[ "$got" = "$LLVM_TAG" ] || { echo "source is at '$got', pin says $LLVM_TAG" >&2; exit 1; }

# X86 is the host target the tools themselves need; M68k is the experimental target.
# Link jobs are serialised: linking clang is what exhausts RAM, not compiling.
configure=(cmake -S "$src/llvm" -B "$bld" -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_INSTALL_PREFIX="$prefix"
  -DLLVM_TARGETS_TO_BUILD=X86
  -DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=M68k
  -DLLVM_ENABLE_PROJECTS=clang
  -DLLVM_PARALLEL_LINK_JOBS=1
  -DLLVM_ENABLE_ASSERTIONS=OFF
  -DLLVM_ENABLE_DEBUG_INFO=OFF
  -DCMAKE_C_FLAGS_RELEASE=-O2
  -DCMAKE_CXX_FLAGS_RELEASE=-O2
  -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF
  -DLLVM_INCLUDE_DOCS=OFF -DCLANG_INCLUDE_TESTS=OFF -DCLANG_INCLUDE_DOCS=OFF
  -DCLANG_ENABLE_STATIC_ANALYZER=OFF -DCLANG_ENABLE_ARCMT=OFF
  -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_ZSTD=OFF -DLLVM_ENABLE_LIBXML2=OFF)
echo "configure: ${configure[*]}"
"${configure[@]}"

# Only what a bare-metal 68000 flow uses; no need to build or install the other tools.
tools=(clang llvm-mc llvm-objdump llvm-objcopy llvm-readelf llvm-nm)
ninja -C "$bld" -j "$jobs" "${tools[@]}" clang-resource-headers
echo "compile: $(( $(date +%s) - start )) s since start"
mkdir -p "$prefix/bin"
for t in "${tools[@]}"; do cp "$bld/bin/$t" "$prefix/bin/"; done
# clang finds its builtin headers relative to its own binary.
mkdir -p "$prefix/lib"
cp -r "$bld/lib/clang" "$prefix/lib/"

"$prefix/bin/clang" --version | head -1 | sed 's/^/built: /'
"$prefix/bin/clang" -print-targets | grep -i m68k | sed 's/^/target: /'
[ "$keep_build" = 1 ] || rm -rf "$bld" "$src"
echo "wall: $(( $(date +%s) - start )) s"
