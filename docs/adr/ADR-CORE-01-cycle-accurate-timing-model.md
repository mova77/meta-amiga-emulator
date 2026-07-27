# ADR-CORE-01 — One colour-clock timeline: DMA-slot-accurate chipset scheduling

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | Every emulated subsystem — CPU, Agnus, Copper, Blitter, Denise, Paula, CIA |
| **Supersedes** | — |

## Context

The Amiga is not a CPU with peripherals attached; it is a set of coprocessors sharing one
memory bus on a fixed slot schedule, with the CPU as the lowest-priority participant. A
scanline is 227 colour clocks, each one a DMA slot, allocated in a fixed order: memory
refresh, disk, audio, sprites, bitplanes, then whatever is left to Copper, Blitter and
CPU.

This is not an implementation detail — it is the machine's observable behaviour. Programs
depend on it constantly and deliberately:

- Enabling bitplanes changes how many cycles the CPU gets, so a routine's *execution
  speed* is a function of the display mode. Demos time effects against this.
- The Copper writes registers at exact beam positions; a raster split is a `WAIT` on a
  beam coordinate followed by a `MOVE` that must land before the beam draws the next
  pixel.
- Blitter-CPU contention under `BLTPRI` determines whether a blit finishes before the
  beam reaches the area it is drawing into. Tearing, or its absence, is a timing outcome.
- Copy protections and disk loaders measure their own execution against CIA timers and
  the beam counters.

Three modelling tiers were available:

1. **Frame-accurate** — render once per frame. Runs most games, fails almost all demos.
2. **Scanline-accurate** — evaluate register state at line boundaries. Runs most things,
   fails mid-scanline raster effects, Blitter contention timing, and sprite reuse. In
   practice this caps compatibility somewhere below 95 %, and the failures are
   concentrated in exactly the demoscene material this project targets.
3. **Slot-accurate** — schedule every subsystem on the colour clock.

The ≥99 % goal across games *and* demoscene forecloses the first two. Retrofitting tier 3
onto a tier-2 core is a rewrite, not a refactor — the state machine, the register-write
path and the rendering path all change shape.

## Decision

**D1 · One timeline.** A single monotonic colour-clock counter is the only notion of time
in the core. Every subsystem advances by being scheduled on it. No subsystem keeps a
private clock, and no subsystem is "caught up" retroactively.

**D2 · The slot allocator is the arbiter.** Agnus owns a per-line slot table computed from
`DMACON`, `DDFSTRT`/`DDFSTOP`, `BPLCON0` bitplane count and fetch mode, sprite enables and
audio state. Every bus participant asks the allocator for a slot and stalls if refused.
The CPU is a client of this allocator, not an exception to it.

**D3 · Beam-accurate pixel output.** Denise emits pixels as the beam advances, reading the
register state live. A register written mid-scanline affects the pixels after it and not
the pixels before it, without special-casing. Deferred or per-line rendering is
prohibited.

**D4 · The Blitter is scheduled, not immediate.** Blits consume slots at the rate the
hardware consumes them; `DMACONR`'s busy bit and the blitter-finished interrupt become
correct as a consequence rather than as an approximation.

**D5 · CPU bus cycles are real.** The 68000 core requests read and write cycles against
the allocator with the correct cycle counts per addressing mode and the correct chip-RAM
versus fast-RAM cost. Instruction timing is emergent, not table-driven per instruction.

**D6 · Determinism is a build-enforced invariant.** Given the same configuration, media
and input script, a run is bit-identical across platforms, architectures and optimisation
levels. Floating point in the emulation path is either absent or strictly specified;
iteration order over containers is deterministic; no wall-clock or address-derived value
influences emulated state.

## Consequences

**Cost.** Slot-accurate emulation is roughly an order of magnitude more work per emulated
second than scanline approximation. A 7 MHz A500 is cheap; an accelerated 68040 A4000 with
8 bitplanes is not. This is the price of the compatibility target and it is accepted
knowingly — [ADR-PERF-06](ADR-PERF-06-optimisation-policy.md) covers how the cost is
brought back down without compromising D1–D6.

**Design constraint.** Subsystems cannot be developed in isolation with private notions of
time. Every subsystem lands with its scheduling behaviour and its timing tests together.

**Payoff beyond accuracy.** D6 makes the entire compatibility corpus (§9 of the
specification) mechanisable — a demo either produces the reference frame hashes or it does
not — and makes regressions bisectable. Savestates and rewind fall out of it. Without
determinism, "99 % compatible" would remain an assertion.

**Risk.** The scheduler is the one component the whole system's correctness rests on. It
is specified and tested before any subsystem uses it, and its tests are the first thing in
CI.

## Open decisions

- Slot granularity for models where the CPU runs asynchronously to the chipset (accelerated
  68030/040/060 with fast RAM): whether to model the asynchronous boundary faithfully or to
  keep the CPU on the chipset timeline at a scaled rate.
- Whether the JIT tier can be permitted to batch bus cycles between chipset-visible
  accesses, and how equivalence against the interpreter is then proven.
