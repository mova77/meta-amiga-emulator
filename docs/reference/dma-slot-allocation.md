# DMA time-slot allocation, per horizontal line

| | |
|---|---|
| **Status** | Transcribed from published documentation · **not yet verified against hardware** |
| **Date** | 2026-09-23 |
| **Produced by** | The DMA slot-table spike, the paper half of its time-box |
| **Feeds** | [SPIKE-S0](../spikes/SPIKE-S0-core-timeline.md) §3.2 and §3.3 · specification §3 |
| **Machine-readable form** | [dma-slot-allocation.yaml](dma-slot-allocation.yaml) |

This is the transcription of record for who owns each colour clock of a scanline. Every
row cites the document and section it came from. Anything the sources do not settle is
marked **UNVERIFIED** and is not filled in from anywhere else — a guessed constant in
this table is the failure mode [ADR-CORE-01](../adr/ADR-CORE-01-cycle-accurate-timing-model.md)
says is a rewrite to recover from.

## Provenance

Derived **only** from Commodore's published *Amiga Hardware Reference Manual*, which
[PROVENANCE.md](../../PROVENANCE.md) lists as a permitted source. No emulator source,
and no third-party reproduction of an emulator's tables, was read, searched or consulted
in producing this document. Where a number here disagrees with what some other project
does, the manual is what this table records, and the disagreement is a measurement to
make — not an invitation to copy.

---

## 1. Sources consulted

| # | Source | Section | What it supplies |
|---|--------|---------|------------------|
| S1 | *Amiga Hardware Reference Manual*, 3rd ed. (AmigaGuide edition, ADCD 2.1) | Ch. 6 *Blitter Hardware* → **Blitter Operations and System DMA** | Priority order; per-line slot **counts**; the 68000-uses-even-cycles rule; the four-or-more-bitplanes statement |
| S2 | *ibid.* | **Figure 6-9: DMA Time Slot Allocation / Horizontal Line** | Slot **positions** for refresh, disk, audio, sprites; both bitplane fetch patterns; the $18 and $D8 hardware limits |
| S3 | *ibid.* | Ch. 3 *Playfield Hardware* → Forming a Basic Playfield → **Telling the System How to Fetch and Display Data** | Normal `DDFSTRT`/`DDFSTOP` values; the fetch-start programming resolution; the DDF↔DIW relation |
| S4 | *ibid.* | **Figure 6-10: Normal 68000 Cycle** | That the 68000's memory-access half-cycle is the even clock |

S2 is an image page. It was transcribed by measuring the figure itself rather than by
reading it off by eye: the drawing is on an exact 20-pixel grid, one cell per colour
clock, and the hex tick marks fall precisely on cell boundaries, so each drawn box maps
to one clock without interpretation. §6 records how that mapping was calibrated and why
it is believed.

---

## 2. The line as a whole

From **S1**, verbatim:

> During a horizontal scan line (about 63 microseconds), there are 227.5 "color clocks",
> or memory access cycles. A memory cycle is approximately 280 ns in duration. The total
> of 227.5 cycles per horizontal line includes both display time and non-display time.
> Of this total time, 226 cycles are available to be allocated to the various devices
> that need memory access.

and the counts, verbatim:

> ```
>       4 cycles for memory refresh
>       3 cycles for disk DMA
>       4 cycles for audio DMA (2 bytes per channel)
>      16 cycles for sprite DMA (2 words per channel)
>      80 cycles for bitplane DMA (even- or odd-numbered slots
>           according to the display size used)
> ```

The 80 is the **four-bitplane low-resolution** case: 4 planes × 20 words. It is not a
ceiling — §4 shows six planes taking 120 of the 160 clocks in the fetch window.

**Parity is the organising rule.** S1 states the 68000 uses only the even-numbered
memory access cycles, and S4 draws the even clock as the 68000's memory-access half.
Every fixed allocation in §3 lands on an **odd** clock, and so do all four low-resolution
bitplane slots of a four-plane display; planes 5 and 6 are what break the arrangement,
which is exactly what S1 says happens past four planes. High resolution breaks it sooner,
because its 4-clock group has only two odd slots to give.

---

## 3. Fixed allocations

Slot indices are colour clocks within the line, hex, as Figure 6-9 labels them.

| Device | Slots | Count | Source |
|--------|-------|-------|--------|
| Memory refresh | `$01`, `$03`, `$05`, **+ one further slot, index UNVERIFIED** | 4 | S2 · count from S1 |
| Disk DMA | `$07`, `$09`, `$0B` | 3 | S2 · count from S1 |
| Audio channel 0 | `$0D` | 1 | S2 |
| Audio channel 1 | `$0F` | 1 | S2 |
| Audio channel 2 | `$11` | 1 | S2 |
| Audio channel 3 | `$13` | 1 | S2 |
| Sprite 0 | `$15`, `$17` | 2 | S2 |
| Sprite 1 | `$19`, `$1B` | 2 | S2 |
| Sprite 2 | `$1D`, `$1F` | 2 | S2 |
| Sprite 3 | `$21`, `$23` | 2 | S2 |
| Sprite 4 | `$25`, `$27` | 2 | S2 |
| Sprite 5 | `$29`, `$2B` | 2 | S2 |
| Sprite 6 | `$2D`, `$2F` | 2 | S2 |
| Sprite 7 | `$31`, `$33` | 2 | S2 |

Every one of these is claimed **only when the device is active**. Figure 6-9's own
footnote: *"These operations only take slots if the associated operation is being
performed."* An unclaimed slot is FREE, which is what makes `slot_owner` a function of
`DMACON` and not of the line alone.

### 3.1 The fourth refresh slot — UNVERIFIED

Figure 6-9 draws four refresh cells at the same two-clock pitch as everything else, but
the leftmost one sits **one cell to the left of the `$00` tick**. The figure marks this
with a footnote of its own:

> *This cycle 0 appears to exclude one of the memory refresh cycles. This is not the
> case. Actual system hardware demands certain specific values for data fetch start and
> display start. Therefore this timing chart has been "adjusted" to match those
> requirements.*

So the manual admits the drawing is offset, and names the reason: the fetch-start and
display-start values had to come out right. It does **not** say what index that fourth
slot carries. Three readings are open — it is the last odd clock of the preceding line;
the whole refresh group is one clock later than drawn; or the line's clock numbering
begins before `$00`. Nothing in S1–S4 chooses between them.

This is recorded as an open measurement, not resolved. It is also the **only** absolute
index in §3 that the figure leaves ambiguous: the other thirteen are anchored by the
`$18` limit in §5, which is stated as a number rather than drawn.

---

## 4. Bitplane fetch patterns

Bitplane DMA claims slots inside the `DDFSTRT`..`DDFSTOP` window, in a group that
repeats for every word fetched. Offsets below are from the group's first clock, so the
table is independent of where `DDFSTRT` is put.

### 4.1 Low resolution — 8-clock group

Normal `DDFSTRT` is `$38` (S3), so the concrete column shows the first group of a
standard 320-pixel display.

| Offset | Clock at `DDFSTRT=$38` | Owner (6 planes) | Owner (≤4 planes) |
|--------|------------------------|------------------|-------------------|
| 0 | `$38` | free | free |
| 1 | `$39` | bitplane 4 | bitplane 4 |
| 2 | `$3A` | bitplane 6 | free |
| 3 | `$3B` | bitplane 2 | bitplane 2 |
| 4 | `$3C` | free | free |
| 5 | `$3D` | bitplane 3 | bitplane 3 |
| 6 | `$3E` | bitplane 5 | free |
| 7 | `$3F` | bitplane 1 | bitplane 1 |

Source: S2, the *320 mode Bit-Plane DMA, by plane* stratum, which the figure draws for
the six-plane maximum. The ≤4-plane column follows from the footnote quoted in §3 —
a plane that is not enabled does not take its slot — and it is what makes S1's two
statements come out right:

- **Four planes take 80 cycles.** Offsets 1, 3, 5, 7 are used, 20 times → 80. ✓
- **Four or fewer planes leave the 68000 alone; more than four steal from it.** Offsets
  1, 3, 5, 7 are the odd clocks; offsets 0, 2, 4, 6 the even ones. Planes 5 and 6 are
  the first to land on even clocks, taking two of the four the 68000 had — *"bitplane
  DMA steals 50 percent of the open slots"* (S1). ✓

That both independent statements fall out of the transcribed pattern is the strongest
evidence the pattern was read off correctly.

### 4.2 High resolution — 4-clock group

Normal `DDFSTRT` is `$3C` (S3).

| Offset | Clock at `DDFSTRT=$3C` | Owner (4 planes) |
|--------|------------------------|------------------|
| 0 | `$3C` | bitplane 4 |
| 1 | `$3D` | bitplane 2 |
| 2 | `$3E` | bitplane 3 |
| 3 | `$3F` | bitplane 1 |

Source: S2, the *640 mode Bit-Plane DMA, by plane* stratum. Nothing is free: four planes
in four clocks is the whole group, which is why a full-width four-plane hires display
locks the 68000 out of the fetch window entirely rather than merely halving it.

The plane **order** differs from lores — `4,2,3,1` against `4,6,2 / 3,5,1` — and is not
a re-ordering of the same sequence. It is transcribed as drawn.

### 4.3 Fetch window

| Quantity | Low resolution | High resolution | Source |
|----------|----------------|-----------------|--------|
| Normal `DDFSTRT` | `$38` | `$3C` | S3 |
| Normal `DDFSTOP` | `$D0` | `$D4` | S3 |
| Programming resolution of fetch start | 8 clocks | 4 clocks | S3 |
| Words fetched, normal width | 20 | 40 | S3 |
| `DDFSTRT` = `DDFSTOP` − … | `8 × (words − 1)` | `4 × (words − 2)` | S3 |

Both relations check against the normal values: `$D0 − 8×19 = $38` and
`$D4 − 4×38 = $3C`. S3 also fixes the fetch-start-to-window-start offset at 8.5 clocks
(lores) and 4.5 clocks (hires) below `DIWSTRT`/2, giving the same `$38` and `$3C` from a
`DIWSTRT` hstart of `$81`.

### 4.4 AGA fetch modes — UNVERIFIED, no permitted source held

`FMODE`, the 32- and 64-bit fetch modes, and their 8- and 16-slot groups postdate the
*Hardware Reference Manual* 3rd edition. Appendix C of that manual covers ECS only, and
nothing in S1–S4 describes them. **No AGA fetch-mode table is transcribed here.** Filling
one in would require a named Commodore AGA document; until one is in hand, SPIKE-S0 §3.3's
AGA clause is unmet and the slot allocator must be written for OCS/ECS only. This is a scope finding,
not a transcription failure.

---

## 5. Limits the hardware imposes

| Limit | Value | Source | Consequence |
|-------|-------|--------|-------------|
| Earliest bitplane fetch | `$18` | S2 | Data fetch cannot begin sooner. Sprite 0 (`$15`, `$17`) survives; sprites 1–7 (`$19`…`$33`) are taken by bitplane DMA if the display starts this early. Audio (`≤$13`) and disk (`≤$0B`) are untouched. |
| Hardware data-fetch stop | `$D8` | S2 | Installed *"so as to prevent the bit-plane data fetch from overrunning the time allotted for the memory refresh or disk DMA."* |
| Display latency after fetch | 5 clocks | S2 | *"if data fetch start is $38, data will not be available for display until clock number $45 … because display processing does not begin until all of the bit-planes for a particular pixel have been fetched."* |

The `$18` limit is doing real work in this document: it is the manual stating, in a
number rather than a drawing, that sprite 0 is the last device before the earliest
possible fetch. The transcribed sprite indices put sprite 0 at `$15`/`$17` and sprite 1
at `$19`/`$1B`, which is the only assignment consistent with *"wipe out most of the
sprites … but leaves the audio and disk DMA untouched"*.

### 5.1 `DDFSTRT`/`DDFSTOP` outside documented ranges — UNVERIFIED

Specification §4 requires the display to **follow** out-of-range data-fetch settings
rather than clamp them, because software sets them routinely. The manual gives two hard
points — nothing before `$18`, a stop at `$D8` — and nothing at all about what happens
between and beyond: whether `DDFSTOP` below `DDFSTRT` fetches nothing or wraps, what an
odd `DDFSTRT` does when the programming resolution says it should be a multiple of 8,
or how a `DDFSTOP` past `$D8` interacts with the hardware stop. **These are measurements,
not transcriptions**, and they are the substance of SPIKE-S0 §3.3's second checkbox.

---

## 6. How Figure 6-9 was read, and why the reading is trusted

The figure is a 2400 × 400 image. It was measured, not eyeballed.

1. **Grid.** Drawn cells are 20 px wide on a 20 px pitch across the whole figure, and the
   figure's own *280 ns* annotation brackets exactly one cell. One cell is one colour
   clock.
2. **Ticks.** Every hex tick (`$0`, `$8`, `$10`, `$18`, `$20`, `$28`, `$30`, `$38`, `$40`,
   `$48`, `$50`, `$58`, `$D0`, `$D8`, `$E0`) sits exactly on a cell boundary, at
   `x = 39 + 20N` for clock `N`, with no residual across fifteen ticks. The axis is
   linear apart from one elision between `$58` and `$D0`, which the figure marks with
   *"Normal Res. CYCLES 5–19 same as cycle 4"* and *"High Res. CYCLES 8–37 same as
   cycle 7"*.
3. **Which cell a tick names.** The cell to the *right* of tick `N` is clock `N`. Three
   independent checks agree:
   - the lores group whose completion arrow reads *"Data fetch completed for cycle $38"*
     spans exactly the eight cells from the `$38` tick to the `$40` tick;
   - the hires plane pattern's labelled run begins at the `$3C` tick, which S3 gives
     independently as the normal high-resolution `DDFSTRT`;
   - under this reading, and only under it, every fixed allocation and the four-plane
     lores fetch land on odd clocks, which is S1's and S4's 68000 rule.
4. **Strata.** Boxes were classified by fill: diagonal hatch = refresh, horizontal rule =
   disk, vertical rule = audio, dot-fill = sprite, dot-fill upper stratum = 320-mode
   bitplane, solid black = 640-mode bitplane, empty = *"Slots available for Blitter,
   Copper and 68000"*. The legend is the figure's own.

The residual uncertainty is the one the figure itself declares: §3.1's fourth refresh
slot.

---

## 7. Predicted CPU bus cycles per line — the target for test 14

SPIKE-S0 test 14 compares CPU slots available per line, as measured on hardware, against
what the transcribed table predicts. The measurement has not run; this is the predicted
column, published ahead of it so the measurement has something to disagree with.

PAL, 227 colour clocks, clocks `$00`–`$E2`: **114 even, 113 odd**. Normal-width display,
`DDFSTRT` `$38` / `$3C`, 20 words lores and 40 hires.

The two parities are counted separately and deliberately not added together. Even clocks
are the 68000's own memory-access half and nothing but bitplane DMA takes them. Free odd
clocks are contended between CPU, Blitter and Copper, and who wins is bus arbitration —
SPIKE-S0 §4 and the bus-arbitration work, not this table.

**Even clocks, the 68000's half**

| Display | Bitplane even slots taken | Even clocks left to the 68000 | Measured |
|---|---|---|---|
| Blanking / bitplane DMA off | 0 | 114 | — |
| Lores, 1–4 planes | 0 | 114 | — |
| Lores, 5 planes | 20 (plane 5, offset 6) | 94 | — |
| Lores, 6 planes | 40 (planes 5 and 6, offsets 6 and 2) | 74 | — |
| Hires, 1–2 planes | 0 | 114 | — |
| Hires, 3 planes | 40 (plane 3, offset 2) | 74 | — |
| Hires, 4 planes | 80 (planes 3 and 4, offsets 2 and 0) | 34 | — |

This row set *is* the manual's four-or-fewer-bitplanes claim in numbers: up to four lores
planes cost the 68000 nothing, the fifth costs it 20 cycles a line and the sixth another
20 — half of the 40 it had inside the fetch window.

**Odd clocks, contended**

Fixed allocations account for 27 odd clocks when every channel is enabled: 4 refresh,
3 disk, 4 audio, 16 sprite. Bitplane DMA takes `min(planes, 4) × 20` more in lores and
`min(planes, 2) × 40` in hires.

| Display, all DMA enabled | Odd clocks free | Measured |
|---|---|---|
| Bitplane DMA off | 86 | — |
| Lores, 2 planes | 46 | — |
| Lores, 4–6 planes | 6 | — |
| Hires, 1 plane | 46 | — |
| Hires, 2–4 planes | 6 | — |

**Carry a ±1 on every figure in this section.** The fourth refresh slot's index is
undetermined (§3.1), so whether it falls inside the line is not known. A measurement that
comes out one clock off is evidence about *that* slot, not a refutation of the table.

Each row is also a DMA-enable combination the measurement program must set up: `DMACON`
with disk, audio, sprite and bitplane DMA independently off and on, at each plane count,
in both resolutions. The program itself is out of this document's scope — SPIKE-S2 §3.1
requires its timing loops to be hand-written 68000 assembly, and it belongs under
`tests/hardware/`.

---

## 8. Verification state

The spike's standard is two independent public statements per table, or an explicit
single-source mark.

| Table | Independent statements | State |
|-------|------------------------|-------|
| Per-line slot **counts** (§2) | S1 text; S2 figure | **Two** |
| Disk, audio, sprite **indices** (§3) | S2 figure; S2's `$18` limit, which only fits this assignment | **Two** (the second is a consistency argument, not a restatement) |
| Refresh indices (§3) | S2 figure only, and the figure disclaims its own offset | **Single-source, partly UNVERIFIED** |
| Lores fetch pattern (§4.1) | S2 figure; S1's 80-cycle and 50-percent statements, both of which it reproduces | **Two** |
| Hires fetch pattern (§4.2) | S2 figure only | **Single-source** |
| `DDFSTRT`/`DDFSTOP` normals (§4.3) | S3 text; S2 figure ticks | **Two** |
| `$18` / `$D8` limits (§5) | S2 figure only | **Single-source** |
| AGA fetch modes | none | **Not transcribed** |
| Out-of-range DDF behaviour | none | **Not transcribed** |

**Nothing here has been verified against hardware.** Every row is paper. The spike's
hardware half — an original measurement program on a PAL A500 counting CPU bus cycles
per line under each DMA enable combination — has not run, so there is no measured column
beside the predicted one.

---

## 9. Divergences found

Recorded as findings, not silently resolved.

1. **227.5 versus 227.** S1 says 227.5 colour clocks per line; specification §3 says 227
   for PAL and 227.5 (alternating 227/228) for NTSC. These do not conflict — the manual
   is NTSC throughout — but the manual never states the PAL figure, so specification §3's
   227 has no support in S1–S4 and rests on its own citation.
2. **"226 cycles are available."** S1 gives 227.5 total and 226 allocatable without
   saying where the other 1.5 go. Unexplained by any source held. UNVERIFIED.
3. **"160 time slots will be taken by bitplane DMA"** for a six-plane lores display (S1).
   The transcribed pattern gives 120 slots taken (6 planes × 20 words) inside a
   160-clock window. 160 is the span, not the count; the sentence reads as though it were
   the count. The 50-percent claim in the same paragraph matches the transcription
   exactly, so the pattern is taken as correct and the 160 as loose wording.
4. **"Data fetch start can only be specified at even multiples of 8 clocks"** (S2) against
   S3's *"a programming resolution of 16 pixels (8 clocks in low resolution mode, 4 clocks
   in high resolution mode)"*. `$38` = 56 = 7 × 8, an **odd** multiple of 8, so S2's
   wording is wrong on its own example. S3 is taken as authoritative: the resolution is
   8 clocks lores, 4 clocks hires.
5. **"20 word fetch for 420 pixel"** (S2, callout). 20 words is 320 pixels, and S3 uses
   320 throughout. Read as a typo for 320 in the figure.
6. **Display start, `$45` versus `$40.5`.** S2 says data is not available until `$45`
   when fetch starts at `$38`; S3 puts the display window start at `DIWSTRT`/2 = `$81`/2
   = `$40.5` clocks. The two are describing different events — data availability against
   window opening — but the manual never reconciles them, and a beam-accurate renderer
   (specification D-1) needs to know which governs the first displayed pixel. Open.
7. **Copper slot cost.** Figure 6-9's footnote states *"Copper Data Move instruction
   require 4 slots. Copper Data Wait instruction require 6 slots."* This is arbitration,
   SPIKE-S0 §4 and the bus-arbitration work, not slot allocation — recorded here so it is not lost, and
   flagged because it disagrees with the more commonly quoted two-slot MOVE. Do not
   implement from this line without its own verification.

---

## 10. Can the slot allocator start?

**Partly.** Not *yes*.

- **Startable now.** The allocator's fixed-allocation table for disk, audio and sprites,
  and the lores and hires bitplane fetch patterns, are transcribed from published
  documentation with the calibration in §6 and the cross-checks in §7. An OCS/ECS
  allocator can be built against them.
- **Not startable.** AGA fetch modes (§4.4) have no source. Out-of-range `DDFSTRT`/
  `DDFSTOP` behaviour (§5.1) has no source. The fourth refresh slot (§3.1) has no
  determined index.
- **Residual risk.** Everything above is paper. The named machine to verify it against
  is a **PAL A500, OCS, 512 KB chip RAM**, running an original measurement program that
  counts CPU bus cycles per line under each DMA enable combination — SPIKE-S0 test 14.
  Until that runs, any test asserting these indices asserts the manual, not the hardware,
  and must say so in its name or comment.

Six subsystems must not be built on an unverified table. One allocator, written to be
driven by this data and tested against it as *transcribed* rather than *measured*, may be.

### 9.1 Deliverables the spike asked for that are not here

- **`src/core/chipset/slot_tables.hpp`.** The story asks for a table file the build
  consumes. The data is here in machine-readable form; turning it into a header is a
  change to the core library, which this piece of work does not touch. The slot allocator generates
  or writes it from [dma-slot-allocation.yaml](dma-slot-allocation.yaml) so there is still
  one source of these numbers.
- **Measurement programs under `tests/hardware/`.** Not written. They are the hardware
  half of the spike, they need the machine to be worth anything, and SPIKE-S2 §3.1
  requires their timing loops to be hand-written 68000 assembly. §7 gives them their
  target table so they have something to fill in.
- **A measured column anywhere.** There is no machine. Every number in this document is
  paper, and the three-way split in §9 says which parts would survive a surprise and
  which would not.
