# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors

cmake_minimum_required(VERSION 3.28)

# Versioning is <yy>.<rel>.<fix> — see README.md. 26.0.0 is pre-release; the first
# public release of 2026 is 26.1.0.
project(meta-amiga
    VERSION 26.0.0
    DESCRIPTION "A portable, cycle-accurate Commodore Amiga emulator"
    HOMEPAGE_URL "https://github.com/meta-agentic/amiga-emulator"
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "" FORCE)
endif()

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(CompilerWarnings)
include(Sanitizers)

option(META_AMIGA_BUILD_TESTS "Build the test suite" ON)
option(META_AMIGA_WERROR "Treat warnings as errors" ON)

add_subdirectory(src/core)

if(META_AMIGA_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

message(STATUS "meta-amiga ${PROJECT_VERSION} — ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}, ${CMAKE_BUILD_TYPE}")
