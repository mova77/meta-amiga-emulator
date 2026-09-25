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

meta_amiga_add_test(version_test)
meta_amiga_add_test(slot_allocator_test)
meta_amiga_add_test(slot_allocator_unsourced_test)
set_tests_properties(slot_allocator_unsourced_test PROPERTIES SKIP_RETURN_CODE 77)

# The generated slot tables must match the YAML they come from. Skipped, not failed,
# where PyYAML is absent; the headers are checked in, so the build never needs it.
find_package(Python3 COMPONENTS Interpreter)
if(Python3_Interpreter_FOUND)
    add_test(NAME slot_tables_generated_up_to_date
        COMMAND Python3::Interpreter "${PROJECT_SOURCE_DIR}/scripts/gen_slot_tables.py" --check)
    add_test(NAME slot_tables_generator_test
        COMMAND Python3::Interpreter "${PROJECT_SOURCE_DIR}/scripts/test_gen_slot_tables.py")
    set_tests_properties(slot_tables_generated_up_to_date slot_tables_generator_test
        PROPERTIES SKIP_RETURN_CODE 77)
endif()
