# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors

cmake_minimum_required(VERSION 3.28)

# Versioning is <yy>.<rel>.<fix> — see README.md. 26.0.0 is pre-release; the first
# public release of 2026 is 26.1.0.
project(meta-amiga
    VERSION 26.0.0
    DESCRIPTION "A portable, cycle-accurate Commodore Amiga emulator"
    LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Fail at configure time rather than with a wall of template errors halfway through the
# build. The floors are the versions where the C++23 features this project relies on are
# usable, not merely announced. AppleClang is versioned independently of LLVM and needs
# its own floor — treating it as Clang would reject working toolchains.
set(_min_version "")
if(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
    set(_min_version 15.0)
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
    set(_min_version 17.0)
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    set(_min_version 13.0)
elseif(CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    set(_min_version 19.38)
else()
    message(WARNING
        "Untested compiler '${CMAKE_CXX_COMPILER_ID}'. The build may work; it is not "
        "covered by CI, so a failure here is expected rather than surprising.")
endif()

if(_min_version AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS _min_version)
    message(FATAL_ERROR
        "${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION} is below the supported "
        "floor of ${_min_version}.")
endif()

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE RelWithDebInfo CACHE STRING "" FORCE)
endif()

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")
include(CompilerWarnings)
include(Sanitizers)

# Warnings are errors for us, but not for someone building a release from source on a
# toolchain we have never seen: a new warning in a future compiler should not stop them
# getting a working emulator. Both default to the project's own build only.
option(META_AMIGA_BUILD_TESTS "Build the test suite" ${PROJECT_IS_TOP_LEVEL})
option(META_AMIGA_WERROR "Treat warnings as errors" ${PROJECT_IS_TOP_LEVEL})

add_subdirectory(src/core)

if(META_AMIGA_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

message(STATUS
    "meta-amiga ${PROJECT_VERSION} — ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}, "
    "${CMAKE_BUILD_TYPE}, werror=${META_AMIGA_WERROR}, sanitizer='${META_AMIGA_SANITIZER}'")
