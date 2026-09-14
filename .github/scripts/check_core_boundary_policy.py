#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# What the freestanding core is allowed to depend on (ADR-PORT-04 D1) — the policy only.
#
# Kept apart from check_core_boundary.py, which reads the tree and the archive, so that
# widening what the core may depend on is a diff to this file and nothing else. That is
# the point: an addition here is a policy change, reviewable as one, rather than an
# include nobody notices. Every entry carries the clause that admits or forbids it.
#
# check_core_boundary_selftest.py asserts classify()'s verdict on known symbol spellings,
# so a gap in this data fails a test rather than passing a scan.

from __future__ import annotations

import re

# --------------------------------------------------------------------------------------
# Include policy
# --------------------------------------------------------------------------------------
#
# Allowlist, not denylist: a header nobody has justified yet is a finding, so the set of
# things the core may depend on only ever grows through a reviewed change. Each entry
# names the clause that admits it. ADR-PORT-04 D1 admits the C++23 standard library minus
# everything that implies I/O, threads, allocation or a platform; the per-entry note says
# why a given header survives that subtraction.
#
# NOT here, on purpose, and each absence is the policy working:
#   <cstdio> <iostream> <fstream> <print> <syncstream>  — I/O (D1: "no I/O")
#   <thread> <mutex> <atomic> <future> <condition_variable> <stop_token> <barrier>
#                                                       — threads (D1: "no threads")
#   <memory> <vector> <string> <map> <set> <deque> <list> <unordered_map> <functional>
#                                                       — allocate (D1: "no dynamic
#                                                         allocation after initialisation";
#                                                         the core sizes fixed-capacity
#                                                         buffers from configuration)
#   <chrono> <ctime>                                    — read a clock (D1: "It cannot
#                                                         open a file, read a clock or
#                                                         draw anything")
#   <filesystem> <locale> <random> <regex>              — platform or allocating runtime
#
ALLOWED_ANGLE_INCLUDES: dict[str, str] = {
    # Types and limits. No runtime, no allocation, no platform surface.
    "cstddef": "D1 — size_t/ptrdiff_t/byte; freestanding, no runtime.",
    "cstdint": "D1 — fixed-width integer types; core/types.hpp is built on these.",
    "climits": "D1 — integer limit macros; preprocessor only.",
    "cfloat": "D1 — floating-point limit macros; preprocessor only.",
    "limits": "D1 — std::numeric_limits; constexpr, no runtime.",
    "version": "D1 — feature-test macros only; defines no entity.",
    # Compile-time machinery. Nothing survives to the object file.
    "type_traits": "D1 — compile-time only.",
    "concepts": "D1 — compile-time only.",
    "compare": "D1 — comparison categories; compile-time only.",
    "initializer_list": "D1 — compiler-supported, no allocation.",
    "source_location": "D1 — compile-time capture; used by diagnostics, not I/O.",
    "ratio": "D1 — compile-time rational arithmetic.",
    # Value types and views that own no storage.
    "array": "D1 — fixed-extent storage; the shape D1 mandates instead of <vector>.",
    "span": "D1 — non-owning view; allocates nothing.",
    "string_view": "D1 — non-owning view; the admissible half of <string>.",
    "utility": "D1 — std::move/forward/pair; no allocation.",
    "tuple": "D1 — aggregate of value types; no allocation.",
    "bit": "D1 — bit_cast/rotl/popcount; constexpr, no runtime.",
    # Diagnostics. assert()'s failure path is the standard's abort path — a
    # contract violation terminating the process, not the core performing I/O.
    "cassert": "D1 — assert(); its failure path is std::abort, not core I/O.",
}

# A quoted include must name a header of this module. Anything else is either a platform
# header reached by the wrong syntax or a reach into a layer D5 forbids.
ALLOWED_QUOTED_PREFIXES: tuple[str, ...] = ("meta_amiga/core/",)

SOURCE_SUFFIXES = (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".inl", ".in")

INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]')

# --------------------------------------------------------------------------------------
# Symbol policy
# --------------------------------------------------------------------------------------
#
# (rule, clause, exact names, mangled/substring fragments). Exact names are matched after
# the platform's leading-underscore convention is normalised away; fragments are matched
# anywhere in the raw symbol, which is how a mangled C++ name is caught without demangling
# (Itanium ABI and MSVC spellings are both listed).
#
DENIED_SYMBOLS: tuple[tuple[str, str, frozenset[str], tuple[str, ...]], ...] = (
    (
        "dynamic allocation",
        'ADR-PORT-04 D1 — "no dynamic allocation after initialisation". The core '
        "imports no allocator at all; buffers are fixed-capacity and sized from "
        "configuration.",
        frozenset(
            # POSIX and C.
            "malloc calloc realloc free aligned_alloc posix_memalign reallocarray "
            "strdup "
            # Win32 heap APIs. A fixed-pool allocator written over HeapAlloc is still an
            # allocator, and D1 does not care which one it is.
            "HeapAlloc HeapFree HeapReAlloc VirtualAlloc VirtualFree LocalAlloc "
            "LocalFree GlobalAlloc GlobalFree "
            # MSVC CRT spellings, as they read AFTER normalise() strips the leading
            # underscore: _aligned_malloc arrives here as aligned_malloc, one character
            # off the C11 aligned_alloc above — which is exactly how it got missed.
            "aligned_malloc aligned_free aligned_realloc aligned_offset_malloc "
            "malloc_base free_base calloc_base realloc_base expand recalloc".split()
        ),
        (
            "_Znw",  # operator new / operator new[] (Itanium ABI)
            "_Zna",
            "_Zdl",  # operator delete / operator delete[] (Itanium ABI)
            "_Zda",
            "??2@",  # operator new (MSVC)
            "??_U@",  # operator new[] (MSVC)
            "??3@",  # operator delete (MSVC)
            "??_V@",  # operator delete[] (MSVC)
            # Throwing allocates: __cxa_allocate_exception takes the exception object
            # from the heap (with a small emergency pool behind it). `throw X{}` in the
            # core is therefore a D1 allocation breach that adds no include for the
            # source scan to find, which is what makes it worth denying by symbol.
            # Fragments rather than exact names because Mach-O prefixes another
            # underscore (___cxa_throw) that normalise() leaves alone.
            "__cxa_allocate_exception",
            "__cxa_free_exception",
            "__cxa_throw",  # also catches __cxa_throw_bad_array_new_length
            "__cxa_rethrow",
            "_CxxThrowException",  # MSVC, plain and decorated
            # NOT denied, deliberately: __cxa_begin_catch, __gxx_personality_v0 and
            # std::terminate. Those are unwinding and contract-violation machinery, not
            # allocation, and a `noexcept` boundary can emit a reference to them without
            # the core ever throwing. Denying them would fail honest code.
        ),
    ),
    (
        "I/O",
        'ADR-PORT-04 D1 — "no I/O ... It cannot open a file". Everything the core '
        "emits or consumes goes through a D2 port it is handed at construction.",
        frozenset(
            "open open64 openat creat read write pread pwrite close lseek stat fstat "
            "fopen fopen64 freopen fclose fread fwrite fseek ftell "
            "printf fprintf vfprintf sprintf snprintf puts fputs putchar fputc getchar "
            "fgets perror socket connect send recv mmap "
            "CreateFileA CreateFileW ReadFile WriteFile".split()
        ),
        (
            "_ZSt4cout",  # std::cout
            "_ZSt4cerr",  # std::cerr
            "_ZSt4clog",
            "_ZSt3cin",
            "basic_ofstream",
            "basic_ifstream",
            "basic_fstream",
        ),
    ),
    (
        "threads",
        'ADR-PORT-04 D1 — "no threads". Determinism (ADR-CORE-01 D6) is an argument '
        "about a single-threaded core; a thread imported here invalidates it.",
        frozenset("thrd_create thrd_join fork CreateThread beginthreadex".split()),
        (
            "pthread_",
            "NSt6thread",  # std::thread (Itanium ABI)
            "St6thread",
            "thread@std@@",  # std::thread (MSVC)
            "Thrd_",  # MSVC threading runtime
        ),
    ),
    (
        "reading a clock",
        'ADR-PORT-04 D1 — "It cannot ... read a clock". Emulated time comes from the '
        "scheduler's cycle count, never from the host.",
        frozenset(
            "time time64 clock clock_gettime gettimeofday mach_absolute_time "
            "QueryPerformanceCounter GetSystemTimeAsFileTime GetTickCount "
            "GetTickCount64".split()
        ),
        (
            "NSt6chrono",  # std::chrono clock implementations (Itanium ABI)
            "chrono@std@@",  # std::chrono (MSVC)
        ),
    ),
)


def normalise(symbol: str) -> str:
    # Mach-O and 32-bit COFF prefix C symbols with an underscore; ELF and 64-bit COFF do
    # not. A COFF symbol reached through an import library carries __imp_ on top of that.
    # Strip both so the exact-name sets stay platform-independent. A mangled C++ name is
    # left alone — the fragments match it raw.
    for prefix in ("__imp_", "_imp_"):
        if symbol.startswith(prefix):
            symbol = symbol[len(prefix) :]
            break
    if symbol.startswith("_") and not symbol.startswith("__") and not symbol.startswith("_Z"):
        return symbol[1:]
    return symbol


def classify(symbol: str) -> list[tuple[str, str]]:
    """Every (rule, clause) a raw imported symbol breaches. Empty means admissible.

    Kept separate from the archive reading so the policy can be tested against known
    symbol spellings without a toolchain — see check_core_boundary_selftest.py.
    """
    plain = normalise(symbol)
    hits: list[tuple[str, str]] = []
    for rule, clause, exact, fragments in DENIED_SYMBOLS:
        if plain in exact or any(fragment in symbol for fragment in fragments):
            hits.append((rule, clause))
    return hits
