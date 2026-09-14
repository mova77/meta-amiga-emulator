<!--
SPDX-License-Identifier: GPL-3.0-or-later
Copyright (C) 2026 The meta-amiga authors

PROVENANCE.md § Contribution gate requires every pull request to carry the clean-room
certification in its description. This template puts that sentence in the one text box
every contributor types into, instead of leaving it in a document a first-time
contributor has no reason to have opened.

It is a prompt, not a gate. Nothing verifies it: ci.yml runs on `push:` and
`workflow_dispatch:` only, and a body-checking job needs a `pull_request` trigger that is
deliberately absent until external contributions start. A contributor can delete this
template. The gate is the reviewer refusing to merge without the assertion.

Delete the sections that do not apply, but not the certification.
-->

## What this changes, and why

<!-- What a reviewer needs in order to judge it. Link the ADR or specification section it
     implements, contradicts or supersedes, if there is one. -->

## Evidence

<!-- What you ran, on what, and what it said. Paste the output rather than describing it.
     "Tests pass" is not evidence; the ctest summary is. -->

---

## Clean-room certification

Required by [PROVENANCE.md](PROVENANCE.md) § *Contribution gate*. A contribution without
this assertion is not merged; one found to breach it is reverted in full, not patched.

> I certify that this contribution is my own original work, or is derived only from the
> permitted sources listed in PROVENANCE.md, and contains no code copied or adapted from
> another emulator.

- [ ] I assert the statement above.

Read [PROVENANCE.md](PROVENANCE.md) before ticking it if you have not. It is more specific
than it looks: reading another emulator's *behaviour* is permitted, and transcribing its
*implementation* is not — in any quantity, including translated, machine-converted or
LLM-regurgitated forms. Generated code whose provenance you cannot state does not go in.

## Checklist

- [ ] **No ROM, key, disk image or other copyrighted media** is added — to the tree, the
      tests or the fixtures.
      [`ADR-ROM-03`](docs/adr/ADR-ROM-03-kickstart-rom-handling.md) D1, enforced by the
      `no-copyrighted-media` CI job. A test needing a Kickstart ROM reads it from a
      developer-supplied path and skips cleanly when it is absent.
- [ ] **Every new source file carries an SPDX identifier.**
      [Specification](docs/specification.md) §10.
- [ ] **For a change under `src/core/`:** no I/O, no thread, no platform header and no
      third-party include added.
      [`ADR-PORT-04`](docs/adr/ADR-PORT-04-portability-and-backends.md) D1 — the core is
      freestanding, and widening what it may depend on is a policy change that wants
      saying out loud here rather than arriving as an include nobody notices.
- [ ] **For anything claiming a performance improvement:** before and after numbers, on
      both architectures, in this description.
      [`ADR-PERF-06`](docs/adr/ADR-PERF-06-optimisation-policy.md) D2 — a change that
      cannot demonstrate its improvement is reverted regardless of how obviously correct
      it looks.
