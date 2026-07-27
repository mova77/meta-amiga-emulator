# Provenance and clean-room policy

meta-amiga is an original implementation. It is **not** a fork, port, translation or
derivative of any existing Amiga emulator.

This matters legally and practically. UAE and its descendants (WinUAE, FS-UAE, PUAE,
Amiberry) are GPL-2.0; vAmiga is GPL-3.0; several others carry unclear or mixed
provenance. meta-amiga is GPL-3.0-or-later, and its copyright must remain traceable to
its own contributors. Importing code from those projects — even a single function, even
with attribution — would create a licence-compatibility problem we cannot unwind later
and would compromise the project's ability to relicense, dual-licence or defend itself.

## What contributors may use

Permitted sources for hardware behaviour:

- Published Commodore documentation — the *Amiga Hardware Reference Manual*, *ROM Kernel
  Reference Manuals*, *Amiga Guru Book*, chip datasheets, and Motorola's 68000-family
  programmer's and user's manuals.
- The Amiga hardware itself: measurement, logic-analyser capture, and test programs you
  wrote, run on real machines.
- Original test programs written for this project, and their captured reference output.
- Public specifications of file and disk formats (ADF, IPF/CAPS format notes, SCP flux
  format, LHA, DMS).
- Reading *behaviour* — not source — of another emulator, i.e. running it and observing
  what it does. Observation of output is fact; transcription of implementation is not.

## What contributors may not use

- Source code, in any quantity, from UAE, WinUAE, FS-UAE, PUAE, Amiberry, vAmiga,
  Hatari, Musashi, Cyclone, Castaway, or any other emulator, disassembler-derived core
  or CPU-core library — including translated, machine-converted or LLM-regurgitated
  forms.
- Code derived from disassembly of Kickstart, Workbench, WHDLoad, or any commercial
  Amiga software.
- Generated code whose provenance you cannot state. If an AI tool produced a routine and
  you cannot say what it was derived from, it does not go in.

Structural similarity that follows from the hardware is unavoidable and fine — there is
one correct Blitter minterm table, and everyone's looks alike. Similarity in naming,
comments, control flow or file organisation to another emulator is not, and will be
treated as a provenance failure regardless of intent.

## Contribution gate

Every pull request must assert, in its description:

> I certify that this contribution is my own original work, or is derived only from the
> permitted sources listed in PROVENANCE.md, and contains no code copied or adapted from
> another emulator.

Contributions without that assertion are not merged. Contributions found to breach it
are reverted in full, not patched.

## Kickstart ROMs

No copyrighted ROM image is included in this repository, in its releases, in its test
fixtures, or in CI. Tests that require a Kickstart ROM read it from a path supplied by
the developer and skip cleanly when it is absent. The redistributable AROS ROM is the
only ROM the project ships.
