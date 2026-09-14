#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Self-test for the policy data in check_core_boundary_policy.py.
#
# The architecture test has two kinds of bug. One is mechanical — the archive reader
# breaks — and a planted breach in CI catches that. The other is a denylist that simply
# does not name the symbol an escape actually imports, and a planted breach catches that
# only for the one escape it plants. This file covers the second kind: it asserts the
# classifier's verdict on known symbol spellings, needing no toolchain, no build tree and
# no platform, so every row runs on every leg.
#
# Rows exist because something got through. The exception-machinery and Win32-allocator
# rows are here because review found a `throw` in the core, and a fixed pool over
# HeapAlloc, both classified clean and would have shipped green.
#
#     python3 .github/scripts/check_core_boundary_selftest.py

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_core_boundary_policy import classify  # noqa: E402

# (symbol as a reader would report it, expected rule or None, why this row exists)
CASES: tuple[tuple[str, str | None, str], ...] = (
    # --- Allocation: the plain C spellings, on each platform's convention -------------
    ("malloc", "dynamic allocation", "ELF/COFF64 bare name"),
    ("_malloc", "dynamic allocation", "Mach-O and COFF32 prefix one underscore"),
    ("__imp_malloc", "dynamic allocation", "reached through a COFF import library"),
    ("free", "dynamic allocation", "the other half of the pair"),
    ("calloc", "dynamic allocation", ""),
    ("posix_memalign", "dynamic allocation", ""),
    # --- Allocation: operator new/delete, both ABIs -----------------------------------
    ("_Znwm", "dynamic allocation", "operator new(size_t), Itanium ABI"),
    ("_Znam", "dynamic allocation", "operator new[](size_t), Itanium ABI"),
    ("_ZdlPv", "dynamic allocation", "operator delete(void*), Itanium ABI"),
    ("??2@YAPEAX_K@Z", "dynamic allocation", "operator new, MSVC"),
    ("??3@YAXPEAX@Z", "dynamic allocation", "operator delete, MSVC"),
    # --- Allocation: throwing ---------------------------------------------------------
    # Review finding. `throw BadAddress{};` in the core heap-allocates the exception
    # object and adds no include for the source scan to find, so the symbol half is the
    # only half that can see it. Every one of these classified clean before the fix.
    ("__cxa_allocate_exception", "dynamic allocation", "Itanium ABI, ELF spelling"),
    ("___cxa_allocate_exception", "dynamic allocation", "Mach-O adds an underscore"),
    ("__cxa_throw", "dynamic allocation", ""),
    ("___cxa_throw", "dynamic allocation", ""),
    ("__cxa_free_exception", "dynamic allocation", ""),
    ("__cxa_rethrow", "dynamic allocation", ""),
    ("_CxxThrowException", "dynamic allocation", "MSVC, plain"),
    ("?_CxxThrowException@@YAXPEAXPEBU_s__ThrowInfo@@@Z", "dynamic allocation", "MSVC"),
    ("__cxa_throw_bad_array_new_length", "dynamic allocation", "allocation failure path"),
    # --- Allocation: Win32 and the MSVC CRT -------------------------------------------
    # Review finding. A fixed-pool allocator written over HeapAlloc is still an allocator.
    ("HeapAlloc", "dynamic allocation", ""),
    ("HeapFree", "dynamic allocation", ""),
    ("VirtualAlloc", "dynamic allocation", ""),
    ("LocalAlloc", "dynamic allocation", ""),
    ("GlobalAlloc", "dynamic allocation", ""),
    # One character from the C11 aligned_alloc that was already listed, which is exactly
    # how it slipped through: normalise() strips the leading underscore, leaving
    # "aligned_malloc", which matched nothing.
    ("_aligned_malloc", "dynamic allocation", "MSVC CRT"),
    ("_aligned_free", "dynamic allocation", "MSVC CRT"),
    ("_malloc_base", "dynamic allocation", "MSVC CRT internal"),
    ("_recalloc", "dynamic allocation", "MSVC CRT"),
    # --- I/O ---------------------------------------------------------------------------
    ("fopen", "I/O", ""),
    ("_fopen", "I/O", ""),
    ("__imp_fclose", "I/O", ""),
    ("write", "I/O", ""),
    ("CreateFileW", "I/O", ""),
    ("_ZSt4cout", "I/O", "std::cout"),
    # --- Threads -----------------------------------------------------------------------
    ("pthread_create", "threads", ""),
    ("_ZNSt6thread15_M_start_threadESt10unique_ptr", "threads", "std::thread, Itanium"),
    ("?_Thrd_start@@YAXXZ", "threads", "MSVC threading runtime"),
    ("CreateThread", "threads", ""),
    # --- Clocks ------------------------------------------------------------------------
    ("clock_gettime", "reading a clock", ""),
    ("QueryPerformanceCounter", "reading a clock", ""),
    ("mach_absolute_time", "reading a clock", ""),
    ("time", "reading a clock", ""),
    # --- Admissible: must NOT be flagged ------------------------------------------------
    # A denylist that fails honest code gets switched off, so the negative rows matter as
    # much as the positive ones.
    ("__security_cookie", None, "MSVC stack-guard cookie, benign"),
    ("___cxa_begin_catch", None, "unwinding, not allocation — catching allocates nothing"),
    ("___gxx_personality_v0", None, "EH personality routine; a noexcept boundary emits it"),
    ("__ZSt9terminatev", None, "std::terminate, a contract-violation path"),
    ("_ZN4meta5amiga4core19linkedVersionStringEv", None, "the core's own symbol"),
    ("memcpy", None, "not I/O, not allocation; freestanding-admissible"),
    ("__stack_chk_fail", None, "stack protector"),
)


def main() -> int:
    failures: list[str] = []
    for symbol, expected, note in CASES:
        rules = [rule for rule, _clause in classify(symbol)]
        if expected is None:
            if rules:
                failures.append(
                    f"{symbol!r} should be admissible but was flagged as {rules}"
                    + (f"  ({note})" if note else "")
                )
        elif expected not in rules:
            failures.append(
                f"{symbol!r} should breach {expected!r} but classified as "
                f"{rules or 'clean'}" + (f"  ({note})" if note else "")
            )

    print(f"check_core_boundary policy self-test — {len(CASES)} cases")
    if failures:
        for failure in failures:
            print(f"::error::{failure}")
            print(f"  {failure}")
        print(f"FAIL — {len(failures)} of {len(CASES)} cases wrong.")
        return 1
    print("PASS — every case classified as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
