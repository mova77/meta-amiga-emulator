#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Wrap boot code in a 1024-byte Amiga boot block, optionally in a blank 880 KiB disk image.

Layout, per the Amiga ROM Kernel Reference Manual (Libraries, "Disk boot"): bytes 0-3 are
'DOS\\0', bytes 4-7 the checksum, bytes 8-11 the root block number (880), the code starts at
byte 12. The checksum is chosen so that the sum of all 256 longwords, with the carry out of
each addition added back in, comes to 0xFFFFFFFF.
"""
import argparse
import struct
import sys


def checksum(block: bytes) -> int:
    total = 0
    for (word,) in struct.iter_unpack(">I", block):
        total += word
        if total > 0xFFFFFFFF:
            total = (total & 0xFFFFFFFF) + 1  # end-around carry
    return (~total) & 0xFFFFFFFF


def verifies(block: bytes) -> bool:
    """The ROM's own test: all 256 longwords summed with end-around carry give 0xFFFFFFFF."""
    return checksum(block[:4] + bytes(4) + block[8:]) == struct.unpack(">I", block[4:8])[0]


def make(code: bytes) -> bytes:
    if len(code) > 1024 - 12:
        raise SystemExit(f"boot code is {len(code)} bytes; the limit is {1024 - 12}")
    block = bytearray(b"DOS\0" + bytes(4) + struct.pack(">I", 880) + code)
    block += bytes(1024 - len(block))
    block[4:8] = struct.pack(">I", checksum(bytes(block)))
    total = 0
    for (word,) in struct.iter_unpack(">I", bytes(block)):
        total += word
        total = (total & 0xFFFFFFFF) + (total >> 32)  # end-around carry
    assert total == 0xFFFFFFFF and verifies(bytes(block)), "boot block checksum is wrong"
    return bytes(block)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("code", help="raw boot code (placed at byte 12)")
    ap.add_argument("out")
    ap.add_argument("--adf", action="store_true", help="write a full 901120-byte disk image")
    a = ap.parse_args()
    block = make(open(a.code, "rb").read())
    if a.adf:
        block += bytes(901120 - len(block))
    open(a.out, "wb").write(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
