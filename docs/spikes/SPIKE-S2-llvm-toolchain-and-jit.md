# SPIKE-S2 — LLVM: an M68k toolchain now, a JIT backend later

| | |
|---|---|
| **Status** | Draft — findings complete, recommendation open |
| **Date** | 2026-07-27 |
| **Relates to** | [ADR-CPU-02](../adr/ADR-CPU-02-68k-core-strategy.md) D6 · [ADR-ACCEL-07](../adr/ADR-ACCEL-07-cpu-and-chipset-acceleration.md) D1 · [ADR-PORT-04](../adr/ADR-PORT-04-portability-and-backends.md) D6 |
| **Examined** | `llvmorg-22.1.8` — the current stable release; `main` is `24.0.0git` |

## 1. The question, and why it has two answers

"Can LLVM optimise codegen for the M68k?" splits into two efforts that point in opposite
directions, and the reading most people reach for first is the one that does not help.

| | Direction | Produces | Helps the emulator? |
|---|---|---|---|
| **A · The M68k target backend** | host → 68k | 68k machine code | **No.** It compiles code that runs *on* the Amiga. Emulation speed is untouched. |
| **B · ORC/JITLink as a dynamic translator** | 68k → host | host machine code | **Yes, eventually.** This is the deferred fork in ADR-CPU-02 D6. |

Both were examined. A turns out to be immediately useful for something else entirely; B
turns out to carry less risk than assumed, without becoming due any sooner.

## 2. What was actually inspected

A sparse checkout of `llvmorg-22.1.8` — 65 MB rather than the ~2 GB a full shallow clone
costs — covering `llvm/lib/Target/M68k`, `llvm/lib/ExecutionEngine`,
`llvm/include/llvm/ExecutionEngine` and `llvm/docs`. Every claim below is from those files,
not from recollection.

## 3. Finding A — the M68k backend is a usable toolchain, and the project needs one

`llvm/lib/Target/M68k/M68k.td` defines subtarget features `isa-68000`, `isa-68010`,
`isa-68020`, `isa-68030`, `isa-68040`, `isa-68060` and FPU features `isa-68881`,
`isa-68882`, with processor definitions for each — **exactly the CPU set this project
emulates** (specification §2.2). The backend carries an AsmParser, a Disassembler and a
GlobalISel implementation (`GISel/M68kInstructionSelector.cpp`, `M68kLegalizerInfo.cpp`,
`M68kRegisterBankInfo.cpp`).

This matters because two pieces of work require *writing 68k code*, and both currently
imply hand-written assembly:

- **The hardware verification programs** that gate the timing core. SPIKE-S0 §3.2 requires
  original test programs, run on real hardware, measuring CPU cycles available per line
  under each DMA enable combination. That work sits on the project's critical path.
- **The Amiga-side filesystem handler** for directory-mapped volumes (specification S-1),
  which must be ours because no third-party handler binary may be embedded.

A working C toolchain makes both tractable. That is a bigger practical win than anything on
the JIT side, and it is available today.

### 3.1 Constraints, none of them fatal

- **M68k is an experimental target.** `llvm/CMakeLists.txt` lists it under
  `LLVM_ALL_EXPERIMENTAL_TARGETS`, not `LLVM_ALL_TARGETS`. It is absent from stock LLVM and
  Clang distributions; building it requires
  `-DLLVM_EXPERIMENTAL_TARGETS_TO_BUILD=M68k`. Experimental also means a lower quality bar
  and no release-to-release stability promise.
- **No AmigaOS target.** It emits ELF. There is no hunk format and no libc. For bare-metal
  test programs that is irrelevant — extract `.text`, load at a known address. The
  filesystem handler would need hunk conversion or a linker script.
- **Compiler output has unpredictable timing.** The programs in SPIKE-S0 §3.2 *measure
  cycles*, so their inner loops must stay hand-written assembly regardless. The toolchain
  helps with everything around those loops — setup, result formatting, the harness — not
  with the measurement itself.
- **It is a build-time dependency only.** It never links into the emulator, so
  ADR-PORT-04 D6's runtime-dependency bar does not apply.

## 4. Finding B — the JIT direction is better supported than assumed

`llvm/lib/ExecutionEngine/JITLink/` contains `MachO_arm64`, `ELF_aarch64`, `MachO_x86_64`,
`ELF_x86_64` and `COFF_x86_64` — **every host platform and architecture combination this
project targets**, on both x86-64 and AArch64. ORC provides `CompileOnDemandLayer` for lazy
compilation and the `EPC*` family for out-of-process execution.

So one of the risks implicitly carried by ADR-CPU-02 D6's deferral — "will ORC even support
our hosts?" — is retired. It does, on all six combinations.

(Incidentally, `LLVM_TARGETS_WITH_JIT` is `X86 PowerPC AArch64 ARM Mips SystemZ`, without
M68k. Irrelevant to us: we JIT *from* 68k, never *to* it. It is noted only so nobody
mistakes its absence for a blocker.)

What the deferral still turns on is unchanged: LLVM's compile latency against a
hand-written dynarec's, and LLVM's size as a runtime dependency — hundreds of megabytes,
which ADR-PORT-04 D6 says needs its own ADR. Neither is answerable without benchmark data,
which is why ADR-CPU-02 D6 defers it.

## 5. Finding C — customising LLVM does not mean forking it

Three levels were considered.

1. **A reduced pass pipeline — worth doing, when the time comes.** LLVM's `O2` pipeline is
   tuned for whole-program ahead-of-time compilation. Emulator-generated IR is small
   blocks, dominated by flag computation, with little of the aliasing ambiguity the
   expensive passes exist to resolve. Compile latency is a JIT's principal cost, so a lean
   pipeline is the highest-value tuning available. `PassBuilder` constructs one through
   public API — **configuration, not a fork**.
2. **Flag-computation elision — the biggest single win, and it does not need LLVM.** Not
   computing the NZVC bits that nothing subsequently reads is what separates a fast 68k
   translator from a slow one. It is best done in *our own* intermediate representation
   before any LLVM IR is emitted, where the 68k semantics are still visible. Doing it as an
   LLVM pass means first discarding the information that makes it easy.
3. **Modifying LLVM itself — not warranted.** Everything above is reachable through public
   APIs. A fork is a permanent maintenance tax against a fast-moving upstream, and it would
   put the project's clean-room provenance story next to a large body of third-party code
   for no gain.

**Recommendation: do not fork LLVM.** If LLVM is chosen as the JIT backend, use it as a
library with a custom `PassBuilder` pipeline, and keep the domain-specific optimisation in
our own IR upstream of it.

## 6. What this changes, and what it does not

**Changes:** the M68k backend becomes a candidate build-time toolchain for the 68k code the
project must write anyway. That is actionable now and touches the critical path.

**Does not change:** the acceleration ordering in ADR-ACCEL-07 D1 — batching, then decode
memoisation, then SIMD, then a JIT last — or ADR-CPU-02 D6's deferral of the LLVM-versus-
dynarec fork to phase 7. Nothing found here argues for pulling that forward; the ORC
support merely means the option will still be there when the benchmark data exists.

## 7. Open items

- Whether to build and pin an M68k toolchain, and where it lives — a per-developer build,
  a container image, or a CI-built artefact. Raised as its own story.
- Whether the filesystem handler's ELF-to-hunk step is a bespoke tool or an existing free
  one, and what that implies for the licence audit.
- Whether the experimental target's stability is good enough to depend on, or whether the
  toolchain is pinned to one LLVM release and upgraded deliberately.
- For phase 7: measured compile latency of an ORC pipeline against a hand-written dynarec,
  on representative translated blocks. Until that exists the fork stays open.
