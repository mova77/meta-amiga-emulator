# SPIKE-S3 — A pinned M68k toolchain: does it work, and what is the cheapest form to depend on

| | |
|---|---|
| **Status** | Draft — findings complete; recommendation awaits review; real-hardware run (§8) outstanding |
| **Date** | 2026-10-31 |
| **Relates to** | [SPIKE-S2](SPIKE-S2-llvm-toolchain-and-jit.md) §3, §3.1, §5, §7 · [ADR-PORT-04](../adr/ADR-PORT-04-portability-and-backends.md) D6 · [ADR-CPU-02](../adr/ADR-CPU-02-68k-core-strategy.md) D6 |
| **Closes** | SPIKE-S2 §7, first open item (build and pin, and where it lives) and third open item (is the experimental target stable enough) |
| **Examined** | `llvmorg-22.1.8` built from source; the distro's clang 18.1.3 (Ubuntu 24.04); `llvmorg-23.1.4`'s assembler and disassembler built and probed (§6); the source headers of `main` for the gaps in §4 |

SPIKE-S2 §3 found that the LLVM M68k backend could compile the 68000 code this project
must write anyway, and listed what stood between that finding and a dependency. This spike
answers by doing: it builds the backend at a pinned tag, compiles and assembles a small
bare-metal program and an instruction kernel, and checks the result against three
independent authorities. It reads nothing but documentation, LLVM's own source and the
output of tools run as black boxes.

## 1. Answer

**Yes, with a short list of known holes, and not from the distro.**

- LLVM `22.1.8` with the experimental M68k target compiles C and assembles instructions into
  correct 68000 code. Every one of the 29 kernel instructions assembled to the encoding derived
  by hand from the 68000 Programmer's Reference Manual (§7), and every program built with it ran
  to the expected result under an independent 68000 model (§7).
- The cheapest form the project can depend on is **a per-developer source build of clang only,
  recipe committed and pinned in one file, with a CI-built artefact of the same recipe as the
  convenience route** (§5, §6). Distro packages are rejected: clang 18.1.3 assembles
  `MOVEM … ,-(SP)` to the wrong bytes (§4.2).
- **lld cannot be part of it.** It has no M68k backend, at 22.1.8, at 23.1.4 or on `main`.
  Linking is done by binutils' `m68k-linux-gnu-ld`, a build-time tool (§4.4).
- The assembler lacks `ADDQ`, `SUBQ`, `DBcc`, `TST`, `CLR`, `SWAP`, `STOP` and more (§4.1).
  The measurement loops SPIKE-S0 §3.2 needs are built on `DBRA`, so they are written with the
  encoding spelled out in `.short`. That is a fact about the backend, not a blocker, and
  `check_encodings.py` pins it so that a toolchain bump that fixes it forces the workaround out.

## 2. Method, and the four authorities

A toolchain is only worth depending on if its output can be shown correct by something other
than itself. Four authorities were identified; three were used.

| | Authority | What it can say | Used |
|---|---|---|---|
| **1** | The Motorola 68000 Programmer's Reference Manual | The correct encoding of each instruction. Ground truth for encodings; says nothing about whole programs. | Yes — 29 encodings derived by hand into `tools/m68k/oracle/kernel.expected` |
| **2** | A real PAL A500 | Ground truth for behaviour *and* timing. | **Not yet** — steps in §8 |
| **3** | A third-party 68000 CPU model, run as a black box | Whether the instruction semantics agree with an implementation written independently of LLVM. Not timing, not the Amiga. | Yes — see below |
| **4** | Another assembler's output (vbcc, vasm) | Nothing. Excluded as a correctness authority by the project's rules. | No |

**Oracle 3, exactly.** The instrument is the `unicorn` package from PyPI, version **2.1.4**
(the `cp37-abi3-manylinux_2_17_x86_64` wheel), CPU model `UC_CPU_M68K_M68000`. It is installed
with `pip` and used only through its documented API: map memory, load bytes, run N
instructions, hook memory writes, read registers back. Its source was not opened, nothing from
it is in this repository, and it is not a dependency of the emulator or of any build: the
oracle script exits with the skip code when it is absent. This is the use
[PROVENANCE.md](../../PROVENANCE.md) describes as permitted — running another implementation and
observing what it does. The reviewer should still confirm that reading, because Unicorn is a
CPU-core library of the kind the same document forbids *importing*. It models a 68000 CPU only:
there is no Amiga here, no Kickstart (none was downloaded, and the route that needs one was
skipped), no custom chips. A store to `$DFF180` is observed as a write to an otherwise empty
page.

Agreement with oracle 3 is two independent implementations agreeing. It is evidence, not proof;
oracle 2 is what closes it.

## 3. The checkpoint

Both toolchains were asked for the same things on the same host (Ubuntu 24.04, 4 cores, 15 GB).

| | Distro clang 18.1.3 | Pinned `22.1.8` |
|---|---|---|
| Has `m68k` in `-print-targets` | yes | yes (built with `LLVM_EXPERIMENTAL_TARGETS_TO_BUILD=M68k`) |
| Compiles C with `--target=m68k -mcpu=M68000` | yes | yes |
| Assembles the kernel | **no** — rejects `moveq` | yes |
| Kernel bytes equal the manual (with `moveq` spelled `.short`) | **no** — `MOVEM … ,-(SP)` is `48E70107`, the manual says `48E7E080` | yes, 29 of 29 |
| Kernel result under oracle 3 | **fails** — `d0`, `d1`, `d2`, `a0` not restored by the `MOVEM` pair | passes, 11 of 11 registers |
| `selftest` (C) under oracle 3, `-Os` and `-O2` | passes | passes |
| `colour-loop` under oracle 3 | passes | passes |
| Links with its own lld | **no** — segfaults on any M68k object | **no** — `unsupported e_machine value: 4` |

Both toolchains produce correct objects for the programs. The distro build fails the more
demanding test: given the same instruction, it emits the wrong bytes, and two independent
authorities catch it.

## 4. What the backend does not do

All of this is pinned by `tools/m68k/oracle/probes.expected` and `kernel.expected`, run by
`check_encodings.py`. A line marked `xfail` that starts to work makes the check fail, so the
workaround is removed on purpose the day a toolchain bump fixes it.

### 4.1 Assembler gaps (both builds unless stated)

| Instruction as written | `18.1.3` | `22.1.8` | Manual encoding |
|---|---|---|---|
| `moveq #9,%d4` | rejected | **works** | `7809` |
| `addq.l #1,%d3`, `subq.l #1,%d3` | rejected | rejected | `5283`, `5383` |
| `dbra %d4,1b` (any `DBcc`) | rejected | rejected | `51CC FFFE` |
| `tst.w %d0`, `clr.w %d0`, `swap %d0`, `stop #$2700` | rejected | rejected | `4A40`, `4240`, `4840`, `4E72 2700` |
| `beq.s`, `bra.s` (explicit short) | rejected | rejected | plain `beq` and `bra` do pick the short form |
| `move.w %d0,0xDFF180`, `move.b …` (word or byte store to an absolute address above `$7FFF`) | rejected | rejected | `33C0 00DF F180` |
| `jmp 0x40000` | rejected | rejected | `4EF9 0004 0000` |

Absolute addressing is not lost: `move.l %d0,0xDFF180` works, so does `lea 0xDFF000,%a5`
followed by `move.w %d0,(0x180,%a5)`, and compiled C reaches `$DFF180` with the correct
`move.w #imm,(xxx).L` (`33FC 0F00 00DF F180`), because the compiler does not go through the
text assembler. `llvmorg-23.1.4` was built (assembler and disassembler only) and run through the same probes:
every row above is unchanged, so a newer tag does not close these. The source headers of `main`
still list `DBcc`, `ADDQ`, `SUBQ` and `TST` as untouched; that is the maintainers' own coverage
table, read, not built.

### 4.2 Wrong encodings, silently

- **`18.1.3`: `movem.l %d0-%d2/%a0,-(%sp)` assembles to `48E7 0107`.** In the pre-decrement mode
  the register mask is reversed (bit 0 is A7, bit 15 is D0); the manual's value is `48E7 E080`.
  The matching `MOVEM (SP)+` is right, so a push/pop pair does not restore the registers it
  names. Found by oracle 1 and independently by oracle 3 (the kernel run leaves `a0 = $7FFC`).
  Compiled C never emitted a pre-decrement `MOVEM` in any function tried, so the damage is to
  hand-written assembly, which is exactly where this project will use it. **Fixed in `22.1.8`.**
- **Both: `move.w #imm,%sr` assembles to `move.w #imm,%d0`** (`303C 2700`, manual `46FC 2700`),
  with no diagnostic. `18.1.3` also turns `move.w %d0,%sr` and `move.w %sr,%d1` into `D0`-to-`D0`
  moves; `22.1.8` gets those two right. Tracked as `xfail`.

### 4.3 Disassembler, `22.1.8`

`llvm-objdump` is not a reliable witness. `48E7 E080` prints as `movem.l %d7/%a5-%sp,-(%sp)`
(the reversed mask is not un-reversed); `DBcc` prints as `sf %a1` followed by `<unknown>`;
`ADDQ` prints `<unknown>`; and `lsr.l #8,%d1` prints `#0`, because the encoding stores 8 as 0.
The bytes are right in each case; the text is not. Oracle 1 therefore compares the bytes first
and uses the disassembly as a second line, with the wrong ones marked.

### 4.4 No linker, no runtime library

- `ld.lld` `22.1.8` stops with `unsupported e_machine value: 4` on an M68k object.
  `lld/ELF/Arch/` has no M68k file at `22.1.8`, and `lld/ELF/Arch/M68k.cpp` returns 404 at
  `llvmorg-23.1.4` and at `main`. Distro lld 18.1.3 segfaults on the same input. The build
  recipe therefore does not build lld, and linking uses `m68k-linux-gnu-ld` (Ubuntu package
  `binutils-m68k-linux-gnu`, 1.3 MB to download, 5.1 MB installed), with a short linker script.
- There is no `compiler-rt` or `libgcc` for M68k, so `* / %` on 32-bit values, which the 68000 has
  no instruction for, would become calls to routines that do not exist. The `selftest` program
  avoids them on purpose. When the first program needs one, it is written once, in assembly, in
  the repository.
- Calls are `jsr` to an absolute address, so a program is linked at the address it runs at. The
  boot block copies the blob there (§8).

### 4.5 Codegen: distro 18 against pinned 22, instruction by instruction

The same C (`tools/m68k/programs/`) was compiled by both and the disassemblies aligned.

| Program | Instructions, 18 → 22 | Aligned identical | What differs |
|---|---|---|---|
| `colour-loop`, `-Os` | 18 → 18 | 17 of 18 | `link.w %a6` → `suba.l #4,%sp` |
| `selftest`, `-Os` | 106 → 102 | 71 of 106 | frame pointer dropped (`link`/`unlk` → `suba`/`adda`), `moveq` for small constants, a dead `sub` in the `popcount` loop gone, registers allocated differently |
| `selftest`, `-O2` | 128 → 124 | 89 of 128 | the same |

Both are correct; the pinned one has three to four per cent fewer instructions and uses `MOVEQ`. Eighteen
is *acceptable as a compiler* for this tiny corpus and not as an assembler.

## 5. What each way of having the toolchain costs

Measured on this host (4 cores, 15 GB RAM, 23 GB free disk) unless marked.

| | (a) Distro package | (b) Per-developer source build | (c) Container image | (d) CI-built artefact |
|---|---|---|---|---|
| What you get | clang 18.1.3 | clang 22.1.8, recipe committed | the (b) prefix in an image | the (b) prefix as a tarball |
| One-time cost | `apt install`, seconds; 80 MB download, about 365 MB installed | **46 minutes** (2 734 s) from a clean state, of which the shallow sparse clone is 86 s | not built: no container daemon on this host. **Estimated** from the prefix: 236 MB plus a base layer | the same build once per pin change; expected to cost about the same on a 4-core runner, not run in CI here |
| Peak disk while building | — | **3.3 GB**, then the 236 MB prefix alone | — | as (b) |
| Peak RAM | — | **5.9 GB** above idle (host-wide, with `LLVM_PARALLEL_LINK_JOBS=1`) | — | as (b) |
| Steady state | 365 MB | **236 MB** prefix (clang, llvm-mc, objdump, objcopy, nm, readelf) | about 250 MB plus a base layer, uncompressed | **58 MB** as `.tar.xz`, 84 MB as `.tar.gz` |
| Correct for this project | **No** (§4.2) | Yes | Yes | Yes |
| Pin is exact | No: whatever the release ships | Yes: `toolchain.pin` | Yes | Yes |
| Developer needs | root, network | about 6 GB of free RAM and under an hour | a container runtime | only to download and unpack |
| Redistribution | none | none | **Apache-2.0 notices apply** (§10) | **Apache-2.0 notices apply** if the artefact is public (§10) |

The first source build, run with the first configuration tried (`clang;lld`), cost 26 minutes up to
the failure of a sparse checkout that omitted a header lld's Mach-O backend wants, and 26 more to
finish, so **about 52 minutes of compiling**; peak disk 4.3 GB (a 2.1 GB sparse clone, a 1.6 GB build tree, a
450 MB prefix), peak RAM 6.6 GB host-wide. Dropping lld, the static analyser and the optional
compression libraries is what makes the recommended recipe cheaper; the column above is that
recipe, measured from nothing by the committed script (configure line in `build-toolchain.sh`; `clang;lld` replaced by `clang`, static analyser, ARC migrator, zlib, zstd and libxml2 off). Its prefix produced byte-identical program blobs to the first build, and passes every check in §7.

## 6. Recommendation

**Hosting.** Build from source with `tools/m68k/build-toolchain.sh`; publish the same recipe's
output as a CI artefact so a contributor who only wants to assemble a test program downloads 58 MB
instead of building for three quarters of an hour. The build is the authority; the artefact is a cache of it, keyed
on the hash of `toolchain.pin` and the recipe. Do not offer a container image until a second
consumer wants one: it adds a runtime to the contributor's machine and a redistribution
obligation to the project, and buys nothing the tarball does not. Do not use the distro package,
for correctness (§4.2) and because its version moves under the project's feet. A tarball is not
free of licence duty either (§10).

**Pinning.** One release, upgraded deliberately. The tag lives in one file,
`tools/m68k/toolchain.pin`, and nothing else in the repository repeats it. Upgrading is a change
of that line plus a run of `tools/m68k/check.sh`; the check is built to make the upgrade honest —
a gap that has closed turns an `xfail` into a failure, a regression turns an `ok` into one, and
the kernel and the three programs must still agree with oracle 3. Tracking `main` is rejected: the
backend is experimental, its own source says unimplemented instructions are "not touched at all",
and a silent change in assembler behaviour would arrive as a change in what a measurement program
measures. Experimental status is acceptable *because* the oracles run on every bump; without them
it would not be.

**Which release.** `22.1.8` is no longer the newest stable: `llvmorg-23.1.4` exists. Its assembler
and disassembler were built and run through oracle 1: the encodings match the manual, the
same twelve probes fail, and the same `MOVEM` disassembly is wrong. Nothing in it is a reason to
move, and nothing in it is a reason to stay except that `22.1.8` is the version every other
result here was measured on. Its C code generator was not run. The first real bump will also
need the recipe to change: configuring `23.1.4` fails unless the sparse checkout includes `libc/`,
which `22.1.8` does not ask for.

## 7. Oracle results

`tools/m68k/check.sh` runs them all. Results for the pinned `22.1.8`:

| Oracle | Subject | Result |
|---|---|---|
| 1 | 29 kernel instructions, assembled bytes against the manual | 29 of 29 identical |
| 1 | 27 round-trips through the disassembler | 26 agree, 1 known-wrong (`MOVEM` pre-decrement text), 2 raw (no support) |
| 1 | `move.w #imm,(xxx).L` from compiled C | `33FC 7FFF 00DF F09A` and `33FC 0F00 00DF F180` present |
| 1 | 20 single-instruction probes | 8 correct, 12 known-broken (§4.1, §4.2) |
| 3 | kernel, executed from `kernel` to `done` | 11 of 11 registers as derived from the manual |
| 3 | `selftest`, C, `-Os` and `-O2` | 8 of 8 results; hex formatting, sign-extending sum, popcount loop, xorshift, switch |
| 3 | `colour-loop` | `INTENA`, `INTREQ`, `DMACON` cleared, then `COLOR00` alternates `$0F00`, `$00F0`; 524 309 or 524 310 instructions between writes (the model: 8 passes of 65 538, plus 5 or 6) |
| 3 | `colour-loop` through its boot block | the block copies the blob to the link address; same sequence |

Expected values for `selftest` are computed in Python, independent of both compiler and CPU
model. The distro build passes the same `selftest` and `colour-loop`, and fails the kernel.

## 8. Oracle 2: the real A500, and what it is for

Nothing above is a statement about timing, and nothing above has met an Amiga. The program is
built so that the first real-hardware run is as cheap as possible.

1. Build: `tools/m68k/build-toolchain.sh`, then `tools/m68k/build-program.sh colour-loop`. The
   output is `tools/m68k/out/colour-loop.adf`, a bootable 901 120-byte disk image (git-ignored;
   it is generated, never committed).
2. Write it to a double-density disk with any ADF writer.
3. Power the PAL A500 off, put the disk in DF0:, power on. Kickstart's boot code reads the first
   sector, checks the checksum and calls the code at byte 12. The stub masks interrupts, copies the
   program to `$40000` and jumps to it.
4. **Expected:** the whole screen turns red, then green, then red, with a half-period of about
   0.74 s: 8 passes of 65 536 `DBRA` at 10 cycles on a 7.093 79 MHz clock is 5.24 million cycles. A
   stopwatch over ten periods is enough to say the `DBRA` cycle count is not wildly wrong; it is
   not a cycle-accurate measurement.
5. **Record:** Kickstart version, installed RAM, drive, the colours seen in order, ten periods by
   stopwatch, and any failure. A black screen, a freeze or a Guru Meditation is a result: report
   the Kickstart and memory configuration and retry with `LOAD_ADDR=0x60000
   tools/m68k/build-program.sh colour-loop`, because the stub's assumption that nothing the ROM
   allocated sits at the load address is unverified.

What oracle 2 settles that the others cannot: that the boot block checksum is accepted (the
algorithm is the published one and the script verifies its own output, but the ROM has not been
asked), that `$DFF180` takes effect when written from the code as built, and that the `DBRA` loop
runs at the cycle count the manual gives.

## 9. Does it make the measurement programs easier?

Measured on the test program, in `tools/m68k/measure/measure.sh`; no effort was timed.

| | All assembly | C plus assembly |
|---|---|---|
| `colour-loop`, the program as shipped | 22 lines of assembly, 64 bytes | 28 lines of C and 15 of assembly, 98 bytes |
| `selftest`, the harness-shaped C | — | 65 lines of C became 102 instructions (`-Os`) or 124 (`-O2`) |

- **The timing loops get no easier, and no smaller.** `colour-loop` is a *worse* program with a C
  harness: more lines and more bytes. The `DBRA` loop is hand-written
  either way, and the assembler cannot write `DBRA`, so the encoding is spelled out.
- **The code around the loops gets considerably easier.** Hex formatting of a result, a sign-extending
  sum, a loop that exits on its data, a table-driven switch and 32-bit shifts are 65 lines of C and about
  100 to 125 instructions the author does not write, schedule registers for, or encode. That is
  1.6 to 1.9 instructions per line of C, and the instructions are verified by oracle 3 rather than
  by eye. This is the claim SPIKE-S2 §3.1 made — the toolchain helps with the harness, not the
  measurement — now measured on a program rather than asserted.
- The honest limit: none of this is a count of hours. A measurement program is mostly loop, and the
  loop is exactly the part the toolchain leaves to hand.

## 10. Licence

LLVM, Clang and the LLVM binutils are under **Apache License 2.0 with LLVM Exceptions**
(`LICENSE.TXT` at the root of the examined tag; SPDX `Apache-2.0 WITH LLVM-exception`). In this
project they are a **build-time tool only**. Nothing of LLVM is linked into the emulator, and the
emulator's binary does not contain any of it; ADR-PORT-04 D6's runtime-dependency bar does not
apply, and the lower bar for build-time tools does.

The exception reads:

> As an exception, if, as a result of your compiling your source code, portions of this Software
> are embedded into an Object form of such source code, you may redistribute such embedded
> portions in such Object form without complying with the conditions of Sections 4(a), 4(b) and
> 4(d) of the License.

Two consequences. First, the *output* of compiling this project's own source is this project's
own work: the licence grants rights in the Software, and the programs here contain no LLVM code
at all — there is no runtime library to embed (§4.4). Second, even where a compiler does embed a
piece of itself in an object, the exception removes the licence-text, notice and modification
conditions for that embedded piece, so nothing is owed in a GPL-3.0-or-later binary that carries
such a piece. The exception's second paragraph concerns GPLv2 and a retroactive waiver of the
patent and indemnity sections; it does not apply here and is not relied on. Apache-2.0 is in any
case one-way compatible with GPL-3.0.

What the exception does **not** cover is redistributing the compiler itself. A container image or
a published CI artefact carries LLVM's binaries, so it needs `LICENSE.TXT` and the notices
Apache-2.0 §4 asks for, shipped beside it. The build script does not yet package them (§11).
The linker, `m68k-linux-gnu-ld`, is GPL-3.0-or-later and is likewise only run. This paragraph is
the author's reading of the text, for the project owner to confirm; it is not legal advice.

## 11. Open

- **Oracle 2.** §8. Until it runs, no claim here is about hardware.
- **Newer tag.** If a bump is wanted, run the whole of `check.sh` on `llvmorg-23.1.4`: only its
  assembler and disassembler have been checked (§6).
- **Package the notices** with any published artefact (§10), and decide where it is published.
- **A runtime library** (`__mulsi3`, `__divsi3` and friends) the first time a program needs one.
- **SPIKE-S2 §7, second item** — ELF to hunk for the filesystem handler — is untouched by this
  spike. Nor is the JIT item.
- **CI.** `check.sh` is runnable; whether it becomes a job depends on the artefact decision above.
