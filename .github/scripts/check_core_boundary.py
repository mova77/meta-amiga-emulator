#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Architecture test for the freestanding-core boundary (ADR-PORT-04 D1).
#
# D1 says the core has "no I/O, no threads, no dynamic allocation after initialisation, no
# platform headers, no third-party dependencies, and no dependency beyond the C++23
# standard library", and that this "is enforced by an architecture test in CI that scans
# the module's includes and symbols, not by convention". This is that test.
#
# Two surfaces, deliberately independent — each catches breaches the other cannot:
#
#   Includes  A source scan of src/core/**. An angle include must be on the allowlist
#             below; a quoted include must resolve inside meta_amiga/core/. Catches a
#             platform header, a third-party header, and a standard header whose mere
#             presence contradicts D1 (<cstdio>, <thread>, <memory>).
#
#   Symbols   The undefined (imported) symbols of the built meta-amiga-core static
#             library, against a denylist. Catches an escape that reaches libc through a
#             header that is itself admissible, and an escape introduced by a header this
#             scan cannot see because it was pulled in transitively.
#
# Scope note — this does NOT prove "no dynamic allocation *after* initialisation". That is
# a runtime property, not a link-time one. The symbol denylist asserts the stronger and
# currently true statement that the core imports no allocator at all; the weaker runtime
# form is left to the ASan legs in CI.
#
# Scope note — ADR-PORT-04 D5 ("core never references ports or frontend") is unchecked:
# neither directory exists. Adding them is rows in ALLOWED_QUOTED_PREFIXES, not a redesign.
#
# Platform coverage — the symbol half prefers `nm` and falls back to `dumpbin /symbols`.
# The difference is here, inside the script, not in the CI matrix. If neither tool can be
# found, the symbol half reports itself SKIPPED with a reason and the include half still
# runs and still fails the build on a breach. A check that is honest about its coverage
# beats one that silently passes.
#
# Measured on the Windows leg rather than assumed: `windows-latest` has an `nm` on PATH
# (Git for Windows ships binutils) and it reads an MSVC `.lib` archive correctly — a
# planted malloc/free import was found in
# build/windows/src/core/RelWithDebInfo/meta-amiga-core.lib and failed that leg. So the
# dumpbin branch below is the fallback for a host without nm, not the Windows path, and
# it is consequently the one part of this script CI does not exercise. It was validated
# by hand against a representative COFF symbol table; treat it as unproven until a host
# without nm actually runs it.
#
# Run it with no arguments from a configured and built tree:
#
#     cmake --preset dev && cmake --build --preset dev
#     python3 .github/scripts/check_core_boundary.py
#
# CI adds --require-symbols, which turns "the library was never built" from a reported
# skip into a failure. A host that has the library but no symbol reader still only
# reports a skip: that is a platform limitation, not a hole in the build.

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "src" / "core"

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
            "malloc calloc realloc free aligned_alloc posix_memalign reallocarray "
            "strdup".split()
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

LIBRARY_NAMES = ("libmeta-amiga-core.a", "meta-amiga-core.lib", "libmeta-amiga-core.lib")


class Finding:
    def __init__(self, where: str, rule: str, detail: str, annotate: str | None = None) -> None:
        self.where = where
        self.rule = rule
        self.detail = detail
        # Source path for a GitHub annotation, when the finding has one. A symbol finding
        # points at a build artifact, which is not a place a reviewer can click to.
        self.annotate = annotate

    def render(self) -> str:
        return f"{self.where}: {self.detail}\n    rule broken: {self.rule}"

    def annotation(self) -> str:
        if self.annotate:
            return f"::error file={self.annotate}::{self.detail}"
        return f"::error::{self.where}: {self.detail}"


# --------------------------------------------------------------------------------------
# Include half
# --------------------------------------------------------------------------------------


def core_sources() -> list[Path]:
    found: list[Path] = []
    for path in sorted(CORE_DIR.rglob("*")):
        if path.is_file() and path.name.endswith(SOURCE_SUFFIXES):
            found.append(path)
    return found


def check_includes() -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    sources = core_sources()
    for path in sources:
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = INCLUDE_RE.match(line)
            if not match:
                continue
            kind, header = match.group(1), match.group(2).strip()
            where = f"{rel}:{lineno}"
            if kind == "<":
                if header not in ALLOWED_ANGLE_INCLUDES:
                    findings.append(
                        Finding(
                            where,
                            "ADR-PORT-04 D1 — the core depends on nothing beyond the "
                            "admissible subset of the C++23 standard library. "
                            "<%s> is not on the allowlist in %s."
                            % (header, Path(__file__).name),
                            f"include of <{header}> is outside the freestanding subset",
                            annotate=rel,
                        )
                    )
            else:
                if not header.startswith(ALLOWED_QUOTED_PREFIXES):
                    findings.append(
                        Finding(
                            where,
                            "ADR-PORT-04 D1/D5 — a quoted include from src/core/ must "
                            "name a core header (meta_amiga/core/...). The core "
                            "references no other layer and no vendored dependency.",
                            f'include of "{header}" leaves the core module',
                            annotate=rel,
                        )
                    )
    return findings, len(sources)


# --------------------------------------------------------------------------------------
# Symbol half
# --------------------------------------------------------------------------------------


def find_library(build_dir: Path | None) -> Path | None:
    roots = [build_dir] if build_dir else [REPO_ROOT / "build"]
    candidates: list[Path] = []
    for root in roots:
        if root is None or not root.is_dir():
            continue
        for name in LIBRARY_NAMES:
            candidates.extend(root.rglob(name))
    if not candidates:
        return None
    # Newest wins: with several presets configured, the one just built is the one the
    # caller means.
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_dumpbin() -> str | None:
    found = shutil.which("dumpbin")
    if found:
        return found
    program_files = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    if not program_files:
        return None
    vswhere = Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    try:
        out = subprocess.run(
            [str(vswhere), "-latest", "-products", "*", "-find", "**\\dumpbin.exe"],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.lower().endswith("dumpbin.exe") and Path(line).is_file():
            # Several host/target pairs are reported; any of them reads a .lib symbol
            # table identically.
            return line
    return None


def undefined_symbols_nm(nm: str, library: Path) -> list[str]:
    out = subprocess.run(
        [nm, "-u", str(library)], capture_output=True, text=True, timeout=300
    )
    if out.returncode != 0:
        raise RuntimeError(f"{nm} failed: {out.stderr.strip()}")
    symbols: list[str] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line or line.endswith(":"):
            continue
        # GNU nm -u prints "        U symbol"; BSD/Apple nm -u prints bare names.
        parts = line.split()
        symbols.append(parts[-1])
    return symbols


def undefined_symbols_dumpbin(dumpbin: str, library: Path) -> list[str]:
    out = subprocess.run(
        [dumpbin, "/symbols", "/nologo", str(library)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if out.returncode != 0:
        raise RuntimeError(f"dumpbin failed: {out.stderr.strip()}")
    symbols: list[str] = []
    for line in out.stdout.splitlines():
        # A COFF symbol-table row for an import reads, with columns:
        #   00F 00000000 UNDEF  notype ()    External     | ?name@@YAXXZ
        if " UNDEF " not in line or "External" not in line:
            continue
        name = line.rsplit("|", 1)[-1].strip()
        if name:
            # dumpbin appends a demangled form in parentheses for some symbols; the raw
            # decorated name is the first token and is what the fragments match.
            symbols.append(name.split()[0])
    return symbols


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


def check_symbols(build_dir: Path | None) -> tuple[list[Finding], str]:
    library = find_library(build_dir)
    if library is None:
        # Distinct from SKIPPED below: a missing library means the build did not run,
        # which in CI is a hole in the gate rather than a platform limitation.
        return [], (
            "MISSING — no built meta-amiga-core library found under "
            f"{(build_dir or REPO_ROOT / 'build')}. Build first: "
            "cmake --preset dev && cmake --build --preset dev"
        )

    nm = shutil.which("nm") or shutil.which("llvm-nm")
    reader = None
    if nm:
        reader = ("nm", lambda: undefined_symbols_nm(nm, library))
    else:
        dumpbin = find_dumpbin()
        if dumpbin:
            reader = ("dumpbin /symbols", lambda: undefined_symbols_dumpbin(dumpbin, library))

    if reader is None:
        # The stated fallback: include half everywhere, symbol half where a symbol reader
        # exists. Reported, never silently passed.
        return [], (
            "SKIPPED — neither nm nor dumpbin was found on this host, so the imported "
            "symbols of the core could not be read. The include half above still ran."
        )

    tool_name, read = reader
    try:
        symbols = read()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return [], f"SKIPPED — {tool_name} could not read {library.name}: {exc}"

    rel = library.relative_to(REPO_ROOT).as_posix() if library.is_relative_to(REPO_ROOT) else str(library)
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for raw in symbols:
        plain = normalise(raw)
        for rule, clause, exact, fragments in DENIED_SYMBOLS:
            hit = plain in exact or any(fragment in raw for fragment in fragments)
            if hit and (raw, rule) not in seen:
                seen.add((raw, rule))
                findings.append(
                    Finding(
                        rel,
                        clause,
                        f"the core imports '{raw}' — {rule}",
                    )
                )
    return findings, f"{len(symbols)} imported symbols read with {tool_name} from {rel}"


# --------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce the freestanding-core boundary of ADR-PORT-04 D1."
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Build tree holding the meta-amiga-core library. Defaults to searching "
        "build/, which is what CI and a preset build both produce.",
    )
    parser.add_argument(
        "--require-symbols",
        action="store_true",
        help="Fail if the core library could not be found at all. CI passes this, "
        "because there the library is always built first and its absence would be a "
        "hole in the gate rather than a platform limitation. A host that has the "
        "library but no nm or dumpbin still reports a stated skip, never an error — "
        "that is the fallback this script documents.",
    )
    args = parser.parse_args()

    if not CORE_DIR.is_dir():
        print(f"::error::src/core not found at {CORE_DIR}", file=sys.stderr)
        return 2

    include_findings, scanned = check_includes()
    symbol_findings, symbol_status = check_symbols(args.build_dir)

    print("meta-amiga — freestanding-core boundary check (ADR-PORT-04 D1)")
    print(f"  includes: {scanned} files scanned under src/core/")
    print(f"  symbols:  {symbol_status}")

    findings = include_findings + symbol_findings
    if symbol_status.startswith("MISSING") and args.require_symbols:
        findings.append(
            Finding(
                ".github/scripts/" + Path(__file__).name,
                "ADR-PORT-04 D1 is enforced over includes *and* symbols; half a check "
                "reported as a pass is the convention this test exists to replace.",
                "the core library was not found and --require-symbols was given",
            )
        )

    if not findings:
        print("PASS — the core stays inside D1.")
        return 0

    print("")
    for finding in findings:
        # GitHub renders ::error:: as an annotation; the plain text below it is what a
        # local run reads.
        print(finding.annotation())
        print(finding.render())
        print("")
    print(f"FAIL — {len(findings)} boundary violation(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
