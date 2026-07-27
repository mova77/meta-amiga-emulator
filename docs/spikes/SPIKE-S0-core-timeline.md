# SPIKE-S0 — The core timeline: event scheduler and DMA slot allocator

| | |
|---|---|
| **Status** | Draft — under review, gates the phase-0 foundation story |
| **Date** | 2026-07-27 |
| **Implements** | [ADR-CORE-01](../adr/ADR-CORE-01-cycle-accurate-timing-model.md) · specification §3 |
| **Governs** | `core/scheduler`, `core/chipset/agnus` slot allocation, the bus arbitration protocol |

The buildable design for the two components everything else in the emulator sits on. No
implementation story for either may start until this spike is accepted, and no other
subsystem may start until they exist — this is the SPARC gate applied where it matters
most, because a timing model that is wrong in its foundations cannot be corrected later
without rewriting every subsystem built on it.

---

## 1. Problem

Specification requirement T-1 says every chipset access, CPU bus cycle, Copper
instruction, Blitter word and audio fetch is scheduled against one colour-clock timeline.
That needs two mechanisms:

- **A scheduler** — what happens next, and in what order when two things happen at once.
- **A slot allocator** — who gets the memory bus on a given colour clock.

They are separate concerns and are designed separately. The scheduler knows nothing about
the Amiga; the allocator knows nothing about time beyond the current beam position.

---

## 2. Scheduler

### 2.1 Shape

The naive choice is a priority queue of `(cycle, callback)`. It is the wrong shape here.
Every device on this machine is always waiting for exactly one next thing — the Copper for
its next instruction, a Paula channel for its next sample fetch, a CIA for its next timer
underflow. A device never has two futures.

So: a **fixed-size table with one entry per device**, indexed by an enumeration. No
allocation, no insertion-order sensitivity, and a linear scan over fourteen entries that
outperforms a heap at this size and has no data-dependent branching to speak of.

```
DEVICES = [ Beam, Refresh, Disk, Audio0..3, Sprites, Bitplanes,
            Copper, Blitter, CiaA, CiaB, Cpu ]        # order is significant

state:
    now : Cycle                       # colour clocks since reset
    due[d] : Cycle for each device    # NEVER when nothing is pending
    handler[d], context[d]
```

### 2.2 Tie-break is the whole determinism argument

`DEVICES` is declared in DMA priority order — refresh and disk before audio, audio before
sprites, sprites before bitplanes, Copper and Blitter over what remains, CPU last. When
two devices are due on the same colour clock, **the lower ordinal runs first**.

That single rule is what makes a run reproducible (ADR-CORE-01 D6), and it is why
reordering the enumeration is a specification-level change rather than a tidy-up. It must
be asserted by a test that schedules devices in reverse priority order and checks they
dispatch in priority order — proving insertion history does not leak into the outcome.

### 2.3 Dispatch

```
procedure run_until(deadline):
    if deadline <= now: return                  # never run backwards

    loop:
        next, earliest ← NONE, NEVER
        for d in DEVICES:                       # declaration order ⇒ ties break correctly
            if due[d] < earliest:
                earliest, next ← due[d], d

        if next is NONE or earliest > deadline:
            break

        now ← earliest
        due[next] ← NEVER                       # clear BEFORE dispatch
        if handler[next]: handler[next](context[next], now)

    now ← deadline
```

Three properties this encodes, each with a test:

1. **A handler observes `now` equal to the cycle it was scheduled for** — never later.
   Late dispatch would silently smear timing.
2. **Clearing before dispatch** is what lets a periodic device reschedule itself from
   inside its own handler. That is the normal way every device works.
3. **`now` lands exactly on `deadline`** on return, whether or not anything was
   dispatched. The caller drives the machine in fixed slices and must not have to correct
   for drift.

### 2.4 Known hazard

An event scheduled at the *current* cycle is dispatched before time advances. That models
genuine same-cycle chaining, and it does not terminate if a handler does it
unconditionally. Deliberately not defended against in the scheduler: a cycle budget per
`run_until` would cost a branch on the hottest loop in the program to protect against a
bug that a test catches. Handlers that can chain get a test that proves they terminate.

Scheduling in the **past** is different — it is always a bug. Assert in debug; in release,
clamp to `now` so the failure surfaces as a visible timing artefact rather than a hang.

---

## 3. Slot allocator

### 3.1 Shape

Per scanline there are 227 colour clocks (PAL), each one a slot. Ownership is a pure
function of chipset register state and beam position — so it is computed **once per line**
into a table and invalidated when a register that feeds it is written.

```
state:
    slot_owner[0..226] : Device or FREE
    dirty : bool

inputs:  DMACON (master + per-channel enables)
         DDFSTRT, DDFSTOP          # bitplane fetch window
         BPLCON0                   # bitplane count, hires, AGA fetch mode
         SPRxPOS / sprite enables
         AUDxPER, audio channel states
         disk DMA state
```

```
procedure rebuild(line):
    fill slot_owner with FREE
    place fixed allocations: refresh, disk, audio           # §3.2
    if DMACON.SPREN and line in vertical sprite window:
        place sprite fetch slots
    if DMACON.BPLEN and line in display window:
        place bitplane slots from DDFSTRT to DDFSTOP        # §3.3
    dirty ← false
```

Cost is amortised across 227 slots and rebuilds are rare — the registers that feed it
change a few times per line at most, even under an aggressive Copper list. Register writes
mark `dirty` rather than rebuilding, so a Copper burst of eight writes costs one rebuild.

### 3.2 Fixed allocations — TO BE TRANSCRIBED

Memory refresh, disk DMA and the four audio channels occupy fixed slots at the start of
every line, followed by sixteen sprite slots. The structure is settled; **the exact slot
numbers are not yet transcribed into this document and must not be guessed.**

Work item, and it gates this spike's acceptance:

- [ ] Transcribe the DMA time-slot allocation table verbatim from the *Amiga Hardware
      Reference Manual* (3rd ed., ch. 6) — refresh, disk, audio, sprite slot indices.
- [ ] Verify the transcription against hardware with an original test program that
      measures CPU cycles available per line under each DMA enable combination.
- [ ] Record any divergence between the manual and the hardware here, with the measurement.

The indicative layout in specification §3 is exactly that — indicative — until this item
closes. Nothing may be built on it before then.

### 3.3 Bitplane fetch patterns — TO BE TRANSCRIBED

Bitplane DMA claims slots inside the `DDFSTRT`..`DDFSTOP` window in a repeating pattern
whose shape depends on fetch mode and bitplane count: a 4-slot group in lores, 8 in hires,
and 8 or 16 under AGA's wider fetch modes. Which slot within the group belongs to which
bitplane is a published table.

- [ ] Transcribe the per-fetch-mode, per-bitplane-count slot pattern.
- [ ] Verify against hardware, including the behaviour when `DDFSTRT`/`DDFSTOP` are set
      outside their documented ranges — which software does routinely and which the
      display must follow rather than clamp (specification §4).

The allocator is written to be **driven by** these tables, so transcribing them is data
entry against a stable interface rather than a redesign. That is the point of separating
§3.1 from §3.2–3.3.

### 3.4 Priority

The allocator answers ownership; it does not arbitrate. `BLTPRI` and the CPU's
lowest-priority position are properties of how the *bus protocol* consumes the table, §4.

---

## 4. Bus arbitration protocol

```
procedure request_bus(device, cycle) -> granted : bool
    owner ← slot_owner[cycle mod line_length]
    if owner == device:            return true
    if owner == FREE:
        return no higher-priority device is contending this slot
    return false
```

- **CPU.** Requests a slot; if refused, stalls and retries on the next slot. Instruction
  timing therefore *emerges* from display mode rather than being looked up (ADR-CPU-02
  D4). A seven-bitplane hires display starving the CPU is not a special case in the code —
  it is what the table says.
- **Blitter.** Takes FREE slots. With `BLTPRI` set it takes them ahead of the CPU; without
  it, it yields after a bounded run so the CPU is not locked out.
- **Copper.** Takes free even slots and stalls on `WAIT` until its beam comparison passes.

### 4.1 Open

The 68030/040/060-with-fast-RAM case is genuinely asynchronous to the chipset. This spike
does not resolve it; it is the open decision on ADR-CORE-01. The protocol above is written
so that a CPU running off the chipset timeline is a different `request_bus` implementation,
not a change to the allocator.

---

## 5. Test plan (SPARC · Refinement)

Written before the implementation, and the acceptance criteria for the foundation story.

**Scheduler**

| # | Assertion |
|---|-----------|
| 1 | Events dispatch in cycle order |
| 2 | Ties break by device order, independent of scheduling order |
| 3 | A handler observes `now` == its scheduled cycle |
| 4 | A handler may reschedule itself; a periodic device runs at its period |
| 5 | Events beyond the deadline stay pending and are not dispatched |
| 6 | Scheduling twice replaces rather than queues |
| 7 | Cancel withdraws a pending event |
| 8 | An unbound device consumes its event as a no-op |
| 9 | `run_until` with a past deadline is a no-op and does not move `now` |
| 10 | `now` == `deadline` on return, in every case |
| 11 | Two identical schedule sequences produce identical dispatch traces |

**Slot allocator** — blocked on §3.2/§3.3, listed so the gate is visible

| # | Assertion |
|---|-----------|
| 12 | Fixed allocations match the transcribed table for every DMA enable combination |
| 13 | Bitplane slots match the transcribed pattern per fetch mode and plane count |
| 14 | CPU slots available per line match hardware measurement, per display mode |
| 15 | A register write marks dirty; N writes before the next line cost one rebuild |
| 16 | `DDFSTRT`/`DDFSTOP` outside documented ranges follow hardware, not a clamp |

**Bus protocol**

| # | Assertion |
|---|-----------|
| 17 | A refused CPU request stalls and retries on the next slot |
| 18 | `BLTPRI` set: Blitter precedes CPU on a contended free slot |
| 19 | `BLTPRI` clear: the Blitter yields within its bounded run |
| 20 | Copper `WAIT` releases at exactly the beam position it compares against |

---

## 6. Acceptance

This spike is accepted when §3.2 and §3.3 are transcribed and verified, and tests 1–11
exist and pass. Tests 12–20 become the acceptance criteria of the slot-allocator and
bus-protocol stories that follow it.

A reference implementation of §2 exists on the parked branch `spike/core-timeline` and is
**not merged**: it was written before this spike, which is the breach that produced this
document. It stands as the shape under review, not as accepted code.
