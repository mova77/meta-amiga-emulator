# SPIKE-S1 — The 68k instruction table and its generator

| | |
|---|---|
| **Status** | Draft — under review, gates every CPU implementation story |
| **Date** | 2026-07-27 |
| **Implements** | [ADR-CPU-02](../adr/ADR-CPU-02-68k-core-strategy.md) D1, D3, D5 · specification §2.2 |
| **Governs** | `core/cpu` — the instruction table, the generator, and the shape of every handler |

ADR-CPU-02 D1 says instruction semantics are written once in a declarative table and
expanded by a build-time generator. This spike fixes the shape of that table and the
generator's contract. Nothing in the CPU epic may be written before it is accepted,
because the table's shape decides whether the epic is tractable or is thirty thousand
lines of near-duplicate handlers, each one a place for a flag bug to hide.

---

## 1. Problem

The 68000 has roughly 80 instruction forms over 12 addressing modes and 3 operand sizes,
and each combination has its own legality rules, flag effects and cycle cost. The 020+
additions roughly double it. Expanded naively that is tens of thousands of handlers.

Three properties are non-negotiable, and they are what rule out the obvious approaches:

1. **Exactness.** Correct flags — including the awkward cases (§4.3) — correct exception
   frames per model, correct bus cycle counts feeding the slot allocator.
2. **Per-model divergence as data.** Seven CPU models differ in instruction availability,
   privilege, cycle counts and stack frame format. `#ifdef` per model does not survive
   contact with seven of them.
3. **Total coverage of the 65 536-entry opcode space.** Every word either decodes to
   exactly one instruction or raises the correct exception. "Exactly one" must be *proven*,
   not assumed — overlapping encodings are the classic 68k emulator bug and they are
   invisible until a specific program hits them.

Ruled out up front: importing a third-party core (Musashi, Cyclone, the UAE-derived cores)
is excluded by [PROVENANCE.md](../../PROVENANCE.md) regardless of technical merit. The
table-driven approach is partly a response to that constraint — it is what makes writing
our own tractable.

---

## 2. Decision summary

| # | Decision |
|---|---|
| **S1-1** | The table is **C++ constexpr data**, compiled as part of the build — not a bespoke text format. |
| **S1-2** | The generator is a **standalone C++ tool** in `tools/`, built by the project and run by a CMake custom command. No new toolchain dependency. |
| **S1-3** | Addressing-mode legality is expressed as the manual's **category algebra**, not as mode lists. |
| **S1-4** | Flag effects are a **declarative vocabulary**, not a bitmask and not free code. |
| **S1-5** | Per-model divergence is **rows in tables**, never preprocessor conditionals. |
| **S1-6** | The generator **proves** disjointness and total coverage over all 65 536 opcodes, and fails the build otherwise. |
| **S1-7** | Handlers perform **explicit bus operations** and return nothing. |

---

## 3. Why constexpr C++ and not a DSL

The obvious choice is a text format (TOML, JSON, a custom `.def`) plus a Python generator.
Rejected for two reasons that matter more than the syntax:

- **A text format needs a parser, and the parser needs its own tests and error messages.**
  That is a component to maintain before a single instruction is described. Worse, a typo
  in the table becomes a runtime error in the generator instead of a compile error.
- **A Python generator is a toolchain dependency on every developer machine and every CI
  runner**, including Windows, where it is the least reliable. ADR-PORT-04 D6 says a
  dependency needs justification; convenience of string formatting is not enough.

Writing the table as `constexpr` C++ struct literals gets the compiler to type-check it for
free. A misspelled enumerator, a size that is not a `Size`, a flag effect that does not
exist — all become compile errors at the point of the mistake. The generator then
`#include`s the table and emits source; it is a program that reads structured data already
in its own address space, so it has no parser at all.

The cost: the table is slightly noisier to read than TOML would be, and designated
initialisers are doing a lot of the work of keeping it readable. Accepted.

**Rejected alternative — pure `constexpr`/template expansion with no generator at all.**
Elegant, and it removes the build step entirely. It also instantiates tens of thousands of
handler bodies through the template machinery, which pushes compile times into the tens of
minutes and is where MSVC gives up. It also produces generated code that cannot be read
when debugging a flag bug, which is exactly when you need to read it.

---

## 4. The table

### 4.1 Encoding patterns

An instruction is declared once with its opcode pattern, where each variable field is named
rather than positional:

```cpp
// Illustrative shape, not final syntax.
struct Encoding {
    u16 fixed;              // bits that are literal
    u16 mask;               // which bits `fixed` constrains
    Field fields[4];        // named variable fields and their bit positions
};

enum class Field : u8 { None, DataReg, AddrReg, Opmode, EffectiveAddress, Size2, Count, Condition, /* … */ };
```

The generator enumerates every assignment of every variable field, computes the resulting
opcode word, and claims it. A field is never expanded into a legal value the schema does
not permit — which is how the effective-address category (§4.2) prunes the space.

### 4.2 Addressing-mode legality is the manual's category algebra

The M68000PRM does not specify legality as mode lists. It specifies it as four overlapping
categories, and every instruction's legality is an intersection of them:

| Category | Contains |
|---|---|
| **Data** | Everything except `An` |
| **Memory** | Everything except `Dn` and `An` |
| **Control** | `(An)`, `d16(An)`, `d8(An,Xn)`, `abs.W`, `abs.L`, `d16(PC)`, `d8(PC,Xn)` |
| **Alterable** | Everything except the PC-relative modes and immediate |

So a declaration says `EaClass::Memory | EaClass::Alterable`, and the generator expands it
to the twelve-mode set. Two things follow, and both matter:

- The table reads like the manual, so transcription is checkable line by line against it
  rather than by re-deriving mode lists.
- Legality is **size-dependent** where the hardware makes it so, and the schema must carry
  that. `ADD.B <ea>,Dn` excludes `An` as a source; `ADD.W`/`ADD.L` permit it. That is one
  row with a per-size EA class, not three declarations.

Mode 7 is expanded by its register field (`abs.W`=0, `abs.L`=1, `d16(PC)`=2, `d8(PC,Xn)`=3,
`#imm`=4), and the unassigned mode-7 registers are among the encodings that must fall
through to the illegal-instruction path (§6.2).

### 4.3 Flag effects are a vocabulary, not a bitmask

The tempting schema is `flags: N|Z|V|C`. It is wrong, and `ADDX` is why.

`ADDX` does not *set* Z the way `ADD` does. It **clears Z if the result is non-zero, and
leaves Z unchanged otherwise** — so that Z survives across a multi-precision addition and
ends up meaning "the whole multi-word result was zero". A bitmask records that Z is
"affected" and loses the only thing about it that matters.

So the schema names effects:

```cpp
enum class FlagEffect : u8 {
    Unaffected,
    Set,             // set to 1
    Cleared,         // set to 0
    FromResult,      // N: sign of result; Z: result == 0
    FromCarry,       // C/X: carry or borrow out
    FromOverflow,    // V: signed overflow
    ClearedIfNonZero // Z on ADDX/SUBX/ABCD/SBCD/NEGX — cleared if non-zero, else held
};

struct FlagEffects { FlagEffect x, n, z, v, c; };
```

Every one of the seven is a distinct code path in the generated handler, written once. The
list is deliberately closed: an instruction whose flag behaviour does not fit is a signal to
extend the vocabulary with a reviewed addition, not to inline a lambda into the table.

### 4.4 Per-model divergence is rows

```cpp
struct ModelBehaviour {
    Model model;              // M68000 … M68060
    Availability availability;// Present, Absent, Privileged, TrapsToSoftware
    CycleCost cost;           // per addressing mode class
};
```

`Availability` covers the cases that actually occur, and each one is a real divergence:

- `MOVE from SR` is unprivileged on the 68000 and **privileged from the 68010 on**. Software
  that runs on both must be emulated differently per model, and Kickstart cares.
- `MOVEC`, `MOVES`, `RTD` appear at the 68010.
- Bitfield operations, `CAS`/`CAS2`, `CHK2`/`CMP2`, `DIVSL`/`DIVUL`, `PACK`/`UNPK`,
  `TRAPcc` and the extended addressing modes appear at the 68020.
- `CALLM`/`RTM` exist on the 68020/030 and are gone on the 68040.
- `MOVE16` appears at the 68040.
- The 68060 traps a set of instructions to software for the 68060 support package to
  emulate — `TrapsToSoftware`, not `Absent`, because the observable behaviour is an
  exception the OS handles, not an illegal instruction.

Exception stack frame formats are the same shape of problem and get the same treatment: a
per-model table from (vector, model) to frame format, covering the 68000's group-0 frame and
the format-word frames from the 68010 on. **The frame layouts themselves are transcription
work (§8).**

---

## 5. Worked example: the `ADD` group

This group was chosen because it demonstrates the schema's hardest requirement — that
sub-opcodes and EA restrictions are two views of the same bits and must be *proven* to tile.

`ADD` occupies line D (`1101`). Its opmode field selects size and direction:

```
1101 rrr ooo eeeeee
     |   |   └── effective address (mode 3 bits, register 3 bits)
     |   └────── opmode
     └────────── data register
```

| opmode | Instruction | Direction | EA class |
|---|---|---|---|
| `000` `001` `010` | `ADD.B/W/L <ea>,Dn` | ea → Dn | Data (B) · All (W, L) |
| `011` | `ADDA.W <ea>,An` | ea → An | All |
| `100` `101` `110` | `ADD.B/W/L Dn,<ea>` | Dn → ea | **Memory Alterable** |
| `111` | `ADDA.L <ea>,An` | ea → An | All |

And `ADDX` also lives on line D:

```
1101 xxx 1ss 00m yyy      m = 0: ADDX Dy,Dx     m = 1: ADDX -(Ay),-(Ax)
```

Read the bits carefully: `ADDX`'s `1ss` is the *same field* as `ADD`'s opmodes
`100`/`101`/`110`, and its `00m` sits exactly where `ADD`'s **EA mode field** sits — taking
mode `000` (`Dn`) and mode `001` (`An`).

Those are precisely the two modes that "Memory Alterable" excludes.

So `ADDX` fills exactly the hole `ADD`'s EA class leaves, and the two declarations tile line
D without overlap and without a gap. Neither declaration mentions the other. **The generator
proves it** (§6.1) — and if a future transcription error widens `ADD`'s EA class to `Data
Alterable`, the build fails with the specific opcodes now claimed twice, rather than
`ADDX` silently disappearing under `ADD` and multi-precision arithmetic breaking in a way
that surfaces months later as one failing demo.

The same structure repeats on line C (`AND`/`ABCD`/`EXG`/`MULU`), line 9 (`SUB`/`SUBX`),
line 8 (`OR`/`SBCD`/`DIVU`) and line B (`CMP`/`CMPM`/`EOR`). Line C is the messiest and is
the generator's stress test.

Flag effects for the three, showing the vocabulary earning its keep:

| | X | N | Z | V | C |
|---|---|---|---|---|---|
| `ADD` | FromCarry | FromResult | FromResult | FromOverflow | FromCarry |
| `ADDA` | Unaffected | Unaffected | Unaffected | Unaffected | Unaffected |
| `ADDX` | FromCarry | FromResult | **ClearedIfNonZero** | FromOverflow | FromCarry |

---

## 6. The generator

### 6.1 Contract

**Input:** the table headers, compiled in. **Outputs:**

| Artifact | Purpose |
|---|---|
| `opcode_table.inc` | 65 536-entry dispatch table |
| `handlers_*.inc` | Generated handler bodies, grouped for compile parallelism |
| `coverage.txt` | Every opcode with its claimant, or its fall-through class |
| `conflicts.txt` | Empty, or the build has already failed |

Generated sources are **not committed** (ADR-CPU-02). The table is the source of truth; the
generator has its own tests; CI verifies that regenerating produces byte-identical output,
so a stale checked-in artefact cannot drift.

### 6.2 The two proofs

These are the reason the generator exists at all, and they run on every build:

- **Disjointness.** Two declarations claiming one opcode is a hard error naming both
  declarations and the opcodes.
- **Total coverage.** All 65 536 opcodes are accounted for. Every unclaimed word is
  classified: `$Axxx` → line-A emulator trap (vector 10), `$Fxxx` → line-F emulator trap
  (vector 11), everything else → illegal instruction (vector 4). An opcode that falls into
  none of those classes is an error. Software uses line-A and line-F deliberately, so these
  are behaviour, not a fallback.

A conflict is a build failure, not a warning. The whole point is that this class of bug
cannot reach a user.

### 6.3 Dispatch

Computed-goto threaded dispatch on Clang and GCC, portable `switch` on MSVC (ADR-CPU-02 D3).
The generator emits both from one description. Handler grouping across translation units is
a compile-time-parallelism decision and must not change behaviour — asserted by CI
regenerating with a different grouping and diffing the differential-execution trace.

---

## 7. Handler shape

Per ADR-CPU-02 D4, a handler performs bus operations and returns nothing:

```cpp
void add_l_ea_dn(Cpu& cpu, u16 opcode) noexcept;   // no cycle count returned
```

Cycles are consumed by the reads and writes themselves, scheduled against the Agnus slot
allocator (SPIKE-S0 §4). Instruction timing is therefore *emergent*: the same instruction
takes longer when more bitplanes are enabled, without a single line of code knowing that.

Two consequences worth stating because they constrain everything downstream:

- **Prefetch is modelled, not skipped.** The 68000's two-word prefetch queue is observable —
  self-modifying code and some copy protections depend on it — and the 020+ instruction
  cache and pipeline change the observable bus traffic. A handler cannot assume its operands
  are already fetched.
- **A handler may be suspended mid-instruction** by bus contention. State that must survive
  a stall lives in the CPU object, not in handler locals.

---

## 8. Transcription work — not yet done, and not to be guessed

As in SPIKE-S0 §3.2, the *schema* is this spike's deliverable and the *data* is separate,
reviewable work. Nothing may be implemented against guessed values.

- [ ] The instruction inventory per model, from the *M68000 Programmer's Reference Manual*
      and each model's user manual — encoding, EA classes per size, flag effects, privilege.
- [ ] Per-model cycle costs, including the 68000's documented read/write/internal breakdown
      that the bus protocol needs.
- [ ] Exception vector assignments and per-model stack frame formats.
- [ ] The 68060 `TrapsToSoftware` set.
- [ ] Divergences between the manuals and hardware, recorded with the measurement that found
      them.

The declarations in §5 are illustrative and are themselves subject to this transcription.

---

## 9. Differential execution — designing for a fast tier that does not exist yet

ADR-CPU-02 D2 makes the interpreter the permanent oracle, and D6 defers the JIT to phase 7.
That deferral is only safe if the interpreter is built so a future fast tier can be checked
against it. Three requirements, all cheap now and expensive to retrofit:

1. **Architectural state is snapshottable and comparable** — registers, SR, the prefetch
   queue, pending exception state — as one addressable object.
2. **The bus operation sequence is observable** as an ordered trace. Equivalence means the
   same architectural state *and* the same bus traffic, since the chipset sees only the
   latter.
3. **Execution is steppable at instruction granularity.** A JIT that batches bus cycles
   between chipset-visible accesses cannot be compared instruction by instruction; that is
   the open decision on ADR-CORE-01, and this spike does not resolve it. It only ensures the
   interpreter side of the comparison exists.

---

## 10. Test plan (SPARC · Refinement)

Acceptance criteria for the generator story that follows this spike.

| # | Assertion |
|---|---|
| 1 | The generator claims each of the 65 536 opcodes at most once |
| 2 | Every opcode is claimed or classified (illegal / line-A / line-F) |
| 3 | Line D expands to `ADD`, `ADDA` and `ADDX` with no overlap and no gap |
| 4 | Widening an EA class to create an overlap fails the build, naming both claimants |
| 5 | Removing a declaration to create a gap fails the build, naming the opcodes |
| 6 | Each `FlagEffect` is exercised by at least one instruction, and `ClearedIfNonZero` preserves Z across a multi-word `ADDX` chain |
| 7 | Per-model availability is honoured: `MOVE from SR` is unprivileged on 68000, privileged on 68010+ |
| 8 | A 68060 `TrapsToSoftware` instruction raises the exception rather than executing or faulting as illegal |
| 9 | Regeneration is byte-identical; a different handler grouping does not change the differential trace |
| 10 | A handler suspended mid-instruction by bus contention resumes with identical results |
| 11 | Architectural state and bus trace are both snapshottable and comparable |

---

## 11. Acceptance

Accepted when §4's schema is reviewed and the §5 expansion is checked against the
*M68000PRM* by a second reader. §8's transcription is **not** a condition of acceptance — it
is the work this spike unblocks. Tests 1–11 become the acceptance criteria of the generator
story.

## 12. Open decisions

- Whether the FPU (68881/68882 and the integrated units) shares this table or gets its own.
  Its encoding space is the F-line coprocessor interface and its "flag effects" are a
  different condition-code model, which argues for a sibling table with the same generator.
- Whether MMU instructions (`PMOVE`, `PTEST`, …) are tabled now or when the MMU scope is
  settled — an open decision on ADR-CPU-02.
- Whether the generated coverage report is published as a project artefact. It is the most
  legible evidence that the decoder is complete, which argues yes.
