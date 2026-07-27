# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# The emulation core. ADR-PORT-04 D1: freestanding — no I/O, no threads, no platform
# headers, no dependency beyond the C++23 standard library. Nothing may be linked here
# that would make that untrue. An architecture test will turn that from a convention into
# a build-time check; until it exists, this comment is the only thing enforcing it.
#
# At this stage the library holds only the version accessor. It exists so the build
# foundation is provably exercised end to end — configure_file, the include path, the
# warning set, the sanitizer flags and the link step — rather than being declared correct
# on an empty target. Subsystems land into this structure.

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/include/meta_amiga/core/version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/include/meta_amiga/core/version.hpp"
    @ONLY)

add_library(meta-amiga-core STATIC
    version.cpp)

add_library(meta-amiga::core ALIAS meta-amiga-core)

target_include_directories(meta-amiga-core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_BINARY_DIR}/include")

target_compile_features(meta-amiga-core PUBLIC cxx_std_23)

meta_amiga_set_warnings(meta-amiga-core)
meta_amiga_apply_sanitizers(meta-amiga-core)
