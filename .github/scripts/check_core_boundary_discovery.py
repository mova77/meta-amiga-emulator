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
# the library targets DECLARED under src/core/**. Adding add_library(meta-amiga-cpu ...)
# in src/core/cpu/CMakeLists.txt brings that library under the symbol scan with no edit to
# this file and none to the policy beside it.
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


def core_library_targets(core_dir: Path, repo_root: Path) -> tuple[list[str], list[str]]:
    """Return (targets to scan, reasons a declared target cannot be scanned).

    Reads every CMakeLists.txt under src/core/**. The second list is what makes deriving
    the subject safe: anything declared there that this check cannot open is reported by
    name, so the symbol half's coverage cannot quietly become narrower than the include
    half's.
    """
    scannable: list[str] = []
    unreadable: list[str] = []
    for path in sorted(core_dir.rglob("CMakeLists.txt")):
        # A commented-out add_library is not a declaration. Stripping '#' to end of line
        # is enough for CMake as this project writes it.
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
            kind = args[0] if args else ""
            if kind in NO_ARTIFACT_TYPES or "IMPORTED" in args:
                continue
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
            scannable.append(name)
    # CMake forbids declaring a target twice; dedupe anyway, so a malformed tree costs a
    # repeated scan rather than a confusing count.
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
