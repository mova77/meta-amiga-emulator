# Design spikes

Buildable designs for the parts of the system where the algorithm is the hard bit. An ADR
records *what was decided and why*; a spike records *how it works* in enough detail to
implement without re-deriving it.

A spike is written **before** the code it governs and is accepted before implementation
starts. Where a design depends on hardware behaviour that has not been transcribed and
verified, the spike says so explicitly and marks it as work that gates acceptance — a
guessed constant in a foundational table is worse than an admitted gap.

| Spike | Covers | Status |
|-------|--------|--------|
| [SPIKE-S0](SPIKE-S0-core-timeline.md) | The core timeline: event scheduler, DMA slot allocator, bus arbitration | Draft |
| [SPIKE-S1](SPIKE-S1-m68k-instruction-table.md) | The 68k instruction table schema and its build-time generator | Accepted |

## Status vocabulary

**Draft** — under review; nothing may be implemented against it.
**Accepted** — implementation stories may start.
**Superseded by SPIKE-…** — kept, so the reasoning trail survives.
