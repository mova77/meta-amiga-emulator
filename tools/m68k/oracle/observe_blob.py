#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Oracle 3: run a raw 68000 blob under a third-party CPU emulator, as a black box.

The instrument is the `unicorn` PyPI package, used only through its documented public API:
load bytes at an address, run N instructions, hook memory writes, read registers back. Its
source is never read and nothing from it enters this repository (PROVENANCE.md, "What
contributors may use": observing behaviour is permitted, transcribing implementation is not).
It models a 68000 CPU only: there is no Amiga here, no Kickstart, no custom-chip model. A
write to $DFF180 is observed as a store to an otherwise empty mapped page.

Exit 0 when the observed write sequence and register state match the expectations given on
the command line, 1 on a mismatch, 77 (the CTest skip code) when unicorn is not installed.

Usage: observe_blob.py colour-loop <blob> <load-addr> [--outer N] [--bootblock <image>]
       observe_blob.py selftest <blob> <load-addr>
       observe_blob.py kernel <kernel.bin> <load-addr> --syms <kernel.syms>
"""
from __future__ import annotations

import argparse
import sys

SKIP = 77

try:
    import unicorn
    from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
    from unicorn import m68k_const as m
except ImportError:
    print("SKIP: the 'unicorn' package is not installed (pip install unicorn)")
    sys.exit(SKIP)

CUSTOM = 0x00DFF000
PAGE = 0x1000


def new_machine(blob: bytes, load: int) -> Uc:
    uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
    uc.ctl_set_cpu_model(m.UC_CPU_M68K_M68000)
    ram = 0x00080000  # 512 KiB of "chip RAM" is plenty for these programs
    uc.mem_map(0, ram)
    uc.mem_map(CUSTOM, PAGE)  # stores land here; nothing models them
    uc.mem_write(load, blob)
    uc.reg_write(m.UC_M68K_REG_A7, ram - 0x100)  # a stack for C code
    return uc


def run_colour_loop(blob: bytes, load: int, instructions: int, outer: int,
                    bootblock: bytes | None = None) -> int:
    """With a boot block: place it where a ROM might (not at `load`), enter at byte 12 as
    the ROM does, and require that the stub copies the blob to `load` before it runs."""
    uc = new_machine(b"" if bootblock else blob, load)
    entry = load
    if bootblock:
        base = 0x00070000
        uc.mem_write(base, bootblock)
        entry = base + 12
    writes: list[tuple[int, int]] = []
    stamps: list[int] = []  # instructions retired when each write happened
    retired = [0]

    def on_code(_uc, _address, _size, _user):
        retired[0] += 1

    def on_write(_uc, _access, address, size, value, _user):
        if CUSTOM <= address < CUSTOM + PAGE:
            writes.append((address - CUSTOM, value & ((1 << (8 * size)) - 1)))
            stamps.append(retired[0])

    uc.hook_add(UC_HOOK_MEM_WRITE, on_write)
    uc.hook_add(UC_HOOK_CODE, on_code)
    uc.emu_start(entry, 0, count=instructions)

    want_prefix = [(0x09A, 0x7FFF), (0x09C, 0x7FFF), (0x096, 0x7FFF)]
    colours = [v for off, v in writes if off == 0x180]
    skip = 1 if bootblock else 0  # the stub masks INTENA once before it copies
    ok = writes[skip:skip + 3] == want_prefix
    if bootblock:
        copied = bytes(uc.mem_read(load, len(blob)))
        print(f"boot block copied the blob to ${load:X}: {copied == blob}")
        ok = ok and copied == blob
    ok = ok and len(colours) >= 3 and all(
        c == (0x0F00, 0x00F0)[i % 2] for i, c in enumerate(colours))
    # Between two COLOR00 writes the program retires DELAY_OUTER passes of 65538
    # instructions plus a handful around them. A DBRA that fell through early, or looped
    # an extra time, moves this number by tens of thousands. DELAY_OUTER comes from --outer.
    colour_at = [t for (off, _), t in zip(writes, stamps) if off == 0x180]
    periods = [b - a for a, b in zip(colour_at, colour_at[1:])]
    lo = outer * (65536 + 2)  # per pass: 65536 inner DBRA, the reload and the outer DBRA
    hi = lo + 16
    ok = ok and bool(periods) and all(lo <= p <= hi for p in periods)
    print(f"instructions between COLOR00 writes: {periods} (expected {lo}..{hi})")
    print(f"observed {len(writes)} custom-register writes in {instructions} instructions")
    print("first writes:", ", ".join(f"${o:03X}<-${v:04X}" for o, v in writes[:6]))
    print(f"COLOR00 ($DFF180) sequence: {['$%04X' % c for c in colours]}")
    print(f"pc=${uc.reg_read(m.UC_M68K_REG_PC):08X}  "
          f"sr=${uc.reg_read(m.UC_M68K_REG_SR):04X}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# What programs/selftest/selftest.c must leave in memory, computed here in Python so the
# expectation is independent of both the compiler and the CPU model.
def selftest_expected() -> dict[int, int]:
    def xorshift32(x: int) -> int:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        return x

    table = {0: 10, 1: 21, 2: 32, 3: 43, 5: 65, 7: 87}
    classify = lambda v: table.get(v & 7, -1) & 0xFFFFFFFF
    samples = [-1, 2, -3, 1000, 0x7FFF, -0x8000, 5]
    return {
        0x50000: sum(samples) & 0xFFFFFFFF,
        0x50004: bin(0xF0F0A5C3).count("1"),
        0x50008: xorshift32(1),
        0x5000C: xorshift32(0xDEADBEEF),
        0x50010: classify(5) + 1000,
        0x50014: classify(4),
        0x50018: 0xA5A5A5A5,
    }


def run_selftest(blob: bytes, load: int) -> int:
    uc = new_machine(blob, load)
    uc.emu_start(load, 0, count=200_000)
    ok = True
    for addr, want in selftest_expected().items():
        got = int.from_bytes(uc.mem_read(addr, 4), "big")
        mark = "ok " if got == want else "BAD"
        ok = ok and got == want
        print(f"  {mark} ${addr:05X}: got ${got:08X}  want ${want:08X}")
    text = bytes(uc.mem_read(0x50100, 9))
    mark = "ok " if text == b"00DFF180\0" else "BAD"
    ok = ok and text == b"00DFF180\0"
    print(f"  {mark} $50100: got {text!r}  want b'00DFF180\\x00'")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def run_kernel(blob: bytes, load: int, syms: dict[str, int]) -> int:
    """Execute kernel.s from `kernel` to `done` and compare the registers with the values
    worked out by hand from the instruction semantics in the Programmer's Reference Manual."""
    uc = new_machine(blob, load)
    uc.reg_write(m.UC_M68K_REG_A0, 0x100)
    uc.reg_write(m.UC_M68K_REG_A7, 0x8000)
    try:
        uc.emu_start(load + syms["kernel"], load + syms["done"], count=500)
    except unicorn.UcError as e:
        print(f"  emulation stopped with {e}")
    # d0: $F0 + $F0 (word add) + $F0 (long add) = $2D0; d3 takes d0 through the stack; d4
    # counts 9..0 and DBRA leaves the low word at $FFFF; d5 = 9+8+...+0; d7 = 1 because the
    # first branch (CMP equal, so BEQ taken) skips one MOVE and BNE falls through to MOVEQ.
    want = {
        "d0": 0x2D0, "d1": 0xF0, "d2": 0xF0, "d3": 0x2D0, "d4": 0xFFFF, "d5": 45,
        "d6": 0xBEEF, "d7": 1, "a0": 0x100, "a1": load + syms["sub"], "a7": 0x8000,
    }
    ok = True
    for name, expect in want.items():
        reg = getattr(m, f"UC_M68K_REG_{name.upper()}")
        got = uc.reg_read(reg)
        ok = ok and got == expect
        print(f"  {'ok ' if got == expect else 'BAD'} {name}: got ${got:08X}  want ${expect:08X}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["colour-loop", "selftest", "kernel"])
    ap.add_argument("blob")
    ap.add_argument("load", type=lambda s: int(s, 0))
    ap.add_argument("--syms", help="kernel.syms written by check_encodings.py")
    ap.add_argument("--bootblock", help="boot block image that carries the blob")
    ap.add_argument("--instructions", type=int, default=3_000_000)
    ap.add_argument("--outer", type=int, default=8, help="DELAY_OUTER the blob was built with")
    a = ap.parse_args()
    blob = open(a.blob, "rb").read()
    print(f"instrument: unicorn {unicorn.__version__}, CPU model M68000")
    if a.what == "kernel":
        syms = dict(l.split("=") for l in open(a.syms).read().split())
        return run_kernel(blob, a.load, {k: int(v, 0) for k, v in syms.items()})
    if a.what == "selftest":
        return run_selftest(blob, a.load)
    bb = open(a.bootblock, "rb").read() if a.bootblock else None
    return run_colour_loop(blob, a.load, a.instructions, a.outer, bb)


if __name__ == "__main__":
    sys.exit(main())
