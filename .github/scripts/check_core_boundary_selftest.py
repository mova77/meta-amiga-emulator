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
from check_core_boundary_policy import (  # noqa: E402
    ALLOWED_ANGLE_INCLUDES,
    EXCLUDED_ANGLE_INCLUDES,
    classify,
)

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
    # Second review round. The rethrow path allocates too, and "dependent_" sits between
    # the two halves of the name, so the full spelling __cxa_allocate_exception did not
    # match it. These rows are why the policy uses the __cxa_allocate_ prefix now.
    ("__cxa_allocate_dependent_exception", "dynamic allocation", "rethrow path"),
    ("___cxa_allocate_dependent_exception", "dynamic allocation", "Mach-O spelling"),
    ("__cxa_free_dependent_exception", "dynamic allocation", ""),
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
    # Review asked whether the exact-name `expand` entry is right, since "expand" is a
    # plausible identifier in an emulator. These three rows are the answer, executable:
    # the MSVC CRT spellings are caught and the core's own mangled helper is not.
    ("_expand", "dynamic allocation", "MSVC CRT, the spelling the entry exists for"),
    ("expand", "dynamic allocation", "the same, as COFF64 reports it"),
    (
        "_ZN4meta5amiga4core6expandEj",
        None,
        "a mangled core::expand is unaffected — normalise() leaves _Z names alone",
    ),
    # Measured off a compiled probe, not argued: this is what libc++'s stable_sort and
    # inplace_merge import, and it is the entire reason <algorithm> can be admitted.
    ("__ZnwmRKSt9nothrow_t", "dynamic allocation", "operator new(nothrow), from stable_sort"),
    ("_ZdlPvSt11align_val_t", "dynamic allocation", "sized/aligned delete, its counterpart"),
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
    # These three are NECESSARY exclusions, not merely safe ones, and it was measured
    # rather than argued. A real `throw` emits ___cxa_allocate_exception, ___cxa_throw and
    # ___gxx_personality_v0 and NO ___cxa_begin_catch or terminate; a noexcept boundary
    # with no throw at all emits terminate, begin_catch and personality and no throw
    # symbols. So they are companions of catching and of noexcept, and they routinely
    # appear where __cxa_throw is absent — denying them would fail honest code.
    ("___cxa_begin_catch", None, "catching allocates nothing"),
    ("___gxx_personality_v0", None, "EH personality; a noexcept boundary emits it"),
    ("__ZSt9terminatev", None, "std::terminate, a contract-violation path"),
    ("_ZN4meta5amiga4core19linkedVersionStringEv", None, "the core's own symbol"),
    ("memcpy", None, "not I/O, not allocation; freestanding-admissible"),
    ("__stack_chk_fail", None, "stack protector"),
)


# --------------------------------------------------------------------------------------
# Include policy
# --------------------------------------------------------------------------------------
#
# Every header PR #3's review found in neither list. The rule the rows below enforce is
# simply that none of them can sit in neither list again: a contributor who trips the
# include half must be able to read off whether the absence is policy or an omission,
# because those call for opposite responses.
REVIEWED_HEADERS: tuple[str, ...] = (
    "new",
    "optional",
    "variant",
    "expected",
    "algorithm",
    "ranges",
    "iterator",
    "numeric",
    "bitset",
    "cstring",
    "charconv",
)

# (header admitted, a symbol the escape route inside it imports, the rule that must still
# catch that symbol, why the row exists).
#
# This is what makes admitting these headers safe rather than a quiet loosening, and it is
# the part worth having a test for. Each admitted header has some corner that would breach
# D1; each corner is denied on the other half. Prose saying so rots the moment somebody
# edits DENIED_SYMBOLS. A row fails.
COMPLEMENTARY: tuple[tuple[str, str, str, str], ...] = (
    (
        "algorithm",
        "__ZnwmRKSt9nothrow_t",
        "dynamic allocation",
        "stable_sort and inplace_merge take a temporary buffer — measured",
    ),
    ("new", "__Znwm", "dynamic allocation", "<new> declares the allocating operators too"),
    ("new", "??2@YAPEAX_K@Z", "dynamic allocation", "and their MSVC spellings"),
    (
        "variant",
        "___cxa_allocate_exception",
        "dynamic allocation",
        "std::get throws on the wrong alternative, and throwing allocates — measured",
    ),
    ("expected", "___cxa_throw", "dynamic allocation", ".value() throws on an error"),
    (
        "bitset",
        "___cxa_allocate_exception",
        "dynamic allocation",
        "bitset::test throws out_of_range — measured; operator[] does not",
    ),
    ("cstring", "strdup", "dynamic allocation", "the one allocating function it reaches"),
    ("iterator", "_ZSt4cout", "I/O", "the stream iterators it declares need a stream"),
    ("ranges", "_Znwm", "dynamic allocation", "ranges::to materialises into a container"),
    ("numeric", "_Znwm", "dynamic allocation", "the same allocator, if a range is built"),
    ("charconv", "fopen", "I/O", "formatting is not a reason for the core to open a file"),
)


def check_include_policy() -> list[str]:
    failures: list[str] = []

    both = sorted(set(ALLOWED_ANGLE_INCLUDES) & set(EXCLUDED_ANGLE_INCLUDES))
    if both:
        failures.append(f"admitted and refused at once: {both}")

    for header in REVIEWED_HEADERS:
        allowed = header in ALLOWED_ANGLE_INCLUDES
        excluded = header in EXCLUDED_ANGLE_INCLUDES
        if not allowed and not excluded:
            failures.append(
                f"<{header}> is in neither list, so the gate cannot tell a contributor "
                "whether its absence is policy or an omission"
            )

    for header, clause in ALLOWED_ANGLE_INCLUDES.items():
        if "D1" not in clause and "D5" not in clause:
            failures.append(f"<{header}> is admitted without citing a clause: {clause!r}")
    for header, reason in EXCLUDED_ANGLE_INCLUDES.items():
        if "D1" not in reason and "D5" not in reason:
            failures.append(f"<{header}> is refused without citing a clause: {reason!r}")

    for header, symbol, rule, note in COMPLEMENTARY:
        if header not in ALLOWED_ANGLE_INCLUDES:
            failures.append(f"<{header}> is no longer admitted, so this row is stale")
            continue
        rules = [name for name, _clause in classify(symbol)]
        if rule not in rules:
            failures.append(
                f"<{header}> is admitted because {symbol!r} is still denied as {rule!r}, "
                f"and it now classifies as {rules or 'clean'}  ({note})"
            )
    return failures


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

    failures.extend(check_include_policy())

    print(
        f"check_core_boundary policy self-test — {len(CASES)} symbol cases, "
        f"{len(ALLOWED_ANGLE_INCLUDES)} headers admitted and "
        f"{len(EXCLUDED_ANGLE_INCLUDES)} refused, {len(COMPLEMENTARY)} of those "
        "admissions resting on a symbol that is still denied"
    )
    if failures:
        for failure in failures:
            print(f"::error::{failure}")
            print(f"  {failure}")
        print(f"FAIL — {len(failures)} expectation(s) wrong.")
        return 1
    print("PASS — every case classified as expected, and every header accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
