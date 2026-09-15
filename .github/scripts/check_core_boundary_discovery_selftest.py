#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Self-test for library discovery in check_core_boundary.py.
#
# The architecture test has three kinds of bug, and each needs a different thing to catch
# it. The archive reader breaking is caught by a planted breach in CI. A denylist that does
# not name the symbol an escape imports is caught by check_core_boundary_selftest.py. The
# third is this file's subject: the check reading a SMALLER core than the one that exists,
# and reporting that as a pass.
#
# That bug has no symptom. A planted breach still fails, the self-test still passes, the
# leg still goes green — it is green over less code than it was yesterday, and nothing in
# the output says so. So it is demonstrated rather than asserted: every case below builds
# a real source tree and a real build tree on disk, declares a library in it, and checks
# that discovery picks the library up. The case that matters most is the one that adds a
# second library to a tree that had one, which is what src/core/cpu/ will be.
#
# No compiler and no toolchain: the archives here are empty files, because discovery is
# about WHICH files the symbol half opens, not what is inside them. What is inside them is
# check_core_boundary_selftest.py's subject and the planted breach's.
#
#     python3 .github/scripts/check_core_boundary_discovery_selftest.py

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_core_boundary_discovery import (  # noqa: E402
    artifact_names,
    core_library_targets,
    find_libraries,
)

FAILURES: list[str] = []


def check(condition: bool, what: str) -> None:
    if not condition:
        FAILURES.append(what)


def declare(core: Path, subdir: str, body: str) -> None:
    """Write a CMakeLists.txt under src/core/<subdir>/, as a contributor would."""
    directory = core / subdir if subdir else core
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "CMakeLists.txt").write_text(body, encoding="utf-8")


def source(core: Path, relative: str) -> None:
    """Write a translation unit under src/core/, as a contributor would."""
    path = core / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("namespace meta::amiga::core {}\n", encoding="utf-8")


def build(root: Path, preset: str, relative: str, target: str) -> Path:
    """Put an archive where a preset build of `target` would put one."""
    directory = root / "build" / preset / relative
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / artifact_names(target)[0]
    archive.write_bytes(b"")
    return archive


CORE_CMAKE = """
add_library(meta-amiga-core STATIC
    version.cpp)

add_library(meta-amiga::core ALIAS meta-amiga-core)
"""

CPU_CMAKE = """
# ADR-CPU-02: the 68k core, landing beside the rest of src/core/.
add_library(meta-amiga-cpu STATIC
    decode.cpp
    execute.cpp)
"""


def case_new_library_is_covered_the_day_it_is_declared() -> None:
    """The story's scenario, end to end, and the reason this file exists.

    A tree with one core library gains a second one — no edit to check_core_boundary.py,
    none to check_core_boundary_policy.py — and the symbol half covers both.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", CORE_CMAKE)
        build(root, "dev", "src/core", "meta-amiga-core")

        before, unreadable = core_library_targets(core, root)
        check(before == ["meta-amiga-core"], f"one declared library: got {before}")
        check(not unreadable, f"nothing unreadable yet: {unreadable}")

        # The 68k core lands. This is the whole diff a contributor writes.
        declare(core, "cpu", CPU_CMAKE)
        build(root, "dev", "src/core/cpu", "meta-amiga-cpu")

        after, unreadable = core_library_targets(core, root)
        check(
            sorted(after) == ["meta-amiga-core", "meta-amiga-cpu"],
            f"the new library is discovered with no policy edit: got {after}",
        )
        check(not unreadable, f"nothing unreadable after the CPU lands: {unreadable}")

        found, missing = find_libraries(after, root)
        check(not missing, f"both archives located: missing {missing}")
        check(
            sorted(found) == ["meta-amiga-core", "meta-amiga-cpu"],
            f"both libraries are scanned, not one of them: got {sorted(found)}",
        )


def case_declared_but_not_built_is_not_run() -> None:
    """AC4, and the reason discovery starts from the declaration.

    Globbing the build tree would find one archive here and scan it happily. Starting from
    add_library() makes the absent one a named NOT RUN instead.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", CORE_CMAKE)
        declare(core, "cpu", CPU_CMAKE)
        build(root, "dev", "src/core", "meta-amiga-core")  # the CPU one is NOT built

        targets, _ = core_library_targets(core, root)
        found, missing = find_libraries(targets, root)
        check(missing == ["meta-amiga-cpu"], f"the unbuilt library is named: {missing}")
        check(list(found) == ["meta-amiga-core"], f"the built one was found: {list(found)}")


def case_nothing_built_and_nothing_declared() -> None:
    """An empty result is a NOT RUN, from either direction — never a clean pass."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", CORE_CMAKE)

        _, missing = find_libraries(["meta-amiga-core"], root)
        check(missing == ["meta-amiga-core"], f"unbuilt tree yields missing: {missing}")

        core_empty = root / "empty" / "src" / "core"
        core_empty.mkdir(parents=True)
        targets, unreadable = core_library_targets(core_empty, root)
        check(targets == [], f"no declaration means no targets: {targets}")
        check(unreadable == [], f"and nothing unreadable either: {unreadable}")


def case_every_target_is_scanned_across_presets() -> None:
    """The selection rule, in both of its halves.

    Newest wins WITHIN a target — dev/ and asan/ both configured, one archive read for
    that target. It does NOT reduce across targets: two targets, two archives. Before the
    fix this whole tree resolved to exactly one file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", CORE_CMAKE)
        declare(core, "cpu", CPU_CMAKE)

        for preset in ("asan", "dev"):
            build(root, preset, "src/core", "meta-amiga-core")
            build(root, preset, "src/core/cpu", "meta-amiga-cpu")
        # Make "newest" unambiguous rather than dependent on filesystem timestamp
        # granularity: dev/ is rebuilt last, so dev/ is what each target resolves to.
        later = time.time() + 10
        for relative, target in (
            ("src/core", "meta-amiga-core"),
            ("src/core/cpu", "meta-amiga-cpu"),
        ):
            os.utime(root / "build" / "dev" / relative / artifact_names(target)[0], (later, later))

        targets, _ = core_library_targets(core, root)
        found, missing = find_libraries(targets, root)
        check(not missing, f"nothing missing: {missing}")
        check(len(found) == 2, f"one archive per target, not one in total: {found}")
        for target, path in found.items():
            check(
                path.relative_to(root / "build").parts[0] == "dev",
                f"{target} resolved to the newest build of itself, got {path}",
            )


def case_declarations_that_produce_no_archive_are_skipped() -> None:
    """ALIAS, INTERFACE and IMPORTED produce nothing to read, by design.

    The `interface.cpp` source is the point of the last one: the type keyword is read as
    the second argument, never as a word appearing somewhere in the argument list.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(
            core,
            "",
            """
add_library(meta-amiga-core STATIC
    version.cpp
    interface.cpp)
add_library(meta-amiga::core ALIAS meta-amiga-core)
add_library(meta-amiga-core-headers INTERFACE)
add_library(vendored-thing STATIC IMPORTED)
# add_library(commented-out STATIC nope.cpp)
""",
        )
        targets, unreadable = core_library_targets(core, root)
        check(
            targets == ["meta-amiga-core"],
            f"only the real archive-producing target: got {targets}",
        )
        check(not unreadable, f"none of those is unreadable: {unreadable}")


def case_declarations_this_check_cannot_open_are_named() -> None:
    """A target that exists but cannot be read stops the half; it never shrinks it.

    Both of these are honest CMake. Neither yields an archive this check can open, and the
    safe response to that is a NOT RUN naming the target — the same rule as an unbuilt one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(
            core,
            "",
            """
add_library(meta-amiga-core STATIC version.cpp)
add_library(meta-amiga-chipset OBJECT blitter.cpp)
add_library(${GENERATED_TARGET} STATIC generated.cpp)
""",
        )
        targets, unreadable = core_library_targets(core, root)
        check(targets == ["meta-amiga-core"], f"the readable one is kept: {targets}")
        check(len(unreadable) == 2, f"both unreadable ones are reported: {unreadable}")
        check(
            any("meta-amiga-chipset" in reason for reason in unreadable),
            f"the OBJECT library is named: {unreadable}",
        )
        check(
            any("GENERATED_TARGET" in reason for reason in unreadable),
            f"the variable-named target is named: {unreadable}",
        )


def case_declaration_moved_into_an_included_cmake_file() -> None:
    """Review finding. An add_library moved into an include()d .cmake file vanished.

    Ordinary CMake refactoring, and before this the scan returned one target and no
    complaint — the symbol half silently covering half the core it used to. This is the
    reason discovery reads every .cmake file rather than only CMakeLists.txt: an include()
    never has to be evaluated, because the declaration is in a file already being read.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", "add_library(meta-amiga-core STATIC version.cpp)\ninclude(cpu.cmake)\n")
        (core / "cpu.cmake").write_text(
            "add_library(meta-amiga-cpu STATIC cpu/decode.cpp)\n", encoding="utf-8"
        )
        source(core, "version.cpp")
        source(core, "cpu/decode.cpp")

        targets, unreadable = core_library_targets(core, root)
        check(
            sorted(targets) == ["meta-amiga-core", "meta-amiga-cpu"],
            f"the library declared in the included file is found: got {targets}",
        )
        check(not unreadable, f"and nothing is left unaccounted for: {unreadable}")


def case_declaration_outside_src_core_over_core_sources() -> None:
    """Review finding. A core library declared in src/CMakeLists.txt vanished too.

    What makes a library this gate's business is which sources it COMPILES, not where it
    happens to be declared. Keying on the declaration site was the narrower rule, and this
    is the case that showed it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", "add_library(meta-amiga-core STATIC version.cpp)\n")
        (root / "src" / "CMakeLists.txt").write_text(
            "add_library(meta-amiga-cpu STATIC core/cpu/decode.cpp)\n", encoding="utf-8"
        )
        source(core, "version.cpp")
        source(core, "cpu/decode.cpp")

        targets, unreadable = core_library_targets(core, root)
        check(
            sorted(targets) == ["meta-amiga-core", "meta-amiga-cpu"],
            f"a core library declared elsewhere is still a core library: got {targets}",
        )
        check(not unreadable, f"and nothing is left unaccounted for: {unreadable}")
        check(
            "test-helpers" not in targets,
            "a library outside the core is still none of this gate's business",
        )


def case_an_unclaimed_core_source_is_reported() -> None:
    """The backstop, and the only reason the two cases above can be called closed.

    Parsing add_library() will always approximate CMake, so rather than claim every
    declaration is found, discovery asserts something checkable about the result: every
    translation unit under src/core/ is compiled into a library it scans. A declaration
    missed for ANY reason — including one nobody has thought of — leaves its sources
    unclaimed, and an unclaimed core source is reported by name.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", "add_library(meta-amiga-core STATIC version.cpp)\n")
        source(core, "version.cpp")
        source(core, "cpu/decode.cpp")  # compiled by nothing this scan can see

        targets, unreadable = core_library_targets(core, root)
        check(targets == ["meta-amiga-core"], f"the visible target is still found: {targets}")
        check(len(unreadable) == 1, f"exactly one complaint: {unreadable}")
        check(
            any("cpu/decode.cpp" in reason for reason in unreadable),
            f"and it names the unaccounted source: {unreadable}",
        )


def case_a_source_list_that_cannot_be_expanded_says_so() -> None:
    """An unexpandable source list makes an unclaimed file prove nothing, so say that.

    Reporting orphans here would be a red leg for files that are very probably compiled
    after all. The honest report is that the scan cannot confirm coverage — which is a
    NOT RUN either way, but one a reader can act on.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        core = root / "src" / "core"
        declare(core, "", "add_library(meta-amiga-core STATIC ${CORE_SOURCES})\n")
        source(core, "version.cpp")
        source(core, "cpu/decode.cpp")

        _targets, unreadable = core_library_targets(core, root)
        check(len(unreadable) == 1, f"one complaint, not one per file: {unreadable}")
        check(
            "cannot expand" in unreadable[0] and "decode.cpp" not in unreadable[0],
            f"it blames the unexpandable list, not the files: {unreadable}",
        )


CASES = (
    case_new_library_is_covered_the_day_it_is_declared,
    case_declared_but_not_built_is_not_run,
    case_nothing_built_and_nothing_declared,
    case_every_target_is_scanned_across_presets,
    case_declarations_that_produce_no_archive_are_skipped,
    case_declarations_this_check_cannot_open_are_named,
    case_declaration_moved_into_an_included_cmake_file,
    case_declaration_outside_src_core_over_core_sources,
    case_an_unclaimed_core_source_is_reported,
    case_a_source_list_that_cannot_be_expanded_says_so,
)


def main() -> int:
    for case in CASES:
        case()

    print(f"check_core_boundary discovery self-test — {len(CASES)} cases")
    if FAILURES:
        for failure in FAILURES:
            print(f"::error::{failure}")
            print(f"  {failure}")
        print(f"FAIL — {len(FAILURES)} expectation(s) wrong.")
        return 1
    print("PASS — discovery covers every declared core library.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
