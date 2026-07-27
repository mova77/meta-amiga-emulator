# meta-amiga

A portable, cycle-accurate Commodore Amiga emulator for macOS, Linux and Windows.

Written from scratch in C++23 under the GNU General Public License v3 (or later). The
goal is a single codebase that runs **games, Workbench and demoscene productions** with
equal fidelity — the three workloads that stress completely different parts of the
machine, and the reason most emulators are good at one and merely adequate at the others.

> **Status: pre-alpha.** The specification and architecture are being written before the
> implementation. Nothing here boots yet. See [docs/specification.md](docs/specification.md)
> for what is being built and [docs/adr/](docs/adr/) for why it is being built that way.

## What "compatible" means here

Compatibility claims in this space are usually unfalsifiable. Ours is defined as a
measurement against a fixed, published corpus — see
[ADR-TEST-05](docs/adr/ADR-TEST-05-compatibility-measurement.md):

| Workload | Corpus | Target |
|----------|--------|--------|
| Games | Floppy originals and WHDLoad installs across OCS/ECS/AGA | ≥99 % run-to-playable |
| Workbench | Kickstart 1.2 → 3.2, booted to a usable desktop | 100 % of shipped ROM revisions |
| Demoscene | Ranked productions, verified by framebuffer and audio hashing | ≥99 % frame-exact |

Every number is produced by `meta-amiga-verify` against reference traces, and regressions
fail CI. A claim without a passing corpus run is not a claim.

## Hardware scope

- **Models** — A1000, A500, A500+, A600, A1200, A2000, A3000, A4000, CDTV, CD32
- **Chipsets** — OCS · ECS · AGA, modelled at the DMA-slot level on a single colour-clock
  timeline (Agnus/Alice, Denise/Lisa, Paula, CIA 8520 ×2, Gary/Gayle/Ramsey)
- **CPUs** — 68000, 68010, 68EC020, 68020, 68030, 68040, 68060, with 68881/68882 and
  integrated FPUs, MMU where the model has one
- **Media** — ADF, ADZ, DMS, HDF, LHA/WHDLoad, and flux-level images (SCP, raw KryoFlux)
  for copy-protected originals
- **Kickstart** — every shipped revision from 1.2 (33.180) to 3.2, plus AROS as a
  redistributable fallback

## ROMs

**No Kickstart ROM is included, and none ever will be** — they are copyrighted by Cloanto /
Amiga Corporation. meta-amiga loads ROMs you already own, including the encrypted files
and `rom.key` from a licensed **Amiga Forever** installation, which it decrypts in place
at load time. It ships with AROS so it is useful out of the box without one. See
[ADR-ROM-03](docs/adr/ADR-ROM-03-kickstart-rom-handling.md).

## Provenance

meta-amiga is a **clean-room implementation**. It contains no code from UAE, WinUAE,
FS-UAE, vAmiga or any other emulator, and is not a fork of one. Hardware behaviour is
derived from published documentation, hardware measurement and original testing. See
[PROVENANCE.md](PROVENANCE.md) — this is a hard contribution gate, not a preference.

## Build

There is nothing to build yet. The build system lands with the foundation work, and will
require CMake ≥ 3.28, Ninja, and a C++23 compiler (Clang ≥ 17, GCC ≥ 13, MSVC ≥ 19.38).

## Versioning

`<yy>.<rel>.<fix>` — two-digit year, release ordinal within that year, fix ordinal.
`26.1.0` is the first release of 2026; `26.1.3` its third fix. The year component is the
release year, not a support window.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
