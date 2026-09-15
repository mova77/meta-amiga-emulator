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
#   Symbols   The undefined (imported) symbols of every static library built from
#             src/core/**, against a denylist. Catches an escape that reaches libc through
#             a header that is itself admissible, and an escape introduced by a header
#             this scan cannot see because it was pulled in transitively. Which libraries
#             those are is discovered from the add_library() calls that compile core
#             sources, wherever they are declared, so
#             both halves cover the same directory and a new core library comes under the
#             symbol scan the day it is declared — see "Library discovery" below.
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
# The difference is here, inside the script, not in the CI matrix. If the half cannot
# actually inspect the library — no tool, a tool that errors, a tool that returns an empty
# symbol table — it says NOT RUN, with the reason and the reader it tried. Under CI's
# --require-symbols that is a failure, because a gate that quietly enforces half of itself
# is worse than no gate: it reads as a pass. Without the flag it is reported and tolerated,
# so a local run on a host with no symbol reader still gets the include half.
#
# Measured on the Windows leg rather than assumed: `windows-latest` has an `nm` on PATH —
# at C:\mingw64\bin\nm.EXE, from the image's MinGW, which is why the status line prints
# the reader's full path rather than just "nm" — and it reads an MSVC `.lib` archive
# correctly. Planted malloc/free and _CxxThrowException imports were both found in
# build/windows/src/core/RelWithDebInfo/meta-amiga-core.lib and failed that leg.
#
# So the dumpbin branch below is the fallback for a host without nm, not the Windows path,
# and it is consequently the one part of this script CI does not exercise. It was validated
# by hand against a representative COFF symbol table; treat it as unproven until a host
# without nm actually runs it. That host is not hypothetical: nm is on the Windows runner
# by an accident of the image, not by anything this project controls, and --require-symbols
# means the leg goes red rather than quiet if it disappears.
#
# Run it with no arguments from a configured and built tree:
#
#     cmake --preset dev && cmake --build --preset dev
#     python3 .github/scripts/check_core_boundary.py
#
# CI adds --require-symbols, which turns any NOT RUN into a failure.
#
# Five files, because they fail for different reasons and are reviewed by different
# people:
#   check_core_boundary.py          reads the tree and the archive, and reports — this file
#   check_core_boundary_policy.py   what is allowed and what is not, with the clause
#                                   behind each entry; widening it is a diff to that file
#   check_core_boundary_discovery.py
#                                   which libraries the symbol half must read, derived
#                                   from the add_library() calls that compile core
#                                   sources, so both halves cover the same directory
#   check_core_boundary_selftest.py asserts the policy's verdict on known symbol
#                                   spellings, so a gap fails a test rather than passing
#                                   a scan. CI runs it before the scan below.
#   check_core_boundary_discovery_selftest.py
#                                   exercises discovery on synthetic trees. A policy gap
#                                   and a coverage gap fail for different reasons, and a
#                                   reader that quietly stops covering a library is the
#                                   second kind. CI runs it too.

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_DIR = REPO_ROOT / "src" / "core"


# The policy — which headers the core may include, which symbols it may import, and the
# clause behind each — lives next door so that widening it is a diff to one reviewable
# file. This module reads the tree and the archive; it decides nothing.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_core_boundary_discovery import (  # noqa: E402
    core_library_targets,
    find_libraries,
)
from check_core_boundary_policy import (  # noqa: E402
    ALLOWED_ANGLE_INCLUDES,
    ALLOWED_QUOTED_PREFIXES,
    EXCLUDED_ANGLE_INCLUDES,
    INCLUDE_RE,
    SOURCE_SUFFIXES,
    classify,
)


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


def angle_include_rule(header: str) -> str:
    """Why this header is not admitted — and, crucially, which kind of "not".

    A contributor who trips this gate has two possible next moves and they are opposites:
    rewrite the code, or widen the policy. Telling them apart is the whole reason the
    policy keeps a refusal list beside its allowlist. Before that, every absence read the
    same, so an honest std::optional<Event> in the scheduler and a std::vector in the core
    produced the same message.
    """
    refused = EXCLUDED_ANGLE_INCLUDES.get(header)
    if refused:
        return (
            f"ADR-PORT-04 D1 — <{header}> is kept out of the core on purpose: {refused} "
            "This absence is policy rather than an omission, so what clears it is a "
            "change to the code, not an entry in check_core_boundary_policy.py."
        )
    return (
        "ADR-PORT-04 D1 — the core depends on nothing beyond the admissible subset of "
        f"the C++23 standard library, and <{header}> has not been weighed against that "
        "subset in either direction. This is an omission rather than a refusal. If the "
        "header survives D1's subtraction, what clears it is a reviewed entry in "
        "ALLOWED_ANGLE_INCLUDES citing the clause, and it wants saying out loud in the "
        "pull request. If it does not survive, it belongs in EXCLUDED_ANGLE_INCLUDES with "
        "the reason, so that the next contributor is told rather than left guessing."
    )


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
                            angle_include_rule(header),
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


def symbols_nm(nm: str, library: Path) -> tuple[list[str], int]:
    """Return (imported symbols, total symbols seen).

    The total is a liveness probe. `nm -u` returning nothing is the expected output for a
    core that imports nothing, so it cannot on its own distinguish a clean library from a
    reader that parsed no archive at all. The core always *defines* at least
    linkedVersionString, so a total of zero means the reader failed silently.
    """
    undefined = subprocess.run(
        [nm, "-u", str(library)], capture_output=True, text=True, timeout=300
    )
    if undefined.returncode != 0:
        raise RuntimeError(f"{nm} -u failed: {undefined.stderr.strip()}")
    symbols: list[str] = []
    for line in undefined.stdout.splitlines():
        line = line.strip()
        if not line or line.endswith(":"):
            continue
        # GNU nm -u prints "        U symbol"; BSD/Apple nm -u prints bare names.
        symbols.append(line.split()[-1])

    every = subprocess.run([nm, str(library)], capture_output=True, text=True, timeout=300)
    if every.returncode != 0:
        raise RuntimeError(f"{nm} failed: {every.stderr.strip()}")
    total = 0
    for line in every.stdout.splitlines():
        line = line.strip()
        if line and not line.endswith(":"):
            total += 1
    return symbols, total


def symbols_dumpbin(dumpbin: str, library: Path) -> tuple[list[str], int]:
    """Return (imported symbols, total symbol-table rows). See symbols_nm on the total."""
    out = subprocess.run(
        [dumpbin, "/symbols", "/nologo", str(library)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if out.returncode != 0:
        raise RuntimeError(f"dumpbin failed: {out.stderr.strip()}")
    symbols: list[str] = []
    total = 0
    for line in out.stdout.splitlines():
        # A COFF symbol-table row reads, with columns:
        #   00F 00000000 UNDEF  notype ()    External     | ?name@@YAXXZ
        if "|" not in line:
            continue
        total += 1
        if " UNDEF " not in line or "External" not in line:
            continue
        name = line.rsplit("|", 1)[-1].strip()
        if name:
            # dumpbin appends a demangled form in parentheses for some symbols; the raw
            # decorated name is the first token and is what the fragments match.
            symbols.append(name.split()[0])
    return symbols, total


def check_symbols(build_dir: Path | None) -> tuple[list[Finding], str, bool]:
    """Return (findings, status line, ran).

    `ran` is False whenever the symbol half did not actually inspect every core library —
    no library target declared, a target declared in a shape no reader opens, a target
    declared but not built, no reader, a reader that errored, or a reader that returned an
    empty symbol table. --require-symbols turns any of those into a failure, because in CI
    every one of them is a hole in the gate rather than a platform limitation.

    "every core library" rather than "the library": partial coverage reported as a pass is
    the same defect as no coverage reported as a pass, so one unreadable target stops the
    half instead of quietly shrinking it.
    """
    search_root = build_dir if build_dir else REPO_ROOT / "build"

    targets, unreadable = core_library_targets(CORE_DIR, REPO_ROOT)
    if unreadable:
        return [], (
            "NOT RUN — a library target declared under src/core/ cannot be inspected by "
            "this check, so the symbol half would cover less of the core than the include "
            "half without saying so: " + "; ".join(unreadable)
        ), False
    if not targets:
        return [], (
            "NOT RUN — no library target compiles anything under src/core/. The symbol "
            "half derives its subject from add_library(), so finding none means either "
            "the core declares no library or this scan can no longer read the "
            "declaration. Neither means there is nothing to check."
        ), False

    libraries, missing = find_libraries(targets, REPO_ROOT, build_dir)
    if missing:
        return [], (
            "NOT RUN — declared under src/core/ but not built under "
            f"{search_root}: {', '.join(missing)}. Build first: "
            "cmake --preset dev && cmake --build --preset dev"
        ), False

    nm = shutil.which("nm") or shutil.which("llvm-nm")
    if nm:
        tool_name = f"nm ({nm})"

        def read(library: Path) -> tuple[list[str], int]:
            return symbols_nm(nm, library)

    else:
        dumpbin = find_dumpbin()
        if dumpbin is None:
            return [], (
                "NOT RUN — neither nm nor dumpbin was found on this host, so the imported "
                "symbols of the core could not be read. The include half above still ran."
            ), False
        tool_name = f"dumpbin /symbols ({dumpbin})"

        def read(library: Path) -> tuple[list[str], int]:
            return symbols_dumpbin(dumpbin, library)

    findings: list[Finding] = []
    # Keyed on the library too: the same symbol imported by two core libraries is two
    # findings, at two places a reader can go and look.
    seen: set[tuple[str, str, str]] = set()
    per_library: list[str] = []
    imported = 0

    for target in targets:
        library = libraries[target]
        rel = (
            library.relative_to(REPO_ROOT).as_posix()
            if library.is_relative_to(REPO_ROOT)
            else str(library)
        )
        try:
            symbols, total = read(library)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return [], f"NOT RUN — {tool_name} could not read {library.name}: {exc}", False

        if total == 0:
            # Zero *imported* symbols is the expected, healthy result for a core library,
            # so it cannot double as evidence that the reader worked. Zero symbols of any
            # kind cannot be right: a library that was built and linked into the tree
            # defines something. That is a reader which parsed nothing while exiting 0 —
            # a degraded gate, not a clean tree.
            return [], (
                f"NOT RUN — {tool_name} returned an empty symbol table for {rel}, "
                "including defined symbols. A built core library defines at least one, so "
                "the reader did not parse the archive."
            ), False

        imported += len(symbols)
        per_library.append(f"{target}: {len(symbols)} imported of {total} symbols, {rel}")
        for raw in symbols:
            for rule, clause in classify(raw):
                if (rel, raw, rule) in seen:
                    continue
                seen.add((rel, raw, rule))
                findings.append(Finding(rel, clause, f"the core imports '{raw}' — {rule}"))

    noun = "library" if len(targets) == 1 else "libraries"
    # Every library is listed, not just the offending ones. The count is the evidence that
    # coverage did not shrink, and it is only evidence if it is printed on a pass too.
    status = "\n".join(
        [f"{imported} imported across {len(targets)} core {noun}, read with {tool_name}"]
        + [f"            {line}" for line in per_library]
    )
    return findings, status, True


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
        help="Fail unless the symbol half actually inspected the library. Any reason it "
        "did not — no library, no nm or dumpbin, a reader that errored, a reader that "
        "returned an empty symbol table — is a failure. CI passes this: there, a symbol "
        "half that did not run is a hole in the gate, never a platform limitation. "
        "Without the flag those same cases are reported and tolerated, which is what "
        "makes a local run useful on a host with no symbol reader.",
    )
    args = parser.parse_args()

    if not CORE_DIR.is_dir():
        print(f"::error::src/core not found at {CORE_DIR}", file=sys.stderr)
        return 2

    include_findings, scanned = check_includes()
    symbol_findings, symbol_status, symbols_ran = check_symbols(args.build_dir)

    print("meta-amiga — freestanding-core boundary check (ADR-PORT-04 D1)")
    print(f"  includes: {scanned} files scanned under src/core/")
    print(f"  symbols:  {symbol_status}")

    findings = include_findings + symbol_findings
    if not symbols_ran and args.require_symbols:
        findings.append(
            Finding(
                ".github/scripts/" + Path(__file__).name,
                "ADR-PORT-04 D1 is enforced over includes *and* symbols; half a check "
                "reported as a pass is the convention this test exists to replace. The "
                "status line above says which half did not run, and why.",
                "the symbol half did not inspect every core library, and "
                "--require-symbols was given",
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
