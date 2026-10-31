<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 The meta-amiga authors
-->

# tools/m68k — a pinned 68000 toolchain and its checks

Build-time tooling for writing 68000 code: the hardware verification programs and, later, the
Amiga-side handler. Nothing here is linked into the emulator. Design, measured costs and
findings: [SPIKE-S3](../../docs/spikes/SPIKE-S3-m68k-toolchain.md).

| | |
|---|---|
| `toolchain.pin` | The LLVM tag, named here and nowhere else. |
| `build-toolchain.sh` | Builds clang and the LLVM binutils with the experimental M68k backend at that tag into an install prefix, outside the tree. |
| `build-program.sh <name>` | Builds `programs/<name>` into a raw blob at a known link address (linked with binutils' `m68k-linux-gnu-ld`: lld has no M68k backend). |
| `programs/colour-loop` | The hardware program: sets `COLOR00` and loops. Also wrapped in a bootable disk image. |
| `programs/selftest` | C that stresses the code generator; its results are checked, not observed. |
| `bootblock/` | The boot block stub and the script that turns it into an Amiga boot block. |
| `oracle/` | Oracle 1 (encodings against the manual) and oracle 3 (a black-box CPU model). |
| `check.sh` | Runs both oracles against an installed toolchain. |
| `measure/` | The line and instruction counts behind SPIKE-S3 §9. |

```sh
tools/m68k/build-toolchain.sh             # 46 minutes on four cores; a 236 MB prefix
sudo apt install binutils-m68k-linux-gnu  # the linker
pip install unicorn                       # optional: oracle 3; check.sh skips it when absent
tools/m68k/check.sh
```

Generated files go under `tools/m68k/out/`, which is git-ignored. No disk image or ROM is ever
committed.
