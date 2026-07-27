# ADR-TEST-05 — Compatibility is a measured number, not a claim

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | Verification method, corpus governance, CI gating |
| **Depends on** | [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) · [ADR-PORT-04](ADR-PORT-04-portability-and-backends.md) |

## Context

"99 % compatible" is the standard claim in this field and it is almost never falsifiable —
no corpus is named, no method is given, no run is reproducible. The project's headline goal
is a compatibility number, so the number has to mean something or the goal is decoration.

Emulator bugs are also disproportionately *regressions*: a timing fix for one demo breaks
three others, and without an automatic corpus nobody finds out for months. Manual testing
does not scale past a few dozen titles and cannot catch a one-frame desync at all.

Determinism (ADR-CORE-01 D6) and headless operation (ADR-PORT-04 D2) exist to make this
decision possible. This ADR spends them.

## Decision

**D1 · The corpus is a versioned manifest in the repository.** Each entry declares: title,
model and chipset configuration, the SHA-1 of the media it expects, an input script, and
the checkpoints at which output is hashed. The manifest is data under review like any
other file. **It contains no media** — only hashes of media the developer supplies.

**D2 · Verification is framebuffer and audio hashing at declared checkpoints.** A run is
driven by its input script in headless deterministic mode; at each checkpoint the full
overscan framebuffer and the accumulated audio are hashed and compared to stored
references. Games are additionally scored boot-to-playable; demos must match every
checkpoint, because a one-frame desync is a timing bug and the whole point is to catch it.

**D3 · A reference hash is only created from a verified-correct run.** Blessing output is
an explicit, reviewed act with a stated justification — never a bulk re-record. A
regression that gets blessed is a regression that becomes permanent.

**D4 · Three tiers, run at different cadences.**

| Tier | Content | Cadence |
|------|---------|---------|
| **Unit** | Original 68k test programs for CPU, chipset and timing behaviour; scheduler and decoder tests | Every commit, all platforms |
| **Redistributable corpus** | AROS boots, demos with explicit distribution permission, our own test programs | Every commit |
| **Full corpus** | Licensed games, Kickstart/Workbench revisions, ranked demoscene productions | Locally against media the developer owns; before every release |

CI can only run tiers 1 and 2 ([ADR-ROM-03](ADR-ROM-03-kickstart-rom-handling.md) D1). The
manifest marks which tier each entry is in, so the coverage gap is a visible number rather
than an unexamined assumption.

**D5 · The published compatibility figure carries its provenance.** Every claim states the
corpus version, the build, the date and the pass count. `26.1.0 — 1 847/1 863 (99.1 %),
corpus 26.1` is a claim; "99 % compatible" is not.

**D6 · Hardware tests are written before the subsystem, wherever the behaviour is known.**
They are the specification made executable, and they are what tells us the slot allocator
is right before six subsystems are built on top of it.

## Consequences

- Building the corpus and its reference hashes is substantial, ongoing work that produces
  no visible feature. It is planned as first-class work, not absorbed into slack.
- Reference hashes are only as good as the run that produced them. D3 is the control, and
  it depends on human discipline; it is called out in the review checklist for that reason.
- Demos must be run with explicit distribution permission to enter tier 2. Obtaining that
  permission is outreach work, and the tier-2 corpus will start small.
- Determinism becomes load-bearing. If a change makes a run non-reproducible, the corpus
  stops working — so non-determinism is a build-breaking defect, not a curiosity.
- Bisecting a compatibility regression becomes mechanical: the corpus identifies the
  commit, the input script reproduces it, the deterministic core makes it repeatable.

## Open decisions

- Whether checkpoint hashes are of the raw overscan framebuffer or a canonicalised
  presentation, and how tolerant (if at all) audio comparison should be.
- How to handle titles that are genuinely non-deterministic on real hardware (uninitialised
  memory reads, disk timing races) — quarantine tier, or per-entry tolerance.
- Whether to publish the reference hashes and input scripts for third-party verification.
