# ADR-ACCEL-07 — Acceleration strategy: event-bounded batching first, translation last

| | |
|---|---|
| **Status** | Accepted (strategy) — D6 and D7 are open investigations, not decisions |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | How the emulator is made fast: host ISA mapping, threading, pipelining, batching |
| **Depends on** | [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) · [ADR-CPU-02](ADR-CPU-02-68k-core-strategy.md) · [ADR-PORT-04](ADR-PORT-04-portability-and-backends.md) · [ADR-PERF-06](ADR-PERF-06-optimisation-policy.md) |

[ADR-PERF-06](ADR-PERF-06-optimisation-policy.md) is the *policy* — what we are permitted to
do and what evidence a change must carry. This ADR is the *strategy* — where the speed is
actually expected to come from, and which superficially attractive routes are dead ends.
The two are complementary; nothing here escapes ADR-PERF-06 D2's requirement of a
measurement before it lands.

## Context

Slot-accurate emulation is expensive by construction, so the project needs a credible
answer to "how does this ever run full speed". Three answers present themselves, and two of
them are traps.

**Is there hardware acceleration for the 68k?** No, and there will not be. No ARM or x86
core decodes 68000 instructions, and there is no legacy mode to borrow — AArch32 is not
merely unused here, it is absent from Apple silicon and from the newer Cortex-X and
Neoverse cores. "Hardware acceleration" for a 68k guest means software binary translation
and nothing else.

Rosetta 2 is the instructive counter-example. Its one genuine silicon assist is an
Apple-private mode that forces TSO memory ordering so x86's model survives translation. A
68k Amiga guest is uniprocessor: there is no guest memory ordering to preserve. The single
thing Apple needed hardware for is a non-problem here — which is worth stating, because it
removes the temptation to go looking for an equivalent.

**Is the CPU even where the time goes?** Mostly not. Under ADR-CORE-01, a guest memory
access is not a load. It is an alignment check, a memory-map decode, a bus-slot request that
may stall for several colour clocks, and — for a custom register — a write side-effect that
may reschedule the Copper and invalidate the slot table. That is dozens of host instructions
around a few instructions of actual 68k semantics. Translating the arithmetic optimises the
small part.

This is not hypothesis. In the established emulator in this space, the JIT and the
cycle-exact mode are mutually exclusive: speed is bought by surrendering the accuracy that
is this project's entire thesis. We decline that trade, so we need the speed elsewhere.

## Decision

**D1 · Acceleration is software, and translation is the last resort, not the first.**
The ordering is: event-bounded batching (D4) → decode memoisation (D5) → SIMD on the
chipset hot paths (ADR-PERF-06 D5) → and only then the JIT tier, which stays deferred to
phase 7 under ADR-CPU-02 D6 and stays scoped to accelerated configurations where the CPU is
genuinely asynchronous to the chipset.

**D2 · AArch64 is a first-class target, and the mapping is recorded rather than
rediscovered.** It is a better host for a 68k guest than x86-64, and the reason is the
register file:

| 68k | AArch64 | Note |
|---|---|---|
| 8 data + 8 address registers | 31 GPRs | All 16 guest registers can be pinned permanently, leaving ~15 for memory base, cycle counter, CPU-state pointer and EA temporaries. On x86-64's 16 GPRs this is impossible and the difference is constant spilling. |
| `N Z V C` | `NZCV` | Direct correspondence — **except C on subtract**, where ARM sets carry for *no borrow* and the 68k sets it for *borrow*. Inverted at the point of use or folded into lazy-flag state. |
| `X` | — | No host equivalent. Ordinarily a copy of C at operation time; materialised separately. |
| `(An)+` / `-(An)` | post-/pre-indexed addressing | Near-exact correspondence. |
| `d8(An,Xn*s)` | `[Xn, Xm, LSL #k]` | Close, not exact: AArch64 scales only by log2 of the access size, so the 68k's independent 1/2/4/8 scale sometimes needs an explicit shift. |
| Byte/word ops preserving the upper bits of `Dn` | `BFI` / `BFXIL` | One instruction, but it creates a dependency on the prior register value — a real hazard for the out-of-order engine. |
| Big-endian | `REV16` / `REV32` | One instruction per access. |

This holds for the interpreter as much as for any future JIT, and it is the basis for
expecting the interpreter to reach full speed on OCS/ECS machines without a JIT at all —
which is what ADR-CPU-02 D6's deferral is betting on.

**D3 · The emulation core stays single-threaded. This is not a limitation to be engineered
around; it is a property of the machine.** The chips share one bus on a slot schedule with
interdependence at one colour clock — 282 ns on PAL. Cross-core synchronisation costs tens
of nanoseconds at best, against a comparable amount of actual work per slot, so
subsystem-per-thread would run *slower* and would forfeit determinism (ADR-CORE-01 D6),
which the entire compatibility measurement rests on. Speculative parallelism with rollback
fails for the same reason from the other direction: on a machine this tightly coupled the
divergence rate approaches certainty.

Thread-per-subsystem is a sound technique for loosely coupled machines with independent
coprocessors and separate memory. The Amiga is the opposite extreme, and this decision does
not generalise beyond it.

Threads are used, but only past the port boundary (ADR-PORT-04): presentation and scaling,
audio output, media decoding, savestate compression, the GUI, and — when it exists —
background JIT compilation. Additionally, the compatibility corpus (ADR-TEST-05) is
embarrassingly parallel *across runs*, which is the highest-value use of a multicore host in
this project and has nothing to do with the emulation core.

**D4 · Event-bounded batching is the primary acceleration mechanism, and the scheduler
already provides its boundary.**

The hardware's display path is a pipeline — Agnus fetches, Denise serialises, priority and
collision resolve, colour lookup emits. Emulating it a pixel at a time pays per-pixel
overhead; batching it naively breaks mid-scanline register changes, which is the one thing
this project cannot get wrong.

The resolution: **batch only across an interval in which every input to the batched
computation is constant.** Every such change arrives as a scheduled event, so
`Scheduler::nextDue()` is already an upper bound on that interval. Run the pipeline as a
vectorised burst up to the next event, handle the event, continue. Exactness is preserved
*by construction* rather than by care — there is no code path that batches across a change,
because the bound is computed from the same structure that delivers the change.

The same shape applies throughout:

| Subsystem | Batch bound | Typical run |
|---|---|---|
| Denise pixel output | next register write or line end | a PAL line is 227 colour clocks — 454 lores pixels; a Copper writing 8 registers per line still leaves runs averaging ~57 pixels |
| Blitter | next CPU access that could observe the blit | a full blit row |
| Paula audio | next period, volume or DMA change | the period register *is* the colour-clock count per sample — 124 minimum |
| Slot allocator | next write to a feeding register | a whole scanline (already the design in SPIKE-S0 §3.1) |

Two honest caveats. First, **the bound is conservative**: the scheduler knows when the CPU
next takes a bus cycle, not whether that cycle will touch the batched subsystem's inputs. So
CPU-heavy code yields short batches. Refining the bound — bounding only on accesses that
could reach those inputs — is a genuine optimisation with a genuine correctness obligation,
and it needs its own justification. Second, **the win is workload-dependent**: Workbench
batches whole scanlines, a Copper-per-cycle demo degenerates to per-pixel. The
compatibility corpus is the right instrument to measure that across real material, and no
batching change lands without it.

**D5 · Decode is memoised; bus cycles are not.** Instruction decode is a pure function of
the fetched bytes and can be cached per guest address — handler pointer plus pre-decoded
operands. The *bus traffic* of instruction fetch is observable and stays on the schedule;
only the decode work is elided. Self-modifying code is common on this machine, in demos and
in copy protections both, so the cache is invalidated on writes to cached ranges, and the
68000's observable prefetch queue is modelled regardless.

**D6 · Micro-op decomposition — open investigation, and it amends
[SPIKE-S1](../spikes/SPIKE-S1-m68k-instruction-table.md).** Decomposing each instruction
into internal micro-ops (compute EA → bus read → ALU → flags → bus write) is attractive for
a reason unrelated to speed: SPIKE-S1 §7 requires a handler to be suspendable mid-instruction
when the bus stalls, and a micro-op stream makes suspension a natural boundary between ops
instead of bespoke resume state in every handler. It is also closer to the hardware — the
68000 is microcoded, with real microcode and nanocode ROMs.

The cost is per-op dispatch overhead, which is exactly what the interpreter cannot afford.
The proposed resolution, to be evaluated rather than assumed: let the instruction table
describe the micro-op sequence, and have the generator emit **fused handlers for the
interpreter and micro-op streams for the JIT** from the same declaration. If that holds it
serves both tiers and resolves the suspension problem; if it does not, the fused handler
stays and suspension is solved per handler. This must be settled before SPIKE-S1 is
implemented, because it changes what the generator emits.

**D7 · Bounded CPU run-ahead — open investigation.** Running the CPU ahead of the chipset
and replaying its bus requests is unsound in general: the CPU's inputs depend on chipset
state. There is a bounded form that is sound — running ahead *only while the CPU is provably
not touching the chip bus*, which on accelerated configurations with fast RAM is a large
fraction of execution. This is the same question as ADR-CORE-01's open decision on
asynchronous CPUs, approached from the performance side, and the two must be settled
together.

**D8 · Determinism is unaffected by everything above, or the change does not land.** None
of D4, D5, D6 or D7 may make a run non-reproducible. Batching changes *when* work is done,
never *what* is observed; the differential-execution machinery of ADR-CPU-02 D2 and the
corpus of ADR-TEST-05 are what prove it, and a batched build must produce identical
checkpoint hashes to an unbatched one.

## Consequences

- The chipset, not the CPU, is where the acceleration work lives. Bitplane serialisation and
  the Blitter are the SIMD targets already named in ADR-PERF-06 D5, and D4 is what makes
  them reachable — you cannot vectorise a pipeline you are stepping one pixel at a time.
  That work arrives in phase 4, not phase 7.
- Every batched subsystem needs an unbatched reference implementation, built and tested in
  every configuration, per ADR-PERF-06 D4. The batching *is* the optimisation.
- D4 constrains subsystem design: a subsystem must be able to state which registers feed it,
  so its batch bound can be computed. This is a design obligation on every chipset story
  from the start, and retrofitting it is expensive.
- D3 makes the single-threaded core a stated invariant rather than a temporary state, which
  means the port layer carries the whole threading story and needs to be right early.
- The corpus becomes load-bearing twice over: as the correctness proof and as the
  performance instrument. That raises the priority of building it early.

## Open decisions

- D6 and D7 as stated — both need a spike before the work they touch begins.
- Whether the D4 batch bound is refined from "next CPU bus cycle" to "next access that could
  reach these inputs", and what proves the refinement safe.
- Whether decode memoisation (D5) is per-address or per-page, and how invalidation interacts
  with the 020+ instruction cache, which is itself observable.
- Whether AArch64 and x86-64 SIMD paths share a wrapper or are written separately, once
  there is a measurement to argue from.
