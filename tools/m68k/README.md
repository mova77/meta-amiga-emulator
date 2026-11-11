<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 The meta-amiga authors
-->

# tools/m68k — a pinned 68000 toolchain and its checks

Build-time tooling for writing 68000 code: the hardware verification programs and, later, the
Amiga-side handler. Nothing here is linked into the emulator. Design, measured costs and
findings: [SPIKE-S3](../../docs/spikes/SPIKE-S3-m68k-toolchain.md).

C is compiled by **clang** (pinned LLVM, experimental M68k backend). Everything hand-written in
assembly is assembled by **GNU as**, and linked by **GNU ld** (pinned binutils): the LLVM M68k
assembler is incomplete and in places silently wrong, and lld has no M68k backend.

| | |
|---|---|
| `toolchain.pin` | The LLVM tag and the binutils release, named here and nowhere else. |
| `build-toolchain.sh` | Builds clang and the LLVM tools with the experimental M68k backend at the pinned tag into an install prefix, outside the tree. |
| `build-binutils.sh` | Builds the pinned GNU binutils (`m68k-linux-gnu-as`, `-ld`, `-objcopy`, `-objdump`, `-nm`) from the release tarball. Only for a machine whose distribution does not package that version. |
| `build-program.sh <name>` | Builds `programs/<name>` into a raw blob at a known link address: clang for `.c`, GNU as for `.s`, GNU ld to link. |
| `programs/colour-loop` | The hardware program: sets `COLOR00` and loops. Also wrapped in a bootable disk image. |
| `programs/selftest` | C that stresses the code generator; its results are checked, not observed. |
| `bootblock/` | The boot block stub and the script that turns it into an Amiga boot block. |
| `oracle/` | Oracle 1 (assembled bytes against the manual: GNU as is the gate, the LLVM assembler's state is recorded beside it), oracle 3 (a black-box CPU model) and the oracle 2 stand-in (`boot_colour_loop.sh` boots `colour-loop.adf` in FS-UAE and `colour_period.py` reads the colour period off the screen). |
| `check.sh` | Runs the oracles against the installed tools. |
| `measure/` | The line and instruction counts behind SPIKE-S3 section 9. |

```sh
tools/m68k/build-toolchain.sh             # clang: 46 to 52 minutes on four cores
sudo apt install binutils-m68k-linux-gnu  # GNU as and ld 2.42 (Ubuntu 24.04), or:
tools/m68k/build-binutils.sh              # the pinned release from source: about a minute
pip install unicorn                       # optional: oracle 3; check.sh skips it when absent
sudo apt install fs-uae xvfb ffmpeg       # optional: the oracle 2 stand-in; skipped when absent
tools/m68k/check.sh                       # or: check.sh <llvm-bin-dir> <binutils-bin-dir>
python3 -m unittest discover -s tools/m68k/oracle -p 'test_*.py'   # the period reader's own tests
```

The scripts find the binutils on `PATH`, or in `BINUTILS_BIN` / the second argument when they
were built with `build-binutils.sh` (`~/.cache/meta-amiga/binutils-m68k/install/bin`).

Write hand-written 68000 with the real mnemonics, and give every branch an explicit size
(`bra.s`, `beq.s`, `bsr.w`): GNU as encodes an unsized `bra`, `bcc` or `bsr` as the word form
whatever the distance (SPIKE-S3 section 4.3). `jbra`/`jbcc` pick the shortest form instead.

The oracle 2 stand-in boots with FS-UAE's built-in AROS ROM, so it needs no Kickstart;
`KICKSTART=<path> tools/m68k/check.sh` uses a ROM you own instead. It reads the period in host
time, so it checks the emulator's timing, not a real A500's
([SPIKE-S3](../../docs/spikes/SPIKE-S3-m68k-toolchain.md) section 8.2).

Generated files go under `tools/m68k/out/`, which is git-ignored. No disk image or ROM is ever
committed.
