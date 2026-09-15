#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Which libraries the symbol half of the freestanding-core boundary check must read.
#
# Both halves have to reach the same code. The include half globs a directory,
# src/core/**. The symbol half used to read one hardcoded library name and then, among the
# files matching it, keep only the newest — two independent reductions to a single object,
# neither of which announced itself. When the 68k core lands as meta-amiga-cpu under
# src/core/cpu/, the include half keeps scanning it and the symbol half stops, with
# nothing in the output saying coverage shrank. The leg stays green over the newest and
# most safety-relevant code in the repo.
#
# So the symbol half now derives its subject from where the include half derives its own:
# the library targets that COMPILE sources under src/core/**, wherever those targets are
# declared. Adding add_library(meta-amiga-cpu ...) over core sources brings that library
# under the symbol scan with no edit to this file and none to the policy beside it.
#
# Keying on the declaration SITE was the first shape of this, and review showed it was
# narrow twice over: a declaration moved into an include()d .cmake vanished, and so did
# one written in src/CMakeLists.txt over core/ sources. Both are ordinary refactoring,
# and both narrowed the symbol half without a word — the defect this file exists to make
# impossible, surviving inside the fix for it. Hence two changes: every .cmake file is
# read, so include() never has to be evaluated; and core-ness is decided by which
# sources a target compiles, not by where it was written.
#
# The selection rule changed with it, and that change is half the fix rather than a side
# effect of it. max(key=mtime) survives for exactly the job it was written for — choosing
# between several BUILDS of the SAME target, so that with dev/ and asan/ both configured
# the one just built is the one the caller means. It no longer chooses between TARGETS.
# Every core library declared is a core library read, every run.
#
# Discovery starts from the declaration rather than from the build tree, and that is what
# keeps it honest. The obvious repair — glob build/ for anything library-shaped and scan
# what turns up — reintroduces the silent-pass hole the NOT RUN machinery exists to close,
# because a glob that matches nothing is indistinguishable from a clean tree. Starting from add_library() means "declared but
# not built" and "declared in a shape no reader opens" are both things this check can see,
# and both say NOT RUN with the target named, which --require-symbols turns red.
#
# check_core_boundary_discovery_selftest.py exercises all of this on synthetic trees.
from __future__ import annotations

import re
from pathlib import Path


# add_library(<name> [type] ...). CMake commands are case-insensitive, and the argument
# list cannot contain ')', so a character class carries the continuation lines an
# add_library is normally written over.
ADD_LIBRARY_RE = re.compile(r"\badd_library\s*\(\s*([^\s()]+)([^)]*)\)", re.IGNORECASE)

# Declared under src/core/ but producing no archive, by design rather than by omission.
# The type keyword is the second argument, so it is matched there and not anywhere in the
# argument list: a source file named interface.cpp must not read as an INTERFACE library.
NO_ARTIFACT_TYPES = ("ALIAS", "INTERFACE")

# Real core code, in a shape neither nm nor dumpbin opens as an archive. Named rather than
# skipped — a quiet skip here is precisely the defect this section exists to remove.
UNREADABLE_TYPES = ("OBJECT",)


def artifact_names(target: str) -> tuple[str, ...]:
    """The archive spellings one static library target produces across the platforms."""
    return (f"lib{target}.a", f"{target}.lib", f"lib{target}.lib")


# Directories that hold build output or tooling rather than declarations.
SKIP_DIRS = frozenset({"build", "out", ".git", ".claude", "node_modules", ".cache"})

# add_library's second argument, when it is a type rather than the first source.
LIBRARY_TYPES = ("STATIC", "SHARED", "MODULE", "OBJECT", "INTERFACE", "ALIAS", "UNKNOWN")

# Translation units. Headers are not compiled into an archive, so they are not evidence
# that a target is missing.
TU_SUFFIXES = (".cpp", ".cc", ".cxx")


def cmake_files(repo_root: Path):
    """Every CMake file in the tree — CMakeLists.txt and the .cmake files they include.

    Reading the .cmake files too is what makes include() a non-event: the declaration is
    in a file this scan opens either way, so it never has to evaluate an include() to find
    one. Build trees are skipped; a configured build contains copies that would be counted
    twice and CMake's own modules, which declare nothing of ours.
    """
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name != "CMakeLists.txt" and path.suffix != ".cmake":
            continue
        parts = path.relative_to(repo_root).parts[:-1]
        if any(part in SKIP_DIRS or part.startswith("cmake-build-") for part in parts):
            continue
        yield path


def core_library_targets(core_dir: Path, repo_root: Path) -> tuple[list[str], list[str]]:
    """Return (targets to scan, reasons the set cannot be trusted).

    A target is a core target when it COMPILES core sources, not when it happens to be
    declared in a particular file. Keying on the declaration site was the first shape of
    this function and it was too narrow twice over: an add_library moved into an
    include()d .cmake vanished from the scan, and so did one declared in src/CMakeLists.txt
    over core/ sources. Both are ordinary CMake refactoring, both left the symbol half
    covering less than the include half, and neither said anything — the very shape this
    check exists to make impossible.

    The second list is the backstop, and it is what makes this honest rather than merely
    wider. Parsing add_library() will always be an approximation of CMake, so instead of
    claiming to find every declaration, this asserts something checkable about the result:
    every translation unit under src/core/ must be claimed by some discovered target. A
    declaration this scan failed to find leaves its sources unclaimed, and an unclaimed
    core source is reported by name — whatever the reason it was missed, including reasons
    nobody has thought of. Coverage cannot narrow without that check noticing.
    """
    core_dir = core_dir.resolve()
    scannable: list[str] = []
    unreadable: list[str] = []
    claimed: set[Path] = set()
    unresolved_targets: list[str] = []

    for path in cmake_files(repo_root):
        text = "\n".join(
            line.split("#", 1)[0]
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        )
        try:
            where = path.relative_to(repo_root).as_posix()
        except ValueError:
            where = str(path)

        for match in ADD_LIBRARY_RE.finditer(text):
            name, rest = match.group(1), match.group(2)
            args = rest.split()
            kind = args[0] if args and args[0] in LIBRARY_TYPES else ""
            if kind in NO_ARTIFACT_TYPES or "IMPORTED" in args:
                continue

            core_sources: set[Path] = set()
            unresolved = False
            for arg in args[1:] if kind else args:
                arg = arg.strip('"\'')
                if not arg or arg in ("EXCLUDE_FROM_ALL",):
                    continue
                if "$" in arg:
                    unresolved = True
                    continue
                candidate = (path.parent / arg).resolve()
                if candidate == core_dir or core_dir in candidate.parents:
                    core_sources.add(candidate)

            declared_in_core = path.parent.resolve() == core_dir or core_dir in path.parent.resolve().parents
            if not core_sources and not declared_in_core:
                continue  # some other module's library; not this gate's business

            if "${" in name or "@" in name:
                unreadable.append(
                    f"{name} in {where} — the target's name is built from a CMake "
                    "variable, which this scan cannot expand, so it cannot say which "
                    "archive to read"
                )
                continue
            if kind in UNREADABLE_TYPES:
                unreadable.append(
                    f"{name} in {where} — an {kind} library produces object files rather "
                    "than an archive, and neither reader here opens one"
                )
                continue

            if unresolved:
                unresolved_targets.append(f"{name} in {where}")
            claimed.update(core_sources)
            scannable.append(name)

    orphans = sorted(
        path.relative_to(core_dir).as_posix()
        for path in core_dir.rglob("*")
        if path.is_file() and path.suffix in TU_SUFFIXES and path.resolve() not in claimed
    )
    if unresolved_targets and orphans:
        # The source list could not be expanded, so an unclaimed file proves nothing.
        # Say that, rather than reporting orphans that may well be accounted for.
        unreadable.append(
            "the source list of "
            + ", ".join(unresolved_targets)
            + " uses a CMake variable this scan cannot expand, so it cannot confirm that "
            "every core source is compiled into a library it scans"
        )
    elif orphans:
        unreadable.append(
            "under src/core/ but compiled into no library this scan found: "
            + ", ".join(orphans)
            + " — the add_library() declaring them was not discovered, so the symbol half "
            "would cover less of the core than the include half"
        )

    return list(dict.fromkeys(scannable)), unreadable


def find_libraries(
    targets: list[str], repo_root: Path, build_dir: Path | None = None
) -> tuple[dict[str, Path], list[str]]:
    """Return (target -> archive to read, targets with no archive built).

    Newest wins WITHIN a target: with several presets configured, the build just made is
    the one the caller means. It never reduces the set of targets — that reduction was the
    coverage hole, and the missing list carries what could not be found instead of the
    result quietly getting smaller.
    """
    roots = [build_dir] if build_dir else [repo_root / "build"]
    found: dict[str, Path] = {}
    missing: list[str] = []
    for target in targets:
        candidates: list[Path] = []
        for root in roots:
            if root is None or not root.is_dir():
                continue
            for name in artifact_names(target):
                candidates.extend(root.rglob(name))
        if not candidates:
            missing.append(target)
            continue
        found[target] = max(candidates, key=lambda p: p.stat().st_mtime)
    return found, missing
