# ADR-PERF-06 — Optimisation policy: C++23 by default, SIMD by measurement, assembly by exception

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | Language level, toolchain, hot-path optimisation, assembly policy |
| **Depends on** | [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) · [ADR-CPU-02](ADR-CPU-02-68k-core-strategy.md) · [ADR-TEST-05](ADR-TEST-05-compatibility-measurement.md) |

## Context

Slot-accurate emulation (ADR-CORE-01) is expensive by construction, so the project needs
real optimisation, not the appearance of it. It also needs identical results on x86-64 and
AArch64 across three platforms, which is precisely what hand-optimisation tends to break.

The temptation is to write assembly early, in the places that *look* hot. In emulators
those guesses are usually wrong: the cost is rarely in the arithmetic and usually in
dispatch, branch misprediction and memory traffic. Assembly written against a wrong guess
is permanent maintenance cost for nothing, and it is a second implementation that can
disagree with the first.

## Decision

**D1 · C++23 is the baseline** — Clang ≥ 17, GCC ≥ 13, MSVC ≥ 19.38. `std::bit_cast`,
`[[assume]]`, `[[likely]]`, designated initialisers, `constexpr` table generation and
`std::span` do most of what hand-written code used to be needed for. Modules are not
adopted yet; toolchain support is still uneven across the three platforms and the build
must work everywhere.

**D2 · Optimisation follows a profile, or it does not happen.** No optimisation lands
without a benchmark before and after, on both architectures, recorded in the commit. A
change that cannot demonstrate its improvement is reverted regardless of how obviously
correct it looks.

**D3 · The order of resort is fixed:**

1. Better algorithm or data layout — usually the whole win.
2. Portable C++ written so the compiler can vectorise it, with the vectorisation verified
   in the generated code rather than assumed.
3. SIMD intrinsics behind a common wrapper, with NEON and AVX2 paths and a scalar
   reference that is always built and always tested.
4. Hand-written assembly.

Step 4 requires an ADR of its own, naming the function, the measured gain over step 3, and
who maintains it. "LLVM will not generate this" is a claim to be demonstrated by
disassembly, not asserted.

**D4 · Every optimised path keeps a scalar reference implementation**, compiled into every
build and exercised by a differential test asserting bit-identical output. This is
ADR-CPU-02 D2's principle applied generally: the fast thing is only trustworthy because
the slow thing is still there to check it against.

**D5 · The likely hot paths, in expected order** — recorded so profiling has a hypothesis
to falsify, not so they can be optimised on sight:

| Path | Why | Likely technique |
|------|-----|------------------|
| 68k dispatch loop | Executed billions of times; branch-prediction bound | Threaded dispatch (ADR-CPU-02 D3), handler layout |
| Bitplane → chunky serialisation | Up to 8 planes × 1 280 px × 313 lines × 50 Hz | SIMD bit transpose (NEON/AVX2) |
| Blitter inner loop | Barrel shift + minterm over large areas | SIMD, specialised by minterm and shift |
| Slot allocator | Consulted every colour clock | Precomputed per-line slot table, invalidated on register write |
| Audio resampling | Band-limited, 4 channels | SIMD FIR, block-processed |
| Savestate / rewind | Large state, frequent | Delta encoding, not compression |

**D6 · Determinism outranks speed, always.** No optimisation may introduce
platform-dependent results: no fast-math, no unspecified evaluation order affecting
emulated state, no address-derived or timing-derived behaviour. Where a SIMD path cannot be
made bit-identical to the scalar reference, the SIMD path does not ship.

**D7 · The JIT is not an optimisation, it is an architecture decision**, and it stays
deferred to phase 7 under ADR-CPU-02 D6. Interpreter-tier performance is pushed as far as
D1–D5 take it first — partly because that is where the OCS/ECS target is actually met, and
partly because the JIT decision needs the profile data that only a fast interpreter
produces.

## Consequences

- Early phases will look under-optimised and that is correct. Optimising before the
  compatibility corpus exists means optimising without the ability to prove correctness was
  preserved.
- Maintaining a scalar reference alongside every SIMD path is real duplication, accepted as
  the cost of D4. Both are generated from the same source where the shape allows it.
- Requiring a per-function ADR for assembly makes assembly rare. That is the intent: the
  goal is a fast emulator, not an emulator with assembly in it.
- Benchmarks become project infrastructure — stable machines, recorded baselines, tracked
  over time — otherwise D2 degrades into anecdote.

## Open decisions

- Benchmark harness: a microbenchmark library plus corpus-derived macro benchmarks, and
  where the reference numbers are hosted so they survive machine changes.
- Whether PGO and LTO are used for release builds, and whether the profile data is
  committed or regenerated from the corpus at build time.
