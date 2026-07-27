# Architecture decision records

Decisions that shape the system, with the reasoning that produced them. An ADR is written
before the code it governs, and is amended rather than quietly outgrown.

Naming: `ADR-<SCOPE>-<NN>-<slug>.md`, where scope is the subsystem the decision governs.
Numbers are allocated once and never reused.

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) | One colour-clock timeline: DMA-slot-accurate chipset scheduling | Accepted |
| [ADR-CPU-02](ADR-CPU-02-68k-core-strategy.md) | 68k core: a generated interpreter as permanent oracle, JIT deferred | Accepted |
| [ADR-ROM-03](ADR-ROM-03-kickstart-rom-handling.md) | Kickstart ROMs: identify by hash, decrypt Amiga Forever, ship AROS, bundle nothing | Accepted |
| [ADR-PORT-04](ADR-PORT-04-portability-and-backends.md) | A freestanding core behind explicit ports; SDL3 as the reference backend | Accepted |
| [ADR-TEST-05](ADR-TEST-05-compatibility-measurement.md) | Compatibility is a measured number, not a claim | Accepted |
| [ADR-PERF-06](ADR-PERF-06-optimisation-policy.md) | Optimisation policy: C++23 by default, SIMD by measurement, assembly by exception | Accepted |

## Reading order

ADR-CORE-01 first — every other decision here is downstream of the timing model. Then
ADR-PORT-04 for the module boundaries, ADR-CPU-02 for the core that fills them,
ADR-TEST-05 for how any of it is shown to work, and ADR-PERF-06 for what may be done to
make it fast. ADR-ROM-03 stands alone and is mostly a licensing boundary.

## Status vocabulary

**Proposed** · **Accepted** · **Superseded by ADR-…** · **Deprecated**. A decision that
turns out wrong is superseded by a new ADR that says so and why; the original stays, so
the reasoning trail survives.
