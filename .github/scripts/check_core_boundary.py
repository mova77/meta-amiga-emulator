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
# The difference is here, inside the script, not in the CI matrix. If the half cannot
# actually inspect the library — no tool, a tool that errors, a tool that returns an empty
# symbol table — it says NOT RUN, with the reason and the reader it tried. Under CI's
# --require-symbols that is a failure, because a gate that quietly enforces half of itself
# is worse than no gate: it reads as a pass. Without the flag it is reported and tolerated,
# so a local run on a host with no symbol reader still gets the include half.
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
# CI adds --require-symbols, which turns any NOT RUN into a failure.
#
# Three files, because they fail for different reasons and are reviewed by different
# people:
#   check_core_boundary.py          reads the tree and the archive — this file
#   check_core_boundary_policy.py   what is allowed and what is not, with the clause
#                                   behind each entry; widening it is a diff to that file
#   check_core_boundary_selftest.py asserts the policy's verdict on known symbol
#                                   spellings, so a gap fails a test rather than passing
#                                   a scan. CI runs it before the scan below.

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
from check_core_boundary_policy import (  # noqa: E402
    ALLOWED_ANGLE_INCLUDES,
    ALLOWED_QUOTED_PREFIXES,
    INCLUDE_RE,
    SOURCE_SUFFIXES,
    classify,
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
                            f"<{header}> is not on the allowlist in "
                            "check_core_boundary_policy.py; adding it there is a policy "
                            "change and wants saying out loud in the pull request.",
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

    `ran` is False whenever the symbol half did not actually inspect the library — no
    library, no reader, a reader that errored, or a reader that returned an empty symbol
    table. --require-symbols turns any of those into a failure, because in CI every one of
    them is a hole in the gate rather than a platform limitation.
    """
    library = find_library(build_dir)
    if library is None:
        return [], (
            "NOT RUN — no built meta-amiga-core library found under "
            f"{(build_dir or REPO_ROOT / 'build')}. Build first: "
            "cmake --preset dev && cmake --build --preset dev"
        ), False

    nm = shutil.which("nm") or shutil.which("llvm-nm")
    reader = None
    if nm:
        reader = (f"nm ({nm})", lambda: symbols_nm(nm, library))
    else:
        dumpbin = find_dumpbin()
        if dumpbin:
            reader = (f"dumpbin /symbols ({dumpbin})", lambda: symbols_dumpbin(dumpbin, library))

    if reader is None:
        return [], (
            "NOT RUN — neither nm nor dumpbin was found on this host, so the imported "
            "symbols of the core could not be read. The include half above still ran."
        ), False

    tool_name, read = reader
    try:
        symbols, total = read()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return [], f"NOT RUN — {tool_name} could not read {library.name}: {exc}", False

    rel = (
        library.relative_to(REPO_ROOT).as_posix()
        if library.is_relative_to(REPO_ROOT)
        else str(library)
    )

    if total == 0:
        # Zero *imported* symbols is the expected, healthy result for this core, so it
        # cannot double as evidence that the reader worked. Zero symbols of any kind
        # cannot be right: the library defines linkedVersionString at minimum. That is a
        # reader which parsed nothing while exiting 0 — a degraded gate, not a clean tree.
        return [], (
            f"NOT RUN — {tool_name} returned an empty symbol table for {rel}, including "
            "defined symbols. The library always defines at least one, so the reader did "
            "not parse the archive."
        ), False

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for raw in symbols:
        for rule, clause in classify(raw):
            if (raw, rule) in seen:
                continue
            seen.add((raw, rule))
            findings.append(Finding(rel, clause, f"the core imports '{raw}' — {rule}"))
    return (
        findings,
        f"{len(symbols)} imported of {total} symbols, read with {tool_name} from {rel}",
        True,
    )


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
                "the symbol half did not inspect the library, and --require-symbols "
                "was given",
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
