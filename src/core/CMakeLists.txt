# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# The emulation core. ADR-PORT-04 D1: freestanding — no I/O, no threads, no platform
# headers, no dependency beyond the C++23 standard library. Nothing may be linked here
# that would make that untrue.

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/include/meta_amiga/core/version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/include/meta_amiga/core/version.hpp"
    @ONLY)

add_library(meta-amiga-core STATIC
    scheduler.cpp)

add_library(meta-amiga::core ALIAS meta-amiga-core)

target_include_directories(meta-amiga-core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_BINARY_DIR}/include")

target_compile_features(meta-amiga-core PUBLIC cxx_std_23)

meta_amiga_set_warnings(meta-amiga-core)
meta_amiga_apply_sanitizers(meta-amiga-core)
