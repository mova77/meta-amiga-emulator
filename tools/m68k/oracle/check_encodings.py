#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Oracle 1: the M68k backend's encodings against the 68000 Programmer's Reference Manual.

kernel.expected holds, for each instruction of kernel.s, the encoding derived by hand from
the manual. This script
  1. assembles kernel.s and requires the bytes to equal the expected encodings exactly;
  2. feeds each expected encoding back through the backend's disassembler and requires the
     expected text (an instruction the backend cannot disassemble is marked "-", and one it
     is known to disassemble wrongly "xfail:", which turns into a failure the day it is fixed);
  3. compiles the colour-loop C and requires the manual's encoding of a word store to an
     absolute custom-chip address to appear in the object;
  4. assembles single instructions from probes.expected, to track what the assembler can do.

Exit 0 pass, 1 mismatch. Writes kernel.bin and kernel.syms to --out for oracle 3.

Usage: check_encodings.py [--bin DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAMS = HERE.parent / "programs"


def tool(bindir: Path, *names: str) -> str:
    for n in names:
        if (bindir / n).exists():
            return str(bindir / n)
    sys.exit(f"missing {names[0]} in {bindir}")


def run(*cmd: str, stdin: str | None = None) -> str:
    return subprocess.run(cmd, input=stdin, check=True, capture_output=True, text=True).stdout


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_expected():
    rows = []
    for line in (HERE / "kernel.expected").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        enc, dis, src = (f.strip() for f in line.split("|", 2))
        rows.append((bytes.fromhex(enc.replace(" ", "")), dis, src))
    return rows


def check_kernel(a, rows, obj: Path, oc: str, mc: str, nm: str) -> int:
    """Steps 1 and 2: compare the assembled bytes, then round-trip the disassembler.
    Returns the number of failures."""
    fails = 0
    run(oc, "-O", "binary", "-j", ".text", str(obj), str(a.out / "kernel.bin"))
    got = (a.out / "kernel.bin").read_bytes()
    want = b"".join(r[0] for r in rows)
    pos = 0
    for enc, _dis, src in rows:
        if got[pos:pos + len(enc)] != enc:
            fails += 1
            print(f"ENCODING  {src!r}: expected {enc.hex().upper()}, "
                  f"assembled {got[pos:pos + len(enc)].hex().upper()}")
        pos += len(enc)
    if len(got) != len(want):
        fails += 1
        print(f"LENGTH    assembled {len(got)} bytes, expected {len(want)}")
    syms = {}
    for line in run(nm, str(obj)).splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    (a.out / "kernel.syms").write_text("".join(f"{k}=0x{v:x}\n" for k, v in sorted(syms.items())))
    print(f"assembly: {len(rows)} instructions, {len(want)} bytes, "
          f"{'identical to the manual' if got == want else 'DIFFERENT'}")

    xfails = 0
    for enc, dis, src in rows:
        if dis == "-":
            continue
        known_bad = dis.startswith("xfail:")
        want_text = norm(dis.removeprefix("xfail:"))
        text = " ".join(f"0x{b:02x}" for b in enc)
        out = run(mc, "--disassemble", "--triple=m68k", "-mcpu=M68000", stdin=text)
        lines = [norm(l) for l in out.splitlines() if l.strip() and l.strip() != ".text"]
        shown = lines[0] if lines else "<no output>"
        ok = shown == want_text
        if known_bad and not ok:
            xfails += 1
            print(f"XFAIL     {enc.hex().upper()}: disassembles as {shown!r}, "
                  f"the manual says {want_text!r}")
        elif known_bad and ok:
            fails += 1
            print(f"XPASS     {enc.hex().upper()} now disassembles correctly; remove the xfail")
        elif not ok:
            fails += 1
            print(f"DISASM    {enc.hex().upper()}: got {shown!r}, expected {want_text!r}")
    print(f"disassembly: {sum(1 for r in rows if r[1] != '-')} checked, "
          f"{sum(1 for r in rows if r[1] == '-')} raw (no disassembler support), "
          f"{xfails} known-wrong")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path, required=True, help="toolchain bin directory")
    ap.add_argument("--out", type=Path, default=HERE.parent / "out")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cc = tool(a.bin, "clang", "clang-18")
    oc = tool(a.bin, "llvm-objcopy", "llvm-objcopy-18")
    mc = tool(a.bin, "llvm-mc", "llvm-mc-18")
    nm = tool(a.bin, "llvm-nm", "llvm-nm-18")
    version = run(cc, "--version").splitlines()[0]
    print(f"toolchain: {version}")

    rows = parse_expected()
    fails = 0

    # 1. assemble and compare bytes
    obj = a.out / "kernel.o"
    assembled = True
    try:
        run(cc, "--target=m68k", "-mcpu=M68000", "-c", str(HERE / "kernel.s"), "-o", str(obj))
    except subprocess.CalledProcessError as e:
        assembled = False
        fails += 1
        print("ASSEMBLE  the backend's assembler rejects kernel.s:")
        print("\n".join("  " + l for l in e.stderr.splitlines() if "error" in l))
    if assembled:
        fails += check_kernel(a, rows, obj, oc, mc, nm)

    # 3. compiled C: MOVE.W #imm,(xxx).L is 0x33FC, immediate word, 32-bit address
    cobj = a.out / "main-check.o"
    run(cc, "--target=m68k", "-mcpu=M68000", "-Os", "-ffreestanding", "-fno-pic",
        "-c", str(PROGRAMS / "colour-loop" / "main.c"), "-o", str(cobj))
    run(oc, "-O", "binary", "-j", ".text", str(cobj), str(a.out / "main-check.bin"))
    code = (a.out / "main-check.bin").read_bytes()
    for label, pattern in (("INTENA <- $7FFF", "33FC7FFF00DFF09A"),
                           ("COLOR00 <- $0F00", "33FC0F0000DFF180")):
        if bytes.fromhex(pattern) in code:
            print(f"C store   {label}: {pattern} present")
        else:
            fails += 1
            print(f"C store   {label}: {pattern} NOT found in the compiled object")

    # 4. single-instruction probes: what the assembler can do at all
    held = broken = 0
    for line in (HERE / "probes.expected").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        src, enc, status = (f.strip() for f in line.split("|"))
        want_bytes = bytes.fromhex(enc.replace(" ", ""))
        asm = a.out / "probe.s"
        asm.write_text("\t.text\n\t" + src.replace("\\n", "\n\t") + "\n")
        r = subprocess.run([cc, "--target=m68k", "-mcpu=M68000", "-c", str(asm), "-o",
                            str(a.out / "probe.o")], capture_output=True, text=True)
        got_bytes = None
        if r.returncode == 0:
            run(oc, "-O", "binary", "-j", ".text", str(a.out / "probe.o"), str(a.out / "probe.bin"))
            got_bytes = (a.out / "probe.bin").read_bytes()
        good = got_bytes == want_bytes
        shown = "rejected" if got_bytes is None else f"assembled to {got_bytes.hex().upper()}"
        label = src.replace("\\n", " ")
        if status == "ok" and not good:
            fails += 1
            print(f"PROBE     {label}: {shown}, the manual says {want_bytes.hex().upper()}")
        elif status == "xfail" and good:
            fails += 1
            print(f"XPASS     {label} now assembles correctly; remove the xfail")
        elif status == "xfail":
            broken += 1
            print(f"XFAIL     {label}: {shown} (manual: {want_bytes.hex().upper()})")
        else:
            held += 1
    print(f"probes: {held} correct, {broken} known-broken")

    print("PASS" if fails == 0 else f"FAIL ({fails})")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
