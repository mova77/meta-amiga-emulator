# ADR-CPU-02 — 68k core: a generated interpreter as permanent oracle, JIT deferred

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | 68000 · 68010 · 68020 · 68030 · 68040 · 68060 · FPU · MMU |
| **Depends on** | [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) |

## Context

The 68k core has to satisfy two requirements that pull in opposite directions. It must be
**exact** — correct flags, correct exception stack frames per model, correct bus cycle
counts feeding the slot allocator, correct behaviour for the undefined-but-observable
cases that real software hits. And it must eventually be **fast**, because an emulated
68040 at slot accuracy is expensive.

Trying to satisfy both in one core is how emulator projects acquire permanent, unfindable
bugs: a JIT is fast and opaque, and when a demo desyncs there is nothing to compare
against.

Hand-writing the interpreter is also not attractive. The 68000 has ~80 instruction forms
across 8 addressing modes with size variants; written by hand that is tens of thousands of
lines of near-duplicate code where every duplicate is a place for a flag bug to hide. The
020+ additions make it worse.

## Decision

**D1 · The interpreter is generated.** Instruction semantics are written once per
operation in a declarative table — operation, sizes, legal addressing modes, flag effects,
per-model cycle costs, per-model availability. A build-time generator expands it into the
65 536-entry opcode dispatch table and the handler bodies. One semantic bug fixed in one
place, not in 24 expansions of it.

**D2 · The interpreter is the permanent oracle.** It is never retired, never bypassed and
never "the slow path we stopped testing". Every faster tier is validated by differential
execution against it: identical initial state, identical instruction stream, identical
architectural state and identical bus-cycle sequence afterwards. A divergence is a bug in
the fast tier, by definition.

**D3 · Dispatch is a computed-goto threaded interpreter** where the compiler supports it
(Clang and GCC), with a portable `switch` fallback for MSVC. The dispatch loop is the
single hottest path in the program and is measured, not assumed —
[ADR-PERF-06](ADR-PERF-06-optimisation-policy.md) governs what may be done to it.

**D4 · Bus cycles are explicit.** Handlers do not return a cycle count; they perform reads
and writes through the bus interface, which schedules against the Agnus slot allocator per
ADR-CORE-01 D5. Prefetch behaviour (the 68000's two-word prefetch queue, the 020+
instruction cache and pipeline) is modelled, because software observes it.

**D5 · Per-model behaviour is data, not `#ifdef`.** Exception stack frame formats,
instruction availability, cycle costs, address-error behaviour, and the 040/060
unimplemented-instruction traps are table entries selected by the configured model. A
model is added by adding rows.

**D6 · The JIT decision is deferred to phase 7, deliberately.** LLVM ORC versus a
hand-written dynarec is a real fork — ORC is portable and gives us the optimiser for free
but carries a heavy dependency, long compile latency and awkward deoptimisation; a dynarec
is small and fast to enter but must be written per architecture. Choosing now would be
choosing without the benchmark data that decides it. D2 makes the deferral safe: whichever
wins is validated against a core that already exists and is already correct.

The interpreter must therefore be fast enough to make the JIT optional for OCS/ECS
machines, which is the realistic target — a 7 MHz 68000 at slot accuracy is well within a
modern desktop CPU's budget. The JIT exists for accelerated AGA configurations.

## Consequences

- The generator is a build dependency and a piece of software in its own right, with its
  own tests. Generated sources are not committed; the table is the source of truth. Its
  design is [SPIKE-S1](../spikes/SPIKE-S1-m68k-instruction-table.md).
- Differential testing (D2) needs the fast tier to be steppable in lockstep with the
  interpreter, which constrains the JIT's block granularity. This is a known cost of the
  deferral and is recorded as an open decision in ADR-CORE-01.
- Third-party 68k cores (Musashi, Cyclone, and the UAE-derived cores) are excluded by
  [PROVENANCE.md](../../PROVENANCE.md) regardless of technical merit. The table-driven
  approach is partly a response to that: it makes writing our own tractable.
- Validation needs a test suite before the core is trusted. Original test programs
  asserting per-instruction flag and timing behaviour are written alongside the core, not
  after it.

## Open decisions

- Whether the MMU is modelled for all of 68030/040/060 or only where the corpus requires
  it (Kickstart's `mmu.library`, Enforcer-style tools, some 040 setups).
- FPU: whether to implement 68881/2 arithmetic against host `long double` / soft-float, and
  how to reach bit-exactness for the transcendental functions, whose results software does
  compare.
