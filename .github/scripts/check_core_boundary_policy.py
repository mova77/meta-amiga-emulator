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
# Every header this policy has an opinion about is in one of the two dicts below. That is
# the point of having two: a contributor whose honest change trips the include half needs
# to know whether the absence is policy — rewrite the code — or an omission — make the
# case and widen the list. Those call for opposite responses, and a header in neither dict
# told them nothing. check_core_boundary.py quotes the recorded reason back when a
# deliberately excluded header is included, and says so explicitly when a header is in
# neither list.
#
# Several of these entries admit a header whose every escape route is denied on the other
# side, and the two halves being independent is what makes that safe rather than sloppy:
# <algorithm> is admitted while stable_sort's temporary allocation is denied by symbol,
# <variant> while the throw in std::get is. The alternative — excluding the header — puts
# the gate where it cannot tell an allocating use from a non-allocating one, and reddens
# honest code to catch dishonest code the other half already catches. Where an entry below
# says "measured", the symbols were read off a compiled probe rather than argued from the
# standard.
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
    # Vocabulary types that store their value inline. Each is the fixed-capacity answer to
    # something an allocating container header is excluded for.
    "new": "D1 — placement new, std::launder and align_val_t: the mechanism a "
    "fixed-capacity buffer is actually built from, which D1 mandates the shape of. The "
    "allocating operators this header also declares are denied by symbol (_Znw/_Zdl and "
    "the MSVC spellings), so the entry admits the construction and not the allocation.",
    "optional": "D1 — std::optional stores its value inline; measured, it imports "
    "nothing.",
    "variant": "D1 — std::variant stores the alternative inline. Measured: std::get "
    "throws on the wrong alternative and throwing allocates, which the symbol half "
    "denies, so the core uses the non-throwing accessors and the gate still says so.",
    "expected": "D1 — std::expected stores value or error inline: C++23's error channel "
    "for code that must not throw, which is the core. .value() throws and is denied by "
    "symbol.",
    # Algorithms and views over the fixed-extent storage D1 mandates. Without these the
    # core cannot sort its own event queue without writing the sort by hand.
    "algorithm": "D1 — operates on the range it is handed and owns nothing. Measured: "
    "stable_sort and inplace_merge do take a temporary buffer and import operator "
    "new(nothrow), which the symbol half denies; sort, find, copy and rotate import "
    "nothing. The parallel overloads need <execution>, which is excluded.",
    "ranges": "D1 — views are lazy and non-owning; measured, a filtered view over "
    "std::array imports nothing. ranges::to materialises into a container, and no "
    "container header is admitted.",
    "iterator": "D1 — iterator traits and adaptors, compile-time or trivial; measured, "
    "imports nothing. The stream iterators it also declares need a stream, and no stream "
    "header is admitted.",
    "numeric": "D1 — accumulate/reduce/gcd/midpoint over a range; measured, imports "
    "nothing. The parallel overloads need <execution>, which is excluded.",
    "bitset": "D1 — std::bitset<N> is fixed-extent bit storage, the shape D1 mandates, "
    "and the natural one for a chipset register. Measured: test() throws out_of_range and "
    "therefore allocates, which the symbol half denies; operator[] does not. to_string "
    "needs <string>, which is excluded.",
    # Bytes and text, without a string.
    "cstring": "D1 — memcpy/memmove/memset/memcmp; no allocation, no I/O. The symbol "
    "policy below already classifies memcpy admissible, so excluding the header that "
    "declares it would have the two halves contradict each other. strdup allocates and is "
    "denied by symbol.",
    "charconv": "D1 — to_chars/from_chars write into a caller-provided buffer: "
    "allocation-free, locale-free and non-throwing by design, which makes it the D1-shaped "
    "answer to <sstream>. Measured, it imports nothing.",
}

# The other half of the contract above: headers this policy has considered and refused.
# Prose until now, and prose could not be quoted back at a contributor or asserted in a
# test. Each entry is the reason a reader gets when the include half stops them.
EXCLUDED_ANGLE_INCLUDES: dict[str, str] = {
    # D1: "no I/O ... It cannot open a file".
    "cstdio": 'D1 — "no I/O". Diagnostics leave the core through the D2 HostLog port.',
    "iostream": 'D1 — "no I/O", and it allocates and constructs stream objects at start-up.',
    "fstream": 'D1 — "no I/O ... It cannot open a file". Images arrive through MediaSource.',
    "sstream": "D1 — allocates a string buffer. <charconv> is the admitted alternative.",
    "print": 'D1 — "no I/O", and it formats into an allocating buffer.',
    "syncstream": 'D1 — "no I/O", and synchronising a stream implies the threads D1 forbids.',
    # D1: "no threads". ADR-CORE-01 D6's determinism argument is about a single-threaded
    # core, so a thread imported here does not merely breach D1, it invalidates that too.
    "thread": 'D1 — "no threads".',
    "jthread": 'D1 — "no threads".',
    "mutex": 'D1 — "no threads"; a lock in the core means there is something to lock against.',
    "shared_mutex": 'D1 — "no threads".',
    "atomic": 'D1 — "no threads"; atomics exist to be shared between them.',
    "future": 'D1 — "no threads".',
    "condition_variable": 'D1 — "no threads".',
    "stop_token": 'D1 — "no threads".',
    "barrier": 'D1 — "no threads".',
    "latch": 'D1 — "no threads".',
    "semaphore": 'D1 — "no threads".',
    "execution": 'D1 — "no threads"; the parallel algorithm overloads are the reason '
    "<algorithm> and <numeric> are admitted only without it.",
    # D1: "no dynamic allocation after initialisation". The core sizes fixed-capacity
    # buffers from configuration, which is what <array> and <span> are admitted for.
    "memory": "D1 — unique_ptr/shared_ptr/allocator are the allocation D1 forbids.",
    "memory_resource": "D1 — a polymorphic allocator is still an allocator.",
    "vector": "D1 — grows on the heap. Use <array> sized from configuration.",
    "string": "D1 — allocates. <string_view> is admitted; <charconv> formats without one.",
    "map": "D1 — node-allocating. A fixed-capacity sorted <array> is the D1 shape.",
    "set": "D1 — node-allocating.",
    "unordered_map": "D1 — allocates buckets and nodes.",
    "unordered_set": "D1 — allocates buckets and nodes.",
    "deque": "D1 — allocates blocks.",
    "list": "D1 — allocates a node per element.",
    "forward_list": "D1 — allocates a node per element.",
    "queue": "D1 — allocates through the container it adapts.",
    "stack": "D1 — allocates through the container it adapts.",
    "functional": "D1 — std::function type-erases onto the heap above its small buffer.",
    # D1: "It cannot ... read a clock". Emulated time is the scheduler's cycle count.
    "chrono": 'D1 — "It cannot ... read a clock"; emulated time comes from the cycle count.',
    "ctime": 'D1 — "It cannot ... read a clock".',
    # Platform surface, or a runtime that allocates to do its job.
    "filesystem": "D1 — a platform surface, and it cannot open a file in any case.",
    "locale": "D1 — allocating, stateful, and a host-configuration dependency.",
    "random": "D1 — a seeded engine is state the determinism argument has to account for; "
    "the core's randomness, where it needs any, is part of the machine model.",
    "regex": "D1 — allocates, and pulls in <locale>.",
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
            "malloc_base free_base calloc_base realloc_base recalloc "
            # _expand — MSVC's grow-this-heap-block-in-place. Kept as an exact name, and
            # kept deliberately, because review was right that "expand" is a plausible
            # identifier in an emulator: expand a bitplane, expand an instruction field.
            #
            # Measured rather than argued: the core's own helpers are C++ in namespace
            # meta::amiga::core and so arrive mangled, _ZN4meta5amiga4core6expandEj, which
            # normalise() leaves alone by construction and which classifies admissible.
            # The only collision left is an extern "C" symbol literally named expand that
            # the core IMPORTS from another translation unit — and an unmangled global in
            # the core is already outside this module's conventions and exactly the shape
            # a platform escape takes, so a finding there is a conversation worth having
            # rather than a false alarm.
            #
            # A narrower rule would have to condition on the platform or on which other
            # symbols are present, and this file refuses conditional classification
            # outright — see the __cxa_begin_catch note below for why: nm aggregates
            # across archive members, so a verdict that depends on the rest of the library
            # shifts as files enter and leave it. Being wrong here costs a red leg naming
            # the symbol, cleared by renaming the helper or by a reviewed policy diff. It
            # never costs a silent pass, which is the direction that matters.
            "expand".split()
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
            #
            # Prefixes, not whole names: __cxa_allocate_dependent_exception — the rethrow
            # path, which also allocates — puts "dependent_" between the two halves and
            # slipped past the full spelling. Anything the ABI names __cxa_allocate_* or
            # __cxa_free_* is exception storage by construction, so the prefix is both
            # narrower to read and wider in coverage than enumerating the variants.
            "__cxa_allocate_",  # _exception and _dependent_exception
            "__cxa_free_",  # likewise
            "__cxa_throw",  # also catches __cxa_throw_bad_array_new_length
            "__cxa_rethrow",
            # MSVC, plain and decorated. Honest caveat: MSVC does NOT heap-allocate the
            # thrown object — it is constructed in the throwing frame and copied to the
            # catch frame — so on that platform this entry does not literally breach the
            # "no dynamic allocation" clause it sits under. It stays denied because a
            # throwing core is outside D1 regardless, and because this is the only throw
            # marker MSVC gives us. Recorded rather than glossed: a per-entry justification
            # that is wrong on one platform is worse than one that states its own limit.
            "_CxxThrowException",
            # NOT denied, deliberately: __cxa_begin_catch, __gxx_personality_v0 and
            # std::terminate. Measured, not assumed, on two probes: a real `throw` emits
            # __cxa_allocate_exception, __cxa_throw and __gxx_personality_v0 and NO
            # begin_catch or terminate, while a `noexcept` boundary around a fallible call
            # emits terminate, begin_catch and personality with no throw symbol at all.
            # They are companions of catching and of noexcept, not of throwing, and they
            # routinely appear where __cxa_throw is absent — so denying them would fail
            # honest code rather than add coverage.
            #
            # And they must be denied or not denied outright, never conditionally on
            # __cxa_throw being present too: nm aggregates across every archive member, so
            # a legitimate throw in one translation unit would silently un-flag a finding
            # in another, with the verdict shifting as files enter and leave the library.
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
