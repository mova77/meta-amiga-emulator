# SPIKE-S3 — A pinned M68k toolchain: does it work, and what is the cheapest form to depend on

| | |
|---|---|
| **Status** | Draft — findings complete; recommendation awaits review; real-hardware run (§8) outstanding |
| **Date** | 2026-10-31 |
| **Relates to** | [SPIKE-S2](SPIKE-S2-llvm-toolchain-and-jit.md) §3, §3.1, §5, §7 · [ADR-PORT-04](../adr/ADR-PORT-04-portability-and-backends.md) D6 · [ADR-CPU-02](../adr/ADR-CPU-02-68k-core-strategy.md) D6 |
| **Closes** | SPIKE-S2 §7, first open item (build and pin, and where it lives) and third open item (is the experimental target stable enough) |
| **Examined** | `llvmorg-22.1.8` built from source; the distro's clang 18.1.3 (Ubuntu 24.04); `llvmorg-23.1.4`'s assembler and disassembler built and probed (§6); GNU binutils 2.42, as the Ubuntu package and built from the release tarball (§5.1); the source of `main` for the gaps in §4 |

SPIKE-S2 §3 found that the LLVM M68k backend could compile the 68000 code this project
must write anyway, and listed what stood between that finding and a dependency. This spike
answers by doing: it builds the backend at a pinned tag, compiles C and assembles
instructions with it, and checks the result against independent authorities. It reads
nothing but documentation, LLVM's and binutils' behaviour as run, and the source headers of
LLVM's M68k backend.

The backend's *assembler* turned out to be incomplete and in places silently wrong (§4), so
the recipe assembles with GNU as and uses LLVM for C only. Everything below describes that
recipe.

## 1. Answer

**Yes: clang (pinned) for C, GNU binutils (pinned) for assembly and linking. Not the distro's
clang as the project's toolchain, and not LLVM's assembler.**

- LLVM `22.1.8` with the experimental M68k target compiles C into correct 68000 code:
  `selftest` (`-Os` and `-O2`) and `colour-loop` ran to the expected results under an
  independent 68000 model (§7). C code generation is the part of the backend that works.
- Its assembler does not work well enough for hand-written code. It has no `DBcc`, `ADDQ`,
  `SUBQ`, `TST`, `CLR`, `SWAP` or `STOP`, rejects a word store to an absolute custom-chip
  address, and assembles `move.w #imm,%sr` to `move.w #imm,%d0` without a diagnostic. Of 22
  single-instruction probes it assembles 8 to the manual's bytes and 1 to a different valid
  encoding; it rejects 12 and mis-encodes 1 (§4.1, §4.2).
- **GNU as `2.42` (`-m68000`) matches the manual on all 22 probes, including every one LLVM
  gets wrong, on all 29 kernel instructions, and on the hand-written assembly of the test
  programs** (§7). No `.short` workaround remains in the tree; the programs use the real
  mnemonics.
- The cheapest form the project can depend on is **a per-developer source build of clang
  only, recipe committed and pinned in one file, with a CI-built artefact of the same recipe
  as the convenience route, plus GNU binutils** from the distribution (Ubuntu 24.04 ships the
  pinned `2.42`) **or built from the pinned release tarball in about a minute** (§5, §6).
- **lld cannot be part of it.** It has no M68k backend, at 22.1.8, at 23.1.4 or on `main`.
  Linking is done by binutils' `m68k-linux-gnu-ld` (§4.5).
- One behaviour of GNU as to know: an unsized `bra`, `bcc` or `bsr` is always the word form.
  Hand-written code gives branches explicit sizes (§4.3).

## 2. Method, and the four authorities

A toolchain is only worth depending on if its output can be shown correct by something other
than itself. Four authorities were identified; three were used.

| | Authority | What it can say | Used |
|---|---|---|---|
| **1** | The Motorola 68000 Programmer's Reference Manual | The correct encoding of each instruction. Ground truth for encodings; says nothing about whole programs. | Yes — 29 kernel encodings, 22 probes and the programs' assembly derived by hand into `tools/m68k/oracle/*.expected` |
| **2** | A real PAL A500 | Ground truth for behaviour *and* timing. | **Not yet** — steps in §8 |
| **3** | A third-party 68000 CPU model, run as a black box | Whether the instruction semantics agree with an implementation written independently of the toolchain. Not timing, not the Amiga. | Yes — see below |
| **4** | Another assembler's output (vbcc, vasm) | Nothing. Excluded as a correctness authority by the project's rules. | No |

**GNU as is a tool under test, not an authority.** It is held to authority 1 exactly as LLVM's
assembler is: its bytes are compared with the manual's, never with LLVM's. That it passes is
the evidence for using it. Its source was not read.

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

Each toolchain was asked for the same things on the same host (Ubuntu 24.04, 4 cores, 15 GB).
The kernel here is the one as first written, with `moveq` and `.short` standing in for what
LLVM's assembler could not take; the kernel in the tree now uses the real mnemonics and only
GNU as assembles it (§4.1).

| | Distro clang 18.1.3 | Pinned LLVM `22.1.8` | GNU as `2.42` |
|---|---|---|---|
| Has `m68k` in `-print-targets` | yes | yes (built with `LLVM_EXPERIMENTAL_TARGETS_TO_BUILD=M68k`) | — (an `m68k-linux-gnu` assembler) |
| Compiles C with `--target=m68k -mcpu=M68000` | yes | yes | — |
| Assembles the kernel | **no** — rejects `moveq` | yes, with `.short` for `ADDQ` and `DBcc` | yes, every instruction a real mnemonic |
| Kernel bytes equal the manual | **no** — `MOVEM … ,-(SP)` is `48E70107`, the manual says `48E7E080` | yes, 29 of 29 | yes, 29 of 29 |
| Kernel result under oracle 3 | **fails** — `d0`, `d1`, `d2`, `a0` not restored by the `MOVEM` pair | passes, 11 of 11 registers | passes, 11 of 11 registers |
| `selftest` (C) under oracle 3, `-Os` and `-O2` | passes | passes | — (C is clang's) |
| `colour-loop` under oracle 3 | passes | passes | — |
| Links with its own lld | **no** — segfaults on any M68k object | **no** — `unsupported e_machine value: 4` | `ld` links (§4.5) |

The distro build fails the more demanding test: given the same instruction, it emits the wrong
bytes, and two independent authorities catch it. Its C output is correct (§4.6).

## 4. What the LLVM backend does not do, and what GNU as does instead

The state of LLVM's assembler and disassembler is recorded in `tools/m68k/oracle/probes.expected`
and `kernel.expected` and run by `check_encodings.py`, beside GNU as, which is the gate. At
the pinned tag, a recorded row that stops being true fails the check: an `xfail` that starts
to work is noticed, and the notes below change on purpose the day a toolchain bump fixes it.

### 4.1 LLVM assembler gaps (GNU as has none of them)

| Instruction as written | LLVM `18.1.3` | LLVM `22.1.8` | GNU as `2.42` | Manual encoding |
|---|---|---|---|---|
| `moveq #9,%d4` | rejected | **works** | works | `7809` |
| `addq.l #1,%d3`, `subq.l #1,%d3` | rejected | rejected | works | `5283`, `5383` |
| `dbra %d4,1b` (any `DBcc`) | rejected | rejected | works | `51CC FFFE` |
| `tst.w %d0`, `clr.w %d0`, `swap %d0`, `stop #$2700` | rejected | rejected | works | `4A40`, `4240`, `4840`, `4E72 2700` |
| `beq.s`, `bra.s` (explicit short) | rejected | rejected | works | plain `beq` and `bra` pick the short form in LLVM; GNU as picks the word form (§4.3) |
| `move.w %d0,0xDFF180`, `move.b …`, `move.w #imm,0xDFF09A` (word or byte store to an absolute address above `$7FFF`) | rejected | rejected | works | `33C0 00DF F180`, `33FC 7FFF 00DF F09A` |
| `jmp 0x40000` | rejected | rejected | works | `4EF9 0004 0000` |

GNU as matches the manual on every row. Absolute addressing is not lost in LLVM either:
`move.l %d0,0xDFF180` works, so does `lea 0xDFF000,%a5` followed by
`move.w %d0,(0x180,%a5)`, and compiled C reaches `$DFF180` with the correct
`move.w #imm,(xxx).L` (`33FC 0F00 00DF F180`), because the compiler does not go through the
text assembler. `llvmorg-23.1.4` was built (assembler and disassembler only) and run through
the same probes: every row above is unchanged, so a newer tag does not close these.

**Upstream status.** The `move.w #imm,%sr` miscompilation (§4.2) is a known upstream bug:
[llvm-project#165077](https://github.com/llvm/llvm-project/issues/165077), opened 2025-10-25
(`asm("move.w #0x2700,%sr")` is emitted as `move.w #9984, %d0`), closed 2026-09-20 by
[PR #207590](https://github.com/llvm/llvm-project/pull/207590), "[M68k] Add Imm source for MOVE
to CCR/SR". Read in the backend's source, `M68kInstrData.td` on `main` defines `MOV16si`, an
immediate source for MOVE to SR; the same file at `llvmorg-22.1.8` and at `llvmorg-23.1.4` has
none. That is: **fixed upstream on `main`, not yet in a release we pin.**
[PR #168485](https://github.com/llvm/llvm-project/pull/168485) (merged 2026-08-02) is related:
it changes how MOVE to and from SR and CCR is handled on the 68000. LLVM bug 51580 (2021) is
the MOVEM register-list syntax in the AsmParser.

For the missing mnemonics (`DBcc`, `ADDQ`, `SUBQ`, `TST`, `CLR`, `SWAP`, `STOP`) **no tracking
issue was found.** LLVM's own status table, in the header comments of
`llvm/lib/Target/M68k/M68kInstr*.td` on `main`, marks `ADDQ`, `SUBQ`, `DBcc`, `TST` and `SWAP`
"not touched at all". It is a coarse guide, not a contract: it marks `CLR` as usable, which the
assembler rejects, and `MOVEM` and `MOVEQ` as untouched, which it assembles.

### 4.2 LLVM: wrong encodings, silently

- **`18.1.3`: `movem.l %d0-%d2/%a0,-(%sp)` assembles to `48E7 0107`.** In the pre-decrement mode
  the register mask is reversed (bit 0 is A7, bit 15 is D0); the manual's value is `48E7 E080`.
  The matching `MOVEM (SP)+` is right, so a push/pop pair does not restore the registers it
  names. Found by oracle 1 and independently by oracle 3 (the kernel run leaves `a0 = $7FFC`).
  Compiled C never emitted a pre-decrement `MOVEM` in any function tried, so the damage is to
  hand-written assembly. **Fixed upstream** by commit
  [`937446d`](https://github.com/llvm/llvm-project/commit/937446d433b1c0bb3e4194847b3e620f308b0fbb),
  "[M68k] Fix incorrect move mask encoding with pre-decrement operand" (2025-05-15), which is
  why `18.1.3` (2024) is wrong and `22.1.8` is right. GNU as encodes it correctly.
- **LLVM, both: `move.w #imm,%sr` assembles to `move.w #imm,%d0`** (`303C 2700`, manual
  `46FC 2700`), with no diagnostic. `18.1.3` also turns `move.w %d0,%sr` and
  `move.w %sr,%d1` into `D0`-to-`D0` moves; `22.1.8` gets those two right. Upstream status in
  §4.1. GNU as encodes all three correctly.

### 4.3 GNU as: an unsized branch is a word branch

The kernel, assembled by GNU as with branches written the way LLVM accepts them (`beq skip`),
was identical to the manual in every instruction but the branches: `6700 0006` where the
manual-derived expectation is `6704`. Both are valid encodings of the same BEQ; the word form
carries a 16-bit displacement and is two bytes longer, which moves every later offset
(`lea (sub,%pc)` came out `43FA 0008`, not `43FA 0006`). Tried with `-m68000`:

| Source | Encoding |
|---|---|
| `beq fwd` / `bra back` / `bsr fwd`, a local label, 2 to 30 000 bytes away, forward or backward | word: `67 00 dddd`, `60 00 dddd`, `61 00 dddd` |
| `beq.s fwd` | short: `67 dd` |
| `beq.w fwd` | word |
| `jbeq fwd`, `jra back` | the shortest that reaches |

`--disp-size-default-16`, `--pcrel` and `-l` change none of it. So the cause is neither a
global label nor a forward reference nor relaxation failing: this GNU as encodes an unsized
Bcc, BRA or BSR as the word form, and shortens only the `j`-prefixed forms. LLVM picks the
short form when it fits, so source that is right for one is two bytes larger on the other.
**The fix is in the source, with explicit sizes:** `beq.s`, `bne.s` and `bra.s` where the
target is near, `bsr.w` where it is another object (which needs the word form anyway). With
them the kernel is identical to the manual's bytes, and `probes.expected` carries a row that
records both behaviours.

### 4.4 LLVM disassembler, `22.1.8`

`llvm-objdump` is not a reliable witness. `48E7 E080` prints as `movem.l %d7/%a5-%sp,-(%sp)`
(the reversed mask is not un-reversed); `DBcc` prints as `sf %a1` followed by `<unknown>`;
`ADDQ` prints `<unknown>`; and `lsr.l #8,%d1` prints `#0`, because the encoding stores 8 as 0.
The bytes are right in each case; the text is not. Oracle 1 records the LLVM disassembler's
behaviour; the program listings and the instruction counts of §9 come from GNU `objdump`,
which reads every instruction in these programs correctly.

### 4.5 No LLVM linker, no runtime library

- `ld.lld` `22.1.8` stops with `unsupported e_machine value: 4` on an M68k object.
  `lld/ELF/Arch/` has no M68k file at `22.1.8`, and `lld/ELF/Arch/M68k.cpp` returns 404 at
  `llvmorg-23.1.4` and at `main`. Distro lld 18.1.3 segfaults on the same input. The build
  recipe therefore does not build lld, and linking uses `m68k-linux-gnu-ld` from binutils with
  a short linker script. Objects from clang and objects from GNU as link together without a
  diagnostic.
- There is no `compiler-rt` or `libgcc` for M68k, so `* / %` on 32-bit values, which the 68000 has
  no instruction for, would become calls to routines that do not exist. The `selftest` program
  avoids them on purpose. When the first program needs one, it is written once, in assembly, in
  the repository.
- Calls are `jsr` to an absolute address, so a program is linked at the address it runs at. The
  boot block copies the blob there (§8).

### 4.6 Codegen: distro 18 against pinned 22, instruction by instruction

The same C (`tools/m68k/programs/`) was compiled by both and the disassemblies aligned.

| Program | Instructions, 18 → 22 | Aligned identical | What differs |
|---|---|---|---|
| `colour-loop`, `-Os` | 18 → 18 | 17 of 18 | `link.w %a6` → `suba.l #4,%sp` |
| `selftest`, `-Os` | 106 → 102 | 71 of 106 | frame pointer dropped (`link`/`unlk` → `suba`/`adda`), `moveq` for small constants, a dead `sub` in the `popcount` loop gone, registers allocated differently |
| `selftest`, `-O2` | 128 → 124 | 89 of 128 | the same |

Both are correct; the pinned one has three to four per cent fewer instructions and uses `MOVEQ`.

**Does the distro's clang 18 stand rejected, now that its assembler is not used?** As the
project's toolchain, yes. As a C compiler alone it would be acceptable on this evidence: with
clang `18.1.3` compiling the C and GNU as `2.42` and GNU ld doing the rest, `check.sh` passes —
the gate of oracle 1, and oracle 3 on the kernel, `selftest` at `-Os` and `-O2`, `colour-loop`
and its boot block. What keeps it rejected is not the C it produced but what the evidence does
not cover: the corpus is 65 lines of C and one loop program; the distro's version moves with
the release rather than with the project's pin; and it carries the `MOVEM` pre-decrement bug of
§4.2 in a backend whose C path simply has not been seen to use that instruction. So clang 18 is a
stop-gap for a developer who cannot build `22.1.8` and sees `check.sh` pass — not a supported
toolchain.

## 5. What each way of having the toolchain costs

Measured on this host (4 cores, 15 GB RAM, 23 GB free disk) unless marked. The table is for
clang; binutils is in §5.1.

| | (a) Distro package | (b) Per-developer source build | (c) Container image | (d) CI-built artefact |
|---|---|---|---|---|
| What you get | clang 18.1.3 | clang 22.1.8, recipe committed | the (b) prefix in an image | the (b) prefix as a tarball |
| One-time cost | `apt install`, seconds; 80 MB download, about 365 MB installed | **46 minutes** (2 734 s) from a clean state, of which the shallow sparse clone is 86 s | not built: no container daemon on this host. **Estimated** from the prefix: 236 MB plus a base layer | the same build once per pin change; expected to cost about the same on a 4-core runner, not run in CI here |
| Peak disk while building | — | **3.3 GB**, then the 236 MB prefix alone | — | as (b) |
| Peak RAM | — | **5.9 GB** above idle (host-wide, with `LLVM_PARALLEL_LINK_JOBS=1`) | — | as (b) |
| Steady state | 365 MB | **236 MB** prefix (clang, llvm-mc, objdump, objcopy, nm, readelf) | about 250 MB plus a base layer, uncompressed | **58 MB** as `.tar.xz`, 84 MB as `.tar.gz` |
| Correct for this project | C: yes on this corpus, unpinned (§4.6); its assembler is not used | Yes | Yes | Yes |
| Pin is exact | No: whatever the release ships | Yes: `toolchain.pin` | Yes | Yes |
| Developer needs | root, network | about 6 GB of free RAM and under an hour | a container runtime | only to download and unpack |
| Redistribution | none | none | **Apache-2.0 notices apply** (§10) | **Apache-2.0 notices apply** if the artefact is public (§10) |

The first source build, run with the first configuration tried (`clang;lld`), cost 26 minutes up to
the failure of a sparse checkout that omitted a header lld's Mach-O backend wants, and 26 more to
finish, so **about 52 minutes of compiling**; peak disk 4.3 GB (a 2.1 GB sparse clone, a 1.6 GB build tree, a
450 MB prefix), peak RAM 6.6 GB host-wide. Dropping lld, the static analyser and the optional
compression libraries is what makes the recommended recipe cheaper; the column above is that
recipe, measured from nothing by the committed script (configure line in `build-toolchain.sh`; `clang;lld` replaced by `clang`, static analyser, ARC migrator, zlib, zstd and libxml2 off). Its prefix produced byte-identical program blobs to the first build, and passes every check in §7. A later rebuild of the same recipe, run while light checks shared the four cores, took 3 111 s (52 minutes) and produced the same 236 MB prefix and the same program blobs again.

### 5.1 Binutils

| | Distro package | Built from the pinned release |
|---|---|---|
| What you get | `binutils-m68k-linux-gnu` `2.42-4ubuntu2.10` (Ubuntu 24.04) | `2.42` exactly: the release tarball, its SHA-256 in `toolchain.pin` |
| One-time cost | seconds; 1.3 MB download, 5.1 MB installed | **61 s and 71 s** wall in two runs on four cores: download 1 to 15 s for 27 MB, unpack 5 s, configure 2 s, compile 47 to 50 s, install 2 s; `build-binutils.sh` |
| Peak disk while building | — | **583 MB** (27 MB tarball, 374 MB unpacked source, 165 MB build tree, 18 MB prefix) |
| Steady state | 5.1 MB | **18 MB** prefix (`as`, `ld`, `objcopy`, `objdump`, `nm`, `readelf` and the rest of the set, stripped) |
| Developer needs | root, network | `gcc`, `make`, `xz`, `curl`; no `flex`, `bison` or `texinfo` |
| Pin is exact | only where the distribution ships `2.42` | Yes |

Any binutils version is acceptable if oracle 1 passes against it; `check.sh` says which one it
found and notes a difference from the pin. The recipe builds the release tarball, not a git
checkout of its tag: a checkout lacks the generated lexer and parser sources and failed at
`syslex.c` for want of `flex`. The tarball's `gas`, `ld`, `bfd`, `opcodes`, `binutils`,
`libiberty` and `include` trees were compared with a checkout of the tag `binutils-2_42`
(commit `c7f28aad`) and differ by nothing but those generated sources (and some CVS ignore lists).

## 6. Recommendation

**Hosting.** Build clang from source with `tools/m68k/build-toolchain.sh`; publish the same
recipe's output as a CI artefact so a contributor who only wants to assemble a test program
downloads 58 MB instead of building for three quarters of an hour. The build is the authority;
the artefact is a cache of it, keyed on the hash of `toolchain.pin` and the recipe. Binutils
comes from the distribution where it ships the pinned version, and from
`tools/m68k/build-binutils.sh` otherwise: a minute, not an artefact. Keep binutils out of the
published artefact, which then carries Apache-2.0 notices only (§10). Do not offer a container
image until a second consumer wants one: it adds a runtime to the contributor's machine and a
redistribution obligation to the project, and buys nothing the tarball does not. A tarball is
not free of licence duty either (§10).

**Assembling and linking.** Hand-written assembly is assembled by GNU as, `-m68000`, and the
programs are linked by GNU ld; clang is invoked for C only (`-c`, to objects). Branches carry
explicit sizes (§4.3). LLVM's assembler stays in oracle 1 as a recorded column, so that a
future fix is noticed, but nothing depends on it.

**Pinning.** One release of each, upgraded deliberately. The LLVM tag and the binutils release
(version, tarball URL and SHA-256) live in one file, `tools/m68k/toolchain.pin`, and nothing
else in the repository repeats them. Upgrading either is a change of that file plus a run of
`tools/m68k/check.sh`; the check is built to make the upgrade honest — a gap that has closed
turns an `xfail` into a failure, a regression turns an `ok` into one, and the kernel and the
programs must still agree with oracle 3. Tracking `main` is rejected: the backend is
experimental, its own source says unimplemented instructions are "not touched at all", and a
silent change in assembler behaviour would arrive as a change in what a measurement program
measures. Experimental status is acceptable *because* the oracles run on every bump; without
them it would not be. The one upstream fix that matters to us, the immediate source for MOVE
to SR (§4.1), is on `main` and not in a release; GNU as makes it a convenience, not a
dependency.

**Which release.** `22.1.8` is no longer the newest stable: `llvmorg-23.1.4` exists. Its
assembler and disassembler were built and run through oracle 1: the encodings match the manual,
the same rows fail, and the same `MOVEM` disassembly is wrong. With assembly on GNU as, the
assembler's state no longer bears on the choice of release; only its C code generator does, and
that was not run for `23.1.4`. `22.1.8` is the version every other result here was measured on.
The first real bump will also need the recipe to change: configuring `23.1.4` fails unless the
sparse checkout includes `libc/`, which `22.1.8` does not ask for.

## 7. Oracle results

`tools/m68k/check.sh` runs them all. Results for the pinned LLVM `22.1.8` (clang) and GNU
binutils `2.42`:

| Oracle | Subject | Result |
|---|---|---|
| 1 | 29 kernel instructions, assembled by GNU as, bytes against the manual | 29 of 29 identical |
| 1 | the programs' hand-written assembly (`colour_delay`, the boot block stub), GNU as against bytes derived from the manual | 2 of 2 identical |
| 1 | 22 single-instruction probes, GNU as against the manual | 22 of 22 |
| 1 | the same 22 probes through LLVM's assembler, recorded | 8 correct, 13 broken, 1 a different valid encoding (§4.1–4.3) |
| 1 | 27 encodings through LLVM's disassembler, recorded | 26 agree, 1 known-wrong (`MOVEM` pre-decrement text); 2 it cannot read |
| 1 | `move.w #imm,(xxx).L` from compiled C | `33FC 7FFF 00DF F09A` and `33FC 0F00 00DF F180` present |
| 3 | kernel, executed from `kernel` to `done` | 11 of 11 registers as derived from the manual |
| 3 | `selftest`, C, `-Os` and `-O2` | 8 of 8 results; hex formatting, sign-extending sum, popcount loop, xorshift, switch |
| 3 | `colour-loop` | `INTENA`, `INTREQ`, `DMACON` cleared, then `COLOR00` alternates `$0F00`, `$00F0`; 524 309 or 524 310 instructions between writes (the model: 8 passes of 65 538, plus 5 or 6) |
| 3 | `colour-loop` through its boot block | the block copies the blob to the link address; same sequence |

Expected values for `selftest` are computed in Python, independent of both compiler and CPU
model. Built with the distro's clang `18.1.3` for the C and GNU as `2.42` for the assembly,
every row passes too, the LLVM rows being notes rather than failures against an unpinned
compiler.

The kernel contains `ADDQ` and `DBRA` as real instructions. Their encodings (`5283`,
`51CC FFFC`) are the same bytes the previous `.short` workarounds spelled out, so the oracle's
expectation did not change; and the built `colour-loop` blob's `colour_delay` is byte for byte
the one the workarounds produced (`202F 0004 323C FFFF 51C9 FFFE 51C8 FFF6 4E75`).

## 8. Oracle 2: the real A500, and what it is for

Nothing above is a statement about timing, and nothing above has met an Amiga. The program is
built so that the first real-hardware run is as cheap as possible.

1. Build: `tools/m68k/build-toolchain.sh` (clang) and `apt install binutils-m68k-linux-gnu` or
   `tools/m68k/build-binutils.sh`, then `tools/m68k/build-program.sh colour-loop`. The output
   is `tools/m68k/out/colour-loop.adf`, a bootable 901 120-byte disk image (git-ignored; it is
   generated, never committed).
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

### 8.1 A stand-in run in an existing emulator

Before any real A500 run, the disk image was booted in an existing emulator, used as an
observation instrument under `PROVENANCE.md` (its behaviour is observed, its source is not
read):

| | |
|---|---|
| Instrument | FS-UAE (version not recorded), Amiga 500 PAL model, 512 KiB chip RAM |
| ROM | Kickstart 1.3, revision 34.5, identified by SHA-1 `891e9a547772fe0c6c19b610baf8bc4ea7fcb785` and by its header; a dump of a ROM the operator owns, not distributed |
| Disk | `colour-loop.adf` built by `check.sh` at the pinned toolchain (SHA-256 prefix `7edeb41b64c8bb13`) in DF0: |
| Observed | the machine boots from the disk, and the whole screen alternates red and green; each colour lasts a little under one second by eye |
| Expected | red, then green, alternating, about 0.74 s per colour |

What this settles: Kickstart 1.3's boot code accepts the boot block's checksum and runs the
stub, the stub copies the program to `$40000` and jumps to it, and the `COLOR00` writes take
effect in the order the CPU model saw (oracle 3). What it does not settle: the timing seen by
eye is not a measurement, and an emulator's cycle accuracy depends on its configuration. The
`DBRA` cycle count on real hardware therefore stays open for oracle 2 proper. A stopwatch over
ten colour changes (expected about 7.4 s) would turn this run into a coarse timing check.

## 9. Does it make the measurement programs easier?

Measured on the test program, in `tools/m68k/measure/measure.sh`, with the real mnemonics; no
effort was timed.

| | All assembly | C plus assembly |
|---|---|---|
| `colour-loop`, the program as shipped | 20 lines of assembly, 64 bytes | 28 lines of C and 13 of assembly, 98 bytes |
| `selftest`, the harness-shaped C | — | 65 lines of C became 102 instructions (`-Os`) or 124 (`-O2`) |

- **The timing loops get no easier, and no smaller.** `colour-loop` is a *worse* program with a C
  harness: more lines (41 against 20) and more bytes (98 against 64). The `DBRA` loop is
  hand-written either way. Writing it as `dbra` rather than as the `.short` pairs the LLVM
  assembler forced removes two lines from each column (22 and 15 lines of assembly before; 20 and
  13 now) and no bytes (64 and 98 both before and after), so the conclusion does not move.
- **The code around the loops gets considerably easier.** Hex formatting of a result, a sign-extending
  sum, a loop that exits on its data, a table-driven switch and 32-bit shifts are 65 lines of C and about
  100 to 125 instructions the author does not write, schedule registers for, or encode. That is
  1.6 to 1.9 instructions per line of C, and the instructions are verified by oracle 3 rather than
  by eye. This is the claim SPIKE-S2 §3.1 made — the toolchain helps with the harness, not the
  measurement — now measured on a program rather than asserted.
- The honest limit: none of this is a count of hours. A measurement program is mostly loop, and the
  loop is exactly the part the toolchain leaves to hand. What changed is that hand-writing it is now
  an ordinary assembly job: real mnemonics, the manual's encodings checked by oracle 1, and nothing
  to spell out in `.short`.

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
at all — there is no runtime library to embed (§4.5). Second, even where a compiler does embed a
piece of itself in an object, the exception removes the licence-text, notice and modification
conditions for that embedded piece, so nothing is owed in a GPL-3.0-or-later binary that carries
such a piece. The exception's second paragraph concerns GPLv2 and a retroactive waiver of the
patent and indemnity sections; it does not apply here and is not relied on. Apache-2.0 is in any
case one-way compatible with GPL-3.0.

What the exception does **not** cover is redistributing the compiler itself. A container image or
a published CI artefact carries LLVM's binaries, so it needs `LICENSE.TXT` and the notices
Apache-2.0 §4 asks for, shipped beside it. The build script does not yet package them (§11).

**GNU binutils** (`as`, `ld`, `objcopy`, `objdump`) are under the **GNU General Public License,
version 3 or later**: `COPYING3` is in the root of the examined `2.42` release, and the headers
of `gas/as.c` and `ld/ldmain.c` say "either version 3 … or (at your option) any later version".
Like LLVM they are run at build time and linked into nothing the emulator ships. The licence of
a tool does not pass to what the tool is run on: the GNU project's own position (the GPL FAQ,
"GPLOutput") is that the output of a program inherits the licence status of its input, unless
substantial parts of the output are copied from the program itself. An assembler translates
this project's source into machine code, and `ld`, given only this project's objects and its
own short linker script, with no startup files and no libraries, adds none of its own text;
`objcopy -O binary` then strips everything but the section contents. The blobs therefore
carry no obligation from binutils, and the question would in any case be moot between two
GPL-3.0-or-later works. What does carry GPL-3.0 duties is redistributing the binutils binaries:
source or a written offer for it. A published CI artefact would owe that, which is a second
reason (§6) to keep binutils out of it and have contributors take it from their distribution or
build it from the pinned tarball. This paragraph is the author's reading of the texts, for the
project owner to confirm; it is not legal advice.

## 11. Open

- **Oracle 2.** §8. Until it runs, no claim here is about hardware.
- **Newer tag.** If a bump is wanted, run the whole of `check.sh` on `llvmorg-23.1.4`: only its
  assembler and disassembler have been checked (§6).
- **Package the notices** with any published clang artefact (§10), and decide where it is published.
- **A runtime library** (`__mulsi3`, `__divsi3` and friends) the first time a program needs one.
- **SPIKE-S2 §7, second item** — ELF to hunk for the filesystem handler — is untouched by this
  spike. Nor is the JIT item.
- **CI.** `check.sh` is runnable; whether it becomes a job depends on the artefact decision above.
- **Unused LLVM tools.** The recipe still builds `llvm-objdump`, `llvm-objcopy`, `llvm-readelf`
  and `llvm-nm`; nothing in the build or the checks calls them any more (`llvm-mc` is used by
  oracle 1's disassembler row). Dropping them would shorten the build, and the 46 minutes in §5
  would then need measuring again.
