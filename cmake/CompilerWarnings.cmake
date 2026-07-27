# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Specification P-2: the project builds clean under a strict warning set on every
# supported compiler, and warnings are errors by default.

function(meta_amiga_set_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE
            /W4
            /permissive-
            /w14640      # thread-unsafe static member initialisation
            /w14826      # conversion is sign-extended
            $<$<BOOL:${META_AMIGA_WERROR}>:/WX>)
    else()
        target_compile_options(${target} PRIVATE
            -Wall
            -Wextra
            -Wpedantic
            -Wshadow
            -Wconversion
            -Wsign-conversion
            -Wcast-qual
            -Wold-style-cast
            -Wnon-virtual-dtor
            -Woverloaded-virtual
            -Wdouble-promotion
            -Wformat=2
            -Wimplicit-fallthrough
            $<$<BOOL:${META_AMIGA_WERROR}>:-Werror>)
    endif()
endfunction()
