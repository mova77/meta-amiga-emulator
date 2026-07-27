# ADR-ROM-03 — Kickstart ROMs: identify by hash, decrypt Amiga Forever, ship AROS, bundle nothing

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | ROM acquisition, identification, decryption, storage; CI and release artifacts |

## Context

An Amiga emulator is useless without a Kickstart ROM, and every Kickstart ROM is
copyrighted — held today by Cloanto / Amiga Corporation, who sell licensed copies as
**Amiga Forever**. A GPL project distributing them, or making it convenient to obtain them
illegitimately, would be indefensible and would put the project at risk for no benefit.

There are three legitimate sources a user may have: a licensed Amiga Forever installation
(where ROMs are stored encrypted alongside a personal `rom.key`), a dump they made from
hardware they own, or the free AROS ROM replacement.

Users also arrive with broken dumps — byte-swapped, half-size, truncated, wrong model,
padded — and an emulator that responds with a black screen teaches them nothing.

## Decision

**D1 · Nothing copyrighted is ever bundled.** No Kickstart image ships in the repository,
in a release artifact, in a test fixture, in a container image or in CI. This is
unconditional.

**D2 · Identification is by SHA-1 against a built-in database.** Every known ROM revision
— 1.2 (33.180) through 3.2, the A1000 bootstrap, the CDTV and CD32 extended ROMs, the
logical/split variants — is listed with its hash, size, model applicability and version
string. A loaded file is identified, not guessed from its filename or size.

**D3 · Malformed dumps are diagnosed, not tolerated.** The loader detects byte-swapping,
odd/even split halves, truncation and common padding, states exactly what it found, and
offers the correction where one exists. It corrects nothing silently: an emulator that
quietly repairs its input cannot be trusted when it reports a compatibility result.

**D4 · Amiga Forever encrypted ROMs are supported natively.** A file beginning with the
11-byte ASCII magic `AMIROMTYPE1` is decrypted by XOR against the bytes of the user's
`rom.key`, cycled over the ciphertext, and the plaintext is then identified per D2. The
user points at their own licensed installation; the key is read, never copied into our
configuration, never written into savestates, and never included in a bug report or
diagnostic bundle.

This is interoperability with a format the user has a licence to use. It does not
circumvent anything: the key is the user's, supplied by the user, for ROMs the user
bought.

**D5 · AROS ships as the default.** The AROS m68k ROM replacement is redistributable and
is bundled so the emulator does something useful on first launch with no ROM at all. It is
labelled as a replacement, not as Kickstart, because its behavioural differences are real
and will otherwise be reported as our bugs.

**D6 · Tests skip, they do not fail.** Any test needing a real Kickstart reads it from a
developer-supplied path and skips cleanly when absent. CI never has one, so the CI-visible
suite must be meaningful without it — which pushes coverage toward AROS, toward original
test programs, and toward the parts of the corpus that are legally redistributable.

## Consequences

- The ROM database is a maintained asset. New revisions and variants get added with their
  hashes; a hash that is not in the database is reported as unknown rather than rejected,
  and the user can proceed at their own risk.
- CI compatibility coverage is structurally weaker than local coverage. Accepted: the
  alternative is a licensing breach. The corpus manifest marks which entries are
  CI-runnable so the gap is visible rather than assumed away.
- D4 means shipping a working `rom.key` reader. Its input handling is a parser fed
  user-supplied files and is treated as a security boundary — bounds-checked, fuzzed, and
  covered by the threat model.
- Bundling AROS adds a redistribution obligation: its licence and source availability are
  tracked in `docs/third-party.md`.

## Open decisions

- Whether to support Cloanto's newer container formats beyond `AMIROMTYPE1`, if the user's
  Amiga Forever version uses one.
- Whether ROM images referenced by a savestate are identified by hash only (portable,
  requires the user to have the ROM) or embedded (not permissible under D1) — the former,
  almost certainly, but the failure mode when the ROM is missing needs designing.
