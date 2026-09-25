# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# The emulation core. ADR-PORT-04 D1: freestanding — no I/O, no threads, no platform
# headers, no dependency beyond the C++23 standard library. Nothing may be linked here
# that would make that untrue. That is a build-time check rather than a convention:
# `.github/scripts/check_core_boundary.py` scans this directory's includes and the
# imported symbols of the library below, and CI fails the build on a breach. Widening
# what the core may depend on means editing `check_core_boundary_policy.py` beside it,
# which makes it a reviewable policy change rather than an include nobody notices.
#
# Subsystems land into this structure; chipset/ holds the DMA slot allocator, whose
# tables are generated from docs/reference/dma-slot-allocation.yaml by
# scripts/gen_slot_tables.py and checked in, so the build itself needs no Python.

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/include/meta_amiga/core/version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/include/meta_amiga/core/version.hpp"
    @ONLY)

add_library(meta-amiga-core STATIC
    version.cpp
    chipset/slot_allocator.cpp)

add_library(meta-amiga::core ALIAS meta-amiga-core)

target_include_directories(meta-amiga-core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
    "${CMAKE_CURRENT_BINARY_DIR}/include")

target_compile_features(meta-amiga-core PUBLIC cxx_std_23)

meta_amiga_set_warnings(meta-amiga-core)
meta_amiga_apply_sanitizers(meta-amiga-core)
