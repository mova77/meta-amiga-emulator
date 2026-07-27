# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Specification P-2: ASan/UBSan and TSan builds run in CI. They are opt-in presets
# rather than defaults so the ordinary developer build stays fast.

set(META_AMIGA_SANITIZER "" CACHE STRING "Sanitizer to enable: address, thread, or empty")
set_property(CACHE META_AMIGA_SANITIZER PROPERTY STRINGS "" address thread)

function(meta_amiga_apply_sanitizers target)
    if(NOT META_AMIGA_SANITIZER OR MSVC)
        return()
    endif()

    if(META_AMIGA_SANITIZER STREQUAL "address")
        set(flags -fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all)
    elseif(META_AMIGA_SANITIZER STREQUAL "thread")
        set(flags -fsanitize=thread -fno-omit-frame-pointer)
    else()
        message(FATAL_ERROR "Unknown META_AMIGA_SANITIZER '${META_AMIGA_SANITIZER}'")
    endif()

    target_compile_options(${target} PRIVATE ${flags})
    target_link_options(${target} PRIVATE ${flags})
endfunction()
