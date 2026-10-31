#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Oracle 1: assembled bytes against the 68000 Programmer's Reference Manual.

kernel.expected holds, for each instruction of kernel.s, the encoding derived by hand from
the manual; probes.expected does the same for single instructions; asm.expected for the
hand-written assembly of the test programs. The GATE is GNU as, the assembler this project
uses for every hand-written file:
  1. kernel.s assembled with GNU as must equal the expected bytes exactly;
  2. each hand-written program file in asm.expected must assemble to its expected bytes;
  3. each single-instruction probe must assemble with GNU as to the manual's bytes;
  4. clang's compiled C must contain the manual's encoding of a word store to an absolute
     custom-chip address (clang is the C compiler, so its code generation is gated too).
The LLVM M68k ASSEMBLER and DISASSEMBLER are measured beside it and recorded, not relied on:
  5. each probe is also assembled with clang (status in probes.expected: ok, xfail, or
     differs <bytes>), and each kernel encoding is fed to the LLVM disassembler
     (kernel.expected: "-" cannot, "xfail:" known wrong).
At the pinned LLVM tag a deviation from the recorded state fails the check: the record is
stale, or an `xfail` has started to work and the notes in SPIKE-S3 section 4 should change.
Against any other clang the same deviations are printed as notes and do not fail.

Exit 0 pass, 1 mismatch. Writes kernel.bin and kernel.syms to --out for oracle 3.

Usage: check_encodings.py [--bin LLVM-BIN-DIR] [--binutils BINUTILS-BIN-DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
M68K = HERE.parent
PROGRAMS = M68K / "programs"
GNU = "m68k-linux-gnu-"


def run(*cmd: str, stdin: str | None = None) -> str:
    return subprocess.run(cmd, input=stdin, check=True, capture_output=True, text=True).stdout


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def hexb(b: bytes) -> str:
    return " ".join(b[i:i + 2].hex().upper() for i in range(0, len(b), 2))


def read_pin() -> dict[str, str]:
    pin = {}
    for line in (M68K / "toolchain.pin").read_text().splitlines():
        m = re.match(r"([A-Z0-9_]+)=(\S+)", line)
        if m:
            pin[m.group(1)] = m.group(2)
    return pin


def gnu_tool(bindir: Path | None, name: str) -> str:
    if bindir is not None:
        p = bindir / (GNU + name)
        if p.exists():
            return str(p)
        sys.exit(f"missing {GNU}{name} in {bindir}")
    p = shutil.which(GNU + name)
    if p is None:
        sys.exit(f"missing {GNU}{name}: set --binutils, install binutils-m68k-linux-gnu "
                 f"or run tools/m68k/build-binutils.sh")
    return p


def llvm_tool(bindir: Path, *names: str) -> str:
    for n in names:
        if (bindir / n).exists():
            return str(bindir / n)
    sys.exit(f"missing {names[0]} in {bindir}")


def parse_table(path: Path, fields: int):
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        yield [f.strip() for f in line.split("|", fields - 1)]


class Check:
    """GNU as is the gate; the LLVM column fails the check only at the pinned LLVM tag."""

    def __init__(self, args):
        self.out: Path = args.out
        self.pin = read_pin()
        self.fails = 0
        self.llvm_notes = 0
        self.cc = llvm_tool(args.bin, "clang", "clang-18")
        self.mc = llvm_tool(args.bin, "llvm-mc", "llvm-mc-18")
        self.gas = gnu_tool(args.binutils, "as")
        self.oc = gnu_tool(args.binutils, "objcopy")
        self.nm = gnu_tool(args.binutils, "nm")
        clang_v = run(self.cc, "--version").splitlines()[0]
        gas_v = run(self.gas, "--version").splitlines()[0]
        pin_llvm = self.pin["LLVM_TAG"].removeprefix("llvmorg-")
        self.llvm_pinned = bool(re.search(rf"\bversion {re.escape(pin_llvm)}\b", clang_v))
        gas_n = re.search(r"(\d+(?:\.\d+)+)\s*$", gas_v)
        print(f"GNU as    : {gas_v}")
        if gas_n and gas_n.group(1) != self.pin["BINUTILS_VERSION"]:
            print(f"NOTE      binutils {gas_n.group(1)}, the pin says {self.pin['BINUTILS_VERSION']}: "
                  f"acceptable if this check passes")
        print(f"clang     : {clang_v}")
        if not self.llvm_pinned:
            print(f"NOTE      not the pinned LLVM ({self.pin['LLVM_TAG']}): deviations in the "
                  f"LLVM column are notes, not failures")

    def fail(self, msg: str) -> None:
        self.fails += 1
        print(msg)

    def llvm_deviation(self, msg: str) -> None:
        """The LLVM column differs from what is recorded."""
        self.llvm_notes += 1
        if self.llvm_pinned:
            self.fails += 1
            print(msg)
        else:
            print("NOTE      " + msg.strip())

    def text_bytes(self, obj: Path) -> bytes:
        raw = self.out / (obj.name + ".text")
        run(self.oc, "-O", "binary", "-j", ".text", str(obj), str(raw))
        return raw.read_bytes()

    def gnu_assemble(self, src: Path, obj: Path, defsyms: list[str] = ()) -> tuple[bytes | None, str]:
        cmd = [self.gas, "-m68000", "-o", str(obj)]
        for d in defsyms:
            cmd += ["--defsym", d]
        r = subprocess.run(cmd + [str(src)], capture_output=True, text=True)
        if r.returncode != 0:
            return None, r.stderr.strip()
        return self.text_bytes(obj), ""

    def llvm_assemble(self, src: Path, obj: Path) -> bytes | None:
        r = subprocess.run([self.cc, "--target=m68k", "-mcpu=M68000", "-c", str(src), "-o", str(obj)],
                           capture_output=True, text=True)
        return self.text_bytes(obj) if r.returncode == 0 else None

    # 1. kernel.s
    def kernel(self) -> None:
        rows = [(bytes.fromhex(e.replace(" ", "")), d, s) for e, d, s in
                parse_table(HERE / "kernel.expected", 3)]
        obj = self.out / "kernel.o"
        got, err = self.gnu_assemble(HERE / "kernel.s", obj)
        if got is None:
            self.fail(f"ASSEMBLE  GNU as rejects kernel.s: {err}")
            return
        (self.out / "kernel.bin").write_bytes(got)
        want = b"".join(r[0] for r in rows)
        pos = 0
        for enc, _d, src in rows:
            if got[pos:pos + len(enc)] != enc:
                self.fail(f"ENCODING  {src!r}: expected {hexb(enc)}, GNU as gave "
                          f"{hexb(got[pos:pos + len(enc)])}")
                if len(got) != len(want):
                    print("          (the output is a different length, so later rows are shifted)")
                    break
            pos += len(enc)
        if len(got) != len(want):
            self.fail(f"LENGTH    GNU as gave {len(got)} bytes, expected {len(want)}")
        syms = {}
        for line in run(self.nm, str(obj)).splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        (self.out / "kernel.syms").write_text("".join(f"{k}=0x{v:x}\n" for k, v in sorted(syms.items())))
        print(f"kernel    : {len(rows)} instructions, {len(want)} bytes, GNU as "
              f"{'identical to the manual' if got == want else 'DIFFERENT'}")
        self.kernel_disassembly(rows)

    # 5b. the LLVM disassembler on the same encodings (documentation of the backend)
    def kernel_disassembly(self, rows) -> None:
        wrong = raw = 0
        for enc, dis, _src in rows:
            if dis == "-":
                raw += 1
                continue
            known_bad = dis.startswith("xfail:")
            want_text = norm(dis.removeprefix("xfail:"))
            out = run(self.mc, "--disassemble", "--triple=m68k", "-mcpu=M68000",
                      stdin=" ".join(f"0x{b:02x}" for b in enc))
            lines = [norm(l) for l in out.splitlines() if l.strip() and l.strip() != ".text"]
            shown = lines[0] if lines else "<no output>"
            ok = shown == want_text
            if known_bad and not ok:
                wrong += 1
            elif known_bad and ok:
                self.llvm_deviation(f"XPASS     LLVM disassembles {hexb(enc)} correctly now; "
                                    f"remove the xfail")
            elif not ok:
                self.llvm_deviation(f"DISASM    LLVM: {hexb(enc)} reads {shown!r}, recorded {want_text!r}")
        print(f"LLVM disassembler: {len(rows) - raw} encodings, {raw} it cannot read, "
              f"{wrong} it reads wrongly (recorded)")

    # 2. the hand-written assembly of the test programs
    def programs(self) -> None:
        n = 0
        for src, defs, enc in parse_table(HERE / "asm.expected", 3):
            want = bytes.fromhex(enc.replace(" ", ""))
            obj = self.out / (Path(src).name + ".o")
            got, err = self.gnu_assemble(M68K / src, obj, [] if defs == "-" else defs.split())
            if got is None:
                self.fail(f"ASSEMBLE  GNU as rejects {src}: {err}")
            elif got != want:
                self.fail(f"PROGRAM   {src}: expected {hexb(want)}, GNU as gave {hexb(got)}")
            else:
                n += 1
        print(f"programs  : {n} hand-written files assemble to the manual's bytes under GNU as")

    # 3 and 5a. single-instruction probes, GNU as (gate) and clang (recorded)
    def probes(self) -> None:
        gnu_ok = 0
        llvm = {"ok": 0, "xfail": 0, "differs": 0}
        width = 0
        lines = []
        for src, enc, status in parse_table(HERE / "probes.expected", 3):
            want = bytes.fromhex(enc.replace(" ", ""))
            label = src.replace("\\n", " ")
            asm = self.out / "probe.s"
            asm.write_text("\t.text\n\t" + src.replace("\\n", "\n\t") + "\n")
            g, err = self.gnu_assemble(asm, self.out / "probe.gnu.o")
            if g == want:
                gnu_ok += 1
                gcol = "ok"
            else:
                gcol = "FAIL"
                self.fail(f"PROBE     GNU as: {label}: "
                          f"{'rejected: ' + err if g is None else hexb(g)}, the manual says {hexb(want)}")
            l = self.llvm_assemble(asm, self.out / "probe.llvm.o")
            kind, _, rest = status.partition(" ")
            if kind == "ok":
                good = l == want
            elif kind == "xfail":
                good = l != want
            elif kind == "differs":
                good = l == bytes.fromhex(rest.replace(" ", ""))
            else:
                sys.exit(f"probes.expected: unknown status {status!r}")
            shown = "rejected" if l is None else hexb(l)
            if not good:
                what = {"ok": f"{shown}, recorded as correct",
                        "xfail": "now correct, remove the xfail",
                        "differs": f"{shown}, recorded as {rest}"}[kind]
                self.llvm_deviation(f"PROBE     LLVM: {label}: {what}")
            llvm[kind] += 1
            lines.append((label, hexb(want), gcol, status if kind != "ok" else "ok", shown))
            width = max(width, len(label))
        mw = max(len(m) for _l, m, *_ in lines)
        print(f"{'probe':<{width}}  {'manual':<{mw}}  GNU as  LLVM (recorded)  LLVM gave")
        for label, m, g, st, shown in lines:
            print(f"{label:<{width}}  {m:<{mw}}  {g:<6}  {st.split()[0]:<15}  {shown}")
        print(f"probes    : GNU as {gnu_ok} of {len(lines)} match the manual; LLVM recorded as "
              f"{llvm['ok']} correct, {llvm['xfail']} broken, {llvm['differs']} differing")

    # 4. compiled C: MOVE.W #imm,(xxx).L is 0x33FC, immediate word, 32-bit address
    def compiled_c(self) -> None:
        cobj = self.out / "main-check.o"
        run(self.cc, "--target=m68k", "-mcpu=M68000", "-Os", "-ffreestanding", "-fno-pic",
            "-c", str(PROGRAMS / "colour-loop" / "main.c"), "-o", str(cobj))
        code = self.text_bytes(cobj)
        for label, pattern in (("INTENA <- $7FFF", "33FC7FFF00DFF09A"),
                               ("COLOR00 <- $0F00", "33FC0F0000DFF180")):
            if bytes.fromhex(pattern) in code:
                print(f"C store   : {label}: {pattern} present")
            else:
                self.fail(f"C store   : {label}: {pattern} NOT found in the compiled object")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", type=Path, required=True, help="LLVM toolchain bin directory")
    ap.add_argument("--binutils", type=Path, default=None,
                    help="directory with m68k-linux-gnu-as/-objcopy/-nm (default: PATH)")
    ap.add_argument("--out", type=Path, default=M68K / "out")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    c = Check(a)
    c.kernel()
    c.programs()
    c.probes()
    c.compiled_c()
    print("PASS" if c.fails == 0 else f"FAIL ({c.fails})")
    return 0 if c.fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
