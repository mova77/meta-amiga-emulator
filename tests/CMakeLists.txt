# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors

function(meta_amiga_add_test name)
    add_executable(${name} "unit/${name}.cpp")
    target_link_libraries(${name} PRIVATE meta-amiga::core)
    target_include_directories(${name} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
    meta_amiga_set_warnings(${name})
    meta_amiga_apply_sanitizers(${name})
    add_test(NAME ${name} COMMAND ${name})
endfunction()

meta_amiga_add_test(scheduler_test)
meta_amiga_add_test(timing_test)
