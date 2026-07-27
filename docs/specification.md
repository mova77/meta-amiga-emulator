# meta-amiga — system specification

Version 0.1 (draft) · governs release line 26.x

This is the contract the implementation is written against. It states what the emulator
must reproduce and to what tolerance; the *how* lives in the ADRs under
[adr/](adr/). No implementation story starts before the subsystem it touches is specified
here and its architecture recorded as an ADR.

---

## 1. Goals and non-goals

### Goals

1. **Fidelity first.** The emulator reproduces the machine's timing, not merely its
   results. Every visible behaviour — display, audio, disk, interrupt latency — is a
   consequence of one shared cycle timeline, not of subsystem-local approximation.
2. **One codebase, three platforms.** macOS, Linux and Windows build from identical
   sources with no platform code in the emulation core.
3. **Measured compatibility.** ≥99 % of a published corpus of games, Workbench revisions
   and demoscene productions, verified automatically (§9).
4. **Deterministic.** Identical inputs produce a bit-identical run, on every platform, in
   every build configuration. Replay and state snapshots follow from this, and so does
   the ability to bisect a regression.

### Non-goals

- Being fast on hardware that cannot run a cycle-accurate model. The reference core
  targets a modern desktop CPU; low-power targets get the JIT tier or nothing.
- Emulating non-Amiga Motorola systems, however tempting the shared CPU core makes it.
- Shipping copyrighted ROMs or games under any circumstance.

---

## 2. Machine scope

| Model | Chipset | CPU | Chip RAM | Notes |
|-------|---------|-----|----------|-------|
| A1000 | OCS | 68000 | 256–512 K | Bootstrap ROM + Kickstart from disk (WCS) |
| A500 | OCS | 68000 | 512 K–1 M | Trapdoor slow RAM at `$C00000` |
| A500+ | ECS | 68000 | 1–2 M | |
| A600 | ECS | 68000 | 1–2 M | Gayle, PCMCIA, IDE |
| A1200 | AGA | 68EC020 | 2 M | Gayle, IDE |
| A2000 | OCS/ECS | 68000 | 512 K–1 M | Zorro II |
| A3000 | ECS | 68030 + 68882 | 1–2 M | Ramsey/Fat Gary, SCSI (WD33C93), Zorro III |
| A4000 | AGA | 68030/68040 | 2 M | IDE, Zorro III |
| CDTV | OCS | 68000 | 1 M | CD-ROM, DMAC, remote |
| CD32 | AGA | 68EC020 | 2 M | Akiko (chunky-to-planar, CD) |

Accelerated configurations (68030/040/060 + fast RAM in an A500/A1200) are configurations
of the above, not separate models.

### 2.1 Custom chips

- **Agnus** — 8371 (OCS), 8372A/B *Fat Agnus* (ECS, 1–2 M), 8374 *Alice* (AGA). Owns the
  DMA slot allocator, the Copper, the Blitter and the display beam counters.
- **Denise** — 8362 (OCS), 8373 *Super Denise* (ECS), 4203 *Lisa* (AGA). Bitplane
  serialisation, sprite priority and collision, colour lookup.
- **Paula** — 8364. Four audio channels, floppy MFM serialiser, serial port, interrupt
  controller.
- **CIA 8520** ×2 — A at `$BFE001` (odd bytes, keyboard, floppy select, parallel,
  overlay), B at `$BFD000` (even bytes, serial handshake, floppy control, TOD from
  hsync). Both with 24-bit TOD counters and shift registers.
- **Gary / Gayle / Fat Gary / Ramsey / Buster / Akiko / DMAC** per model.

### 2.2 CPU scope

68000, 68010, 68EC020, 68020, 68030, 68040, 68060; FPUs 68881, 68882 and the integrated
040/060 units; MMUs 68851/030/040/060. Full instruction set including the 020+ additions
(bitfields, `CAS`/`CAS2`, `CHK2`/`CMP2`, `DIVSL`/`DIVUL`, packed BCD FPU formats,
`MOVE16` on 040+), correct exception and stack-frame formats per model, and the 040/060
unimplemented-instruction traps that Kickstart's `68040.library` relies on.

---

## 3. The timing model

**Everything is scheduled on the colour clock.** This is the single most consequential
decision in the project and is recorded in
[ADR-CORE-01](adr/ADR-CORE-01-cycle-accurate-timing-model.md).

| Quantity | PAL | NTSC |
|----------|-----|------|
| Colour clock (CCK) | 3.546895 MHz | 3.579545 MHz |
| 68000 clock | 7.093790 MHz (2 × CCK) | 7.159090 MHz |
| CCKs per scanline | 227 | 227.5 (alternating 227/228) |
| Lines per frame | 312 (313 long) | 262 (263 long) |
| Frame rate | 50.080 Hz | 59.940 Hz |

A scanline is 227 colour clocks, each of which is one DMA slot. Slots are allocated in a
fixed priority order, and the CPU gets what is left:

```
slot  $00 $01 $02 $03 $04 $05 $06 $07 $08 $09 $0A $0B..$1A  $1C..
      ref dsk ref dsk ref dsk  —  au0 au1 au2 au3 sprite0-7  bitplanes
```

> **The slot indices above are indicative, not yet authoritative.** The exact allocation is
> transcribed from the *Amiga Hardware Reference Manual* DMA time-slot table and verified
> against hardware as an acceptance condition of
> [SPIKE-S0](spikes/SPIKE-S0-core-timeline.md) §3.2. Nothing may be implemented against
> this diagram until that item closes.

Refresh takes four slots, disk DMA three, audio four, sprites sixteen (two per sprite),
and bitplane DMA claims slots from `DDFSTRT` to `DDFSTOP` — 4 slots per line per bitplane
in lores, 8 in hires, 8 or 16 in AGA fetch modes. The Copper takes free even slots; the
Blitter takes free slots subject to `BLTPRI`; the CPU takes odd slots and whatever even
slots nothing else claimed. Enabling a seventh bitplane in hires starves the CPU almost
completely, and programs depend on exactly that.

**Requirement T-1.** Every chipset access, CPU bus cycle, Copper instruction, Blitter
word and audio sample fetch is scheduled against this slot table. No subsystem advances
on its own clock.

**Requirement T-2.** Register writes take effect at the beam position where the hardware
applies them, including the one-slot delays on `BPLCON0`, the mid-scanline `COLORxx`
change window, and `COPJMP` strobe timing. Copper-driven raster splits are the acceptance
test.

**Requirement T-3.** The Blitter is cycle-scheduled, not instantaneous. Blitter-CPU
contention, `BLTPRI`, and the `DMACONR` busy flag are observable and correct;
blitter-wait loops must take the number of cycles the hardware takes.

---

## 4. Display

- Lores 320, hires 640, AGA super-hires 1280 pixels; 1–6 bitplanes (OCS/ECS) or 1–8
  (AGA); EHB, HAM6, HAM8; dual playfield; 32 / 64 / 256 colour registers with AGA
  palette banking.
- Overscan to the full addressable beam area; programs set `DIWSTRT`/`DIWSTOP` and
  `DDFSTRT`/`DDFSTOP` outside the documented ranges routinely, and the display must
  follow rather than clamp.
- Sprites: 8 hardware sprites, attached pairs, per-line reuse, AGA 32/64-pixel widths,
  sprite/playfield priority via `BPLCON2`, and the `CLXDAT`/`CLXCON` collision registers.
- Interlace and the ECS/AGA productivity and super-hires modes; genlock/`BPLCON0` bits
  that affect colour 0.
- Copper list execution with correct `WAIT`/`SKIP` comparison semantics including the
  blitter-finished-disable bit and vertical-position wraparound past line 255.

**Requirement D-1.** Output is produced as a beam-accurate framebuffer: each pixel is
written when the beam reaches it, so mid-scanline register changes land at the right
pixel. Post-hoc scanline rendering is not acceptable.

**Requirement D-2.** Presentation is decoupled from emulation. The core emits full
overscan frames plus the per-line mode metadata a scaler needs; interpolation, scanline
and CRT filtering, and aspect correction are the frontend's problem.

---

## 5. Audio

Four Paula channels, 8-bit signed samples, DMA-fetched one word (two samples) at a time,
period-driven at up to ~28.8 kHz (PAL, period 124). Modulation of period and volume by
channels 0→1 and 2→3 (`ADKCON` `USEnnn` bits) must be supported; several trackers and
most modern demos rely on it, as do all 14-bit output tricks.

**Requirement A-1.** Sample output is generated from the DMA timeline at colour-clock
resolution and resampled to the host rate by a band-limited resampler. Naive
period-to-rate conversion aliases audibly on exactly the material this project exists to
run.

**Requirement A-2.** Audio DMA restart, `AUDxLEN`/`AUDxPT` reload timing, and the
one-word-lookahead behaviour must match hardware, because loop-point tricks depend on it.

---

## 6. Storage and media

### 6.1 Floppy

The drive is modelled at the **MFM bitstream** level, not the sector level: a rotating
track buffer of raw MFM cells, read and written through Paula's `DSKLEN`/`DSKDAT`
serialiser with `DSKSYNC` matching, correct index-pulse and step timing, and the
`DSKRDY`/`DSKCHANGE`/`TRACK0` lines on CIA B.

| Format | Read | Write | Notes |
|--------|------|-------|-------|
| ADF (880 K) | ✓ | ✓ | Sector image, synthesised to MFM on load |
| Extended ADF | ✓ | ✓ | Per-track raw MFM; carries most protections |
| ADZ / DMS | ✓ | — | Decompressed to ADF in memory |
| SCP (flux) | ✓ | — | SuperCard Pro flux, decoded to MFM cells |
| KryoFlux raw | ✓ | — | |
| IPF / CAPS | optional | — | Requires the non-free `capsimage` library; built only when present and never linked into a release binary (§10) |

Copy-protected originals are the hard case and the reason for the flux path: weak bits,
long tracks, non-standard sync words and deliberate MFM violations all survive at cell
level and none survive at sector level.

### 6.2 Hard disk and CD

HDF (raw and RDB), directory-mapped virtual volumes, IDE (Gayle, A4000), SCSI (A3000
WD33C93, Zorro controllers), CD-ROM for CDTV and CD32 (ISO/CUE/CHD).

**Requirement S-1.** The directory-mapped virtual filesystem needs an Amiga-side handler.
The project writes its own in 68k assembly and ships the source; no third-party handler
binary is embedded.

---

## 7. Kickstart ROMs

Every shipped revision from 1.2 (33.180) through 3.2, plus the A1000 bootstrap and the
CDTV/CD32 extended ROMs. Identification is by SHA-1 against a built-in database, so a
misnamed or byte-swapped dump is diagnosed rather than silently mis-run.

Amiga Forever encrypted ROMs are supported: files beginning with the 11-byte magic
`AMIROMTYPE1` are decrypted at load by XOR against the user's `rom.key`, cycled over the
ciphertext. The key is read from the user's own Amiga Forever installation and is never
copied into the project's configuration or state files.

AROS is bundled as a redistributable fallback so the emulator is useful with no ROM at
all. Detail in [ADR-ROM-03](adr/ADR-ROM-03-kickstart-rom-handling.md).

---

## 8. Portability

The emulation core is freestanding: no I/O, no threads, no allocation after
initialisation, no platform headers, no dependency beyond the C++23 standard library. It
communicates through explicit port interfaces (video sink, audio sink, input source,
storage, clock). Backends implement those ports. See
[ADR-PORT-04](adr/ADR-PORT-04-portability-and-backends.md).

**Requirement P-1.** `core` must compile and its full test suite pass with no backend
present, on all three platforms and on both x86-64 and AArch64.

**Requirement P-2.** No undefined behaviour. The project builds clean under
`-Wall -Wextra -Wpedantic -Werror`, ASan, UBSan and TSan, and those builds run in CI.

---

## 9. Compatibility measurement

The ≥99 % target is meaningless unless it is computed. `meta-amiga-verify` runs a corpus
in headless deterministic mode, drives each entry from a recorded input script, and hashes
the framebuffer and audio output at declared checkpoints against stored references.

- **Games** — boot-to-playable plus a scripted play segment; framebuffer hash at N
  checkpoints.
- **Workbench** — every ROM revision boots to a usable desktop; hash of the settled
  screen.
- **Demos** — full run, frame hash every N frames, audio hash per segment. A demo that
  desyncs by one frame fails.
- **Hardware unit tests** — original 68k test programs asserting documented and measured
  chipset behaviour, run as part of the ordinary suite.

The corpus manifest lists titles, hashes of the *images we expect* and reference output
hashes — never the images themselves. CI runs the subset that is legally redistributable
(AROS, demos with distribution permission, our own test programs); the full corpus runs
locally against media the developer owns. Method in
[ADR-TEST-05](adr/ADR-TEST-05-compatibility-measurement.md).

---

## 10. Licensing constraints on the implementation

- The project is GPL-3.0-or-later. Every source file carries an SPDX identifier.
- No code may be taken from another emulator ([PROVENANCE.md](../PROVENANCE.md)).
- No non-free dependency may be required to build or run. `capsimage` (IPF) is
  detected-and-optional, off by default, and absent from release binaries; flux formats
  cover the same ground with a free implementation.
- Bundled third-party code must be GPL-3-compatible, vendored with its licence, and
  listed in `docs/third-party.md`.

---

## 11. Roadmap

Phases are ordered by what unblocks measurement, not by what demos best.

| Phase | Delivers | Exit criterion |
|-------|----------|----------------|
| **0 · Foundation** | Repo, build, CI, scheduler spine, provenance gate | Core builds clean on 3 platforms; scheduler tests pass |
| **1 · CPU** | 68000/010 interpreter, exceptions, bus timing | Passes the 68k instruction and timing test suite |
| **2 · Chipset** | Agnus slots, Copper, Denise OCS display, CIA, interrupts | Kickstart 1.3 reaches the insert-disk screen |
| **3 · Storage** | MFM floppy, ADF, trackdisk | Workbench 1.3 boots from ADF |
| **4 · Blitter & audio** | Cycle-scheduled Blitter, Paula audio | First demos run with correct timing and sound |
| **5 · ECS/AGA** | ECS Agnus/Denise, AGA, 020+, A1200 | Workbench 3.1 boots; AGA demos run |
| **6 · Breadth** | HDD, IDE/SCSI, WHDLoad, flux images, CD32/CDTV | Corpus pass rate measurable end to end |
| **7 · Performance** | JIT tier, SIMD hot paths, threading | Full-speed AGA on a mid-range laptop |
| **8 · Product** | GUI, configuration, savestates, RTG, releases | `26.1.0` |

---

## 12. Open questions

Tracked as decisions to be made, not gaps to be discovered later.

1. JIT tier: LLVM ORC (portable, heavy) versus a hand-written dynarec (light, per-arch).
   Deferred to phase 7 with the interpreter as permanent oracle —
   [ADR-CPU-02](adr/ADR-CPU-02-68k-core-strategy.md) records why the decision can wait.
2. RTG requires an Amiga-side driver; writing a Picasso96-compatible one from scratch is a
   project in itself. Scope for phase 8 unresolved.
3. Threading model for the presentation and audio backends, once the core is proven
   deterministic single-threaded.
4. Whether savestates are a supported cross-version format or explicitly
   same-build-only.
