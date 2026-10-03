# The core timeline as built: scheduler diagrams

| | |
|---|---|
| **Describes** | `main` from the scheduler merge onward |
| **Derived from** | `src/core/include/meta_amiga/core/scheduler.hpp`, `src/core/scheduler.cpp`, `src/core/include/meta_amiga/core/types.hpp`, `src/core/chipset/slot_allocator.cpp`, `tests/unit/scheduler_test.cpp` |
| **Design** | [SPIKE-S0](../spikes/SPIKE-S0-core-timeline.md) §2–§4 · [ADR-CORE-01](../adr/ADR-CORE-01-cycle-accurate-timing-model.md) D1, D2, D6 |

SPIKE-S0 is the design, written before the code. This page draws what the code on `main`
does, so the two can be compared. Every box and arrow below is taken from the source;
where the spike and the code disagree, the diagram follows the code and the difference is
listed in [§4](#4-where-the-design-documents-and-the-code-differ).

---

## 1. Component view

Solid lines exist in the code today. Dashed boxes and lines are designed in SPIKE-S0 or
ADR-CORE-01 and not yet written.

```mermaid
flowchart LR
    driver["Driver<br/>today: tests/unit/scheduler_test.cpp<br/>later: the machine loop"]

    subgraph timeline["Colour-clock timeline · types.hpp"]
        cycle["Cycle = u64<br/>colour clocks since reset<br/>kNever = all ones = nothing pending"]
    end

    subgraph sched["Scheduler · scheduler.hpp / .cpp"]
        now["now_ : Cycle"]
        due["due_[14] : Cycle<br/>one pending event per Device"]
        slots["slots_[14] : handler + context"]
    end

    devices["Device handlers, none written yet<br/>Beam · Refresh · Disk · Audio0..3 · Sprites · Bitplanes<br/>Copper · Blitter · CiaA · CiaB · Cpu<br/>enum order = tie-break order"]

    subgraph chipset["Slot allocator · chipset/slot_allocator.hpp / .cpp"]
        alloc["SlotAllocator<br/>write* and set*Active mark dirty<br/>beginLine rebuilds if dirty or the line changed<br/>owner(cck) · table()"]
        tables["slot_tables.hpp<br/>generated from dma-slot-allocation.yaml"]
    end

    geom["BeamGeometry · timing.hpp<br/>ccksInLine · linesInFrame"]
    arb["Bus arbitration<br/>request_bus · SPIKE-S0 §4"]

    driver -- "bind · scheduleAt · scheduleIn · cancel" --> sched
    driver -- "runUntil(deadline)" --> sched
    sched -- "now() · dueAt · pending · nextDue" --> driver
    now -. "measured in" .-> cycle
    due -. "measured in" .-> cycle
    sched -- "Handler(context, now)" --> devices
    devices -- "scheduleAt · scheduleIn · cancel" --> sched
    tables --> alloc

    devices -. "Beam: beginLine at each line boundary" .-> alloc
    geom -. "LineContext.clocks" .-> alloc
    devices -. "register writes: write* · set*Active" .-> alloc
    devices -. "every bus cycle" .-> arb
    arb -. "owner(cck)" .-> alloc

    classDef planned stroke-dasharray: 5 5
    class devices,arb,geom planned
```

What the solid part says:

- **The scheduler owns the timeline.** `now_` is the only clock in the core (ADR-CORE-01
  D1). It moves only inside `runUntil`, and nothing else in the core keeps time.
- **One slot per device, not a queue.** `due_` and `slots_` are fixed arrays indexed by
  `Device`. A second `scheduleAt` for the same device replaces the first.
- **Two kinds of caller.** The driver binds handlers, seeds events and advances time with
  `runUntil`. A handler, once dispatched, may call `scheduleAt`, `scheduleIn` or `cancel`
  for itself or for another device. It runs inside the driver's `runUntil` call, at the
  cycle it was due.
- **Today the only driver is the unit test.** No device handler exists on `main`; the
  tests bind small tracing handlers in their place.

What the dashed part says:

- **The allocator is not wired to the scheduler.** It builds and is tested on its own,
  and `beginLine` is called only by its tests. The intended caller is the `Beam` device's
  handler at each line boundary (the `Beam` enumerator's own comment says so), fed the
  line length by `BeamGeometry::ccksInLine`.
- **Nothing consumes `owner(cck)` yet.** The bus arbitration protocol of SPIKE-S0 §4,
  through which every participant asks for a slot (ADR-CORE-01 D2), has no code.

---

## 2. One `runUntil`, with a tie

Two devices, Copper (ordinal 9) and Cpu (ordinal 13), are both due at cycle 40. The
Copper handler reschedules itself 8 cycles on; the Cpu handler does not. The trace was
checked by running exactly these calls against `scheduler.cpp`.

```mermaid
sequenceDiagram
    autonumber
    participant D as Driver
    participant S as Scheduler
    participant CO as Copper handler · ordinal 9
    participant CP as Cpu handler · ordinal 13

    Note over S: now = 0
    D->>S: scheduleAt(Cpu, 40)
    D->>S: scheduleAt(Copper, 40)
    Note over D,S: issued in reverse priority order, insertion order does not leak in

    D->>S: runUntil(40)
    Note over S: scan due_ in Device order with strict less-than, Copper and Cpu both at 40, Copper is met first and kept
    S->>S: now ← 40, due[Copper] ← kNever
    S->>CO: handler(context, 40)
    CO->>S: scheduleIn(Copper, 8) → due 48
    Note over S: next scan, Cpu at 40 ≤ deadline 40, due exactly at the deadline still runs in this call
    S->>S: now ← 40, due[Cpu] ← kNever
    S->>CP: handler(context, 40)
    Note over S: next scan, earliest is Copper at 48 > 40, stop
    S->>S: now ← 40 = deadline
    S-->>D: return

    D->>S: scheduleAt(Cpu, 40) — due at now()
    D->>S: runUntil(40)
    Note over S: deadline ≤ now, return at once, nothing dispatched, Cpu stays pending at 40
    S-->>D: return

    D->>S: runUntil(50)
    S->>S: now ← 40, due[Cpu] ← kNever
    S->>CP: handler(context, 40) — still observes its own cycle
    S->>S: now ← 48, due[Copper] ← kNever
    S->>CO: handler(context, 48)
    CO->>S: scheduleIn(Copper, 8) → due 56
    Note over S: earliest is 56 > 50, stop
    S->>S: now ← 50 = deadline
    S-->>D: return
```

The rules the trace shows, each pinned by a test in `tests/unit/scheduler_test.cpp`:

| Rule | Steps | Test |
|---|---|---|
| Earliest cycle first; on a tie the lower `Device` ordinal, whatever the call order | 1–8 | `tiesBreakByDeviceOrder`, `identicalSchedulesProduceIdenticalTraces` |
| `now()` jumps to each event's cycle, and the handler observes exactly that cycle | 4–5, 7–8, 15–18 | `dispatchesInCycleOrder` |
| A handler's slot is cleared before it is called, so it can reschedule itself | 4–6, 17–19 | `handlersMayRescheduleThemselves` |
| An event due exactly at `deadline` runs in the same call | 7–8 | `eventsBeyondTheDeadlineStayPending` |
| A deadline at or before `now()` dispatches nothing, not even an event due at `now()`; that event runs first on the next call with a later deadline | 11–16 | `aDeadlineAtNowDispatchesNothing` |
| On every call that advances, `now()` ends exactly on `deadline` | 9, 20 | `dispatchesInCycleOrder`, `handlersMayRescheduleThemselves` |

The boundary, stated once: the deadline is **inclusive** for events, and a call whose
deadline does not move time forward is a no-op. An event can only be left waiting at the
current cycle by being scheduled there *after* the call that reached it returned.

---

## 3. One device's event slot

The code stores a single `Cycle` per device, so it has two resting states, not four:
never scheduled, cancelled, dispatched and saturated are all `due = kNever` and are
indistinguishable afterwards.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Idle : Scheduler() fills due_ with kNever

    state "Idle · due = kNever · pending() false" as Idle
    state "Pending · due = t · pending() true" as Pending
    state "Dispatching · due already kNever, handler(context, t) running" as Dispatching

    Idle --> Pending : scheduleAt(t), t ≥ now · scheduleIn(d) without saturating
    Pending --> Pending : scheduleAt / scheduleIn again — replaces, never queues
    Pending --> Idle : cancel()
    Pending --> Idle : scheduleIn(d) with d > kNever − now saturates to kNever
    Idle --> Idle : cancel() · saturating scheduleIn(d)
    Idle --> Pending : scheduleAt(t), t < now — debug asserts, release clamps t to now + 1
    Pending --> Dispatching : runUntil(deadline) picks it — earliest due, t ≤ deadline, lowest Device ordinal on a tie · now ← t · due ← kNever
    Dispatching --> Idle : handler returns without rescheduling · unbound slot is a no-op
    Dispatching --> Pending : handler reschedules itself
```

- **Saturation.** `scheduleIn(d)` computes `now + d` only when it cannot pass `kNever`;
  otherwise it stores `kNever`, which is exactly what `cancel` stores. Without the check
  the sum would wrap into the past, and a release build would clamp it to `now + 1` and
  fire almost at once (`scheduleInSaturatesAtNever`).
- **A past schedule** is drawn from Idle, but the same clamp applies from Pending:
  `scheduleAt` never keeps the old value. Clamping to `now + 1` rather than `now` is what
  keeps `runUntil` advancing (`aPastScheduleAdvancesRatherThanHanging`, release builds
  only).
- **An unbound device** still goes through Dispatching; with no handler the dispatch is a
  no-op and the slot ends Idle (`unboundDevicesDispatchAsNoOps`).

---

## 4. Where the design documents and the code differ

The diagrams follow the code in each case.

1. **`now()` after a past deadline.** SPIKE-S0 §2.3 property 3 and §5 test 10 say `now`
   equals `deadline` on return "in every case". The code, and §5 test 9, return from a
   deadline at or before `now()` without moving `now`, so `now()` then exceeds
   `deadline`. Test 10 holds for every call that advances time.
2. **Slot table shape.** SPIKE-S0 §3.1 sketches `slot_owner[0..226]` holding a `Device` or
   `FREE`. The code's table has 228 entries, for the NTSC long line, and holds a
   `SlotOwner`: a separate enumeration with one owner per sprite and per bitplane and no
   Beam, Copper, Blitter, CIA or CPU entries. No mapping between `SlotOwner` and the
   scheduler's `Device` exists yet; arbitration will need one.
3. **What gates a fixed slot.** The §3.1 `rebuild` sketch places refresh, disk and audio
   unconditionally and gates sprites on `SPREN` and one vertical window. The code places
   only refresh when DMA master is off, needs both the enable and the device's active
   state for disk and each audio channel, and takes a per-sprite window mask from the
   caller.
4. **"The cycle it was scheduled for."** SPIKE-S0 §2.3 property 1 and the `Handler`
   comment say a handler observes the cycle it was scheduled for. That holds for the cycle
   *stored*; after a release-build past schedule the stored cycle is `now + 1`, not the
   one requested.
