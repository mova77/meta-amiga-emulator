# meta-amiga

[![CI](https://github.com/mova77/meta-amiga-emulator/actions/workflows/ci.yml/badge.svg)](https://github.com/mova77/meta-amiga-emulator/actions/workflows/ci.yml)
[![Licence: GPL-3.0-or-later](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue.svg)](LICENSE)
[![C++23](https://img.shields.io/badge/C%2B%2B-23-00599C.svg)](CMakeLists.txt)
[![Clean room](https://img.shields.io/badge/provenance-clean--room-brightgreen.svg)](PROVENANCE.md)

[![macOS](https://img.shields.io/badge/macOS-AArch64-black.svg)](#build)
[![Linux](https://img.shields.io/badge/Linux-x86--64%20%7C%20AArch64-FCC624.svg)](#build)
[![Windows](https://img.shields.io/badge/Windows-x86--64-0078D6.svg)](#build)

A portable, cycle-accurate Commodore Amiga emulator for macOS, Linux and Windows.

Written from scratch in C++23 under the GNU General Public License v3 (or later). The
goal is a single codebase that runs **games, Workbench and demoscene productions** with
equal fidelity — the three workloads that stress completely different parts of the
machine, and the reason most emulators are good at one and merely adequate at the others.

> **Status: pre-alpha — there is no emulator yet.** The specification and architecture are
> written before the implementation, deliberately. What exists today is the design, the
> build and the CI that will hold it to account: nine legs across three platforms and two
> architectures, under warnings-as-errors, ASan/UBSan and TSan.
>
> Start with [docs/specification.md](docs/specification.md) for what is being built,
> [docs/adr/](docs/adr/) for why it is built that way, and [docs/spikes/](docs/spikes/) for
> how the hard parts work.

The platform badges above state what CI actually builds and tests on every push, not an
aspiration. The single CI badge is the live one — GitHub publishes workflow status, not
per-job status, so the platform badges are declarative and the CI badge is the truth.

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

Requires CMake ≥ 3.28, Ninja, and a C++23 compiler — Clang ≥ 17, AppleClang ≥ 15,
GCC ≥ 13, or MSVC ≥ 19.38. The build refuses to configure below those floors rather than
failing later with template errors.

```bash
cmake --preset dev && cmake --build --preset dev && ctest --preset dev
```

Presets: `dev`, `debug`, `asan` (Address + UndefinedBehavior), `tsan`, `release`.

This builds the core library and its tests. **It does not build an emulator** — there is
nothing to run yet. See [the roadmap](docs/specification.md) for what arrives when.

## Versioning

`<yy>.<rel>.<fix>` — two-digit year, release ordinal within that year, fix ordinal.
`26.1.0` is the first release of 2026; `26.1.3` its third fix. The year component is the
release year, not a support window.

## Licence

GPL-3.0-or-later. See [LICENSE](LICENSE).
