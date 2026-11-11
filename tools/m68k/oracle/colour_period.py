#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Read colour-loop's colour period from a screen capture.

The input is what boot_colour_loop.sh records: raw RGB24 frames of a small patch at the centre
of an emulator's window, and the capture's own log, which carries each frame's timestamp
(ffmpeg's `showinfo` filter, `pts_time:`). Each frame is classified as red, green or other by
its mean colour; a colour change is placed halfway between the last frame of the old colour and
the first frame of the new one; and the change times are fitted by least squares to
t_k = t_0 + k * P, so P is the time one colour stays on screen.

The prediction is the program's cycle count on a PAL 68000 with no bus contention, the same
figure SPIKE-S3 section 8 gives: (outer) passes of a 65 536-iteration DBRA loop.

Exit 0 when the colours alternate red, green, red, ... for at least --min-changes changes and
P is within --tolerance of the prediction; 1 otherwise.

Usage: colour_period.py <frames.rgb> <capture.log> [--size 16x16] [--outer 8]
                        [--min-changes 10] [--tolerance 0.02] [--json <out.json>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

PAL_CPU_HZ = 7_093_790  # the PAL A500's 68000 clock, twice the colour clock


def predicted_cycles(outer: int) -> float:
    """Cycles per colour on a 68000 with no wait states, from the Programmer's Reference
    Manual's instruction timings, averaged over the red and the green half.

    colour_delay(outer - 1) runs `outer` passes. Each pass is MOVE.W #imm,Dn (8), 65 535 taken
    DBRA (10 each) and one expired DBRA (14); the outer DBRA is taken outer - 1 times (10) and
    expires once (14). Around the loop, as the built listing has it: MOVE.W #imm,abs.l to
    COLOR00 (20), MOVE.L #imm,(SP) (20), JSR abs.l (20), MOVE.L d16(SP),D0 (16) and RTS (16);
    the green half also takes the BRA.S back to the top (10).
    """
    loop = outer * (8 + 65_535 * 10 + 14) + (outer - 1) * 10 + 14
    around = 20 + 20 + 20 + 16 + 16
    return loop + around + 10 / 2


def classify(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if r > 192 and g < 64 and b < 64:
        return "red"
    if g > 192 and r < 64 and b < 64:
        return "green"
    return "other"


def read_frames(raw: bytes, size: int) -> list[tuple[int, int, int]]:
    n = len(raw) // (size * 3)
    out = []
    for i in range(n):
        f = raw[i * size * 3:(i + 1) * size * 3]
        out.append((sum(f[0::3]) // size, sum(f[1::3]) // size, sum(f[2::3]) // size))
    return out


def read_times(log: str) -> list[float]:
    return [float(t) for t in re.findall(r"pts_time:\s*([0-9.]+)", log)]


def changes(times: list[float], colours: list[str]) -> list[tuple[float, str]]:
    """Red/green changes as (time, new colour). Frames of any other colour are ignored, so the
    boot screen before the program runs produces no change."""
    out: list[tuple[float, str]] = []
    last: tuple[float, str] | None = None
    for t, c in zip(times, colours):
        if c == "other":
            continue
        if last is not None and c != last[1]:
            out.append(((last[0] + t) / 2, c))
        last = (t, c)
    return out


def fit(ts: list[float]) -> tuple[float, float, float]:
    """Least-squares fit of ts[k] = t0 + k * p. Returns p, its standard error and the RMS
    residual."""
    n = len(ts)
    ks = range(n)
    km = sum(ks) / n
    tm = sum(ts) / n
    sxx = sum((k - km) ** 2 for k in ks)
    p = sum((k - km) * (t - tm) for k, t in zip(ks, ts)) / sxx
    t0 = tm - p * km
    res = [t - (t0 + p * k) for k, t in zip(ks, ts)]
    ss = sum(r * r for r in res)
    rms = (ss / n) ** 0.5
    se = (ss / (n - 2) / sxx) ** 0.5 if n > 2 else float("inf")
    return p, se, rms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("frames")
    ap.add_argument("log")
    ap.add_argument("--size", default="16x16", help="captured patch, WxH")
    ap.add_argument("--outer", type=int, default=8, help="the program's DELAY_OUTER")
    ap.add_argument("--min-changes", type=int, default=10)
    ap.add_argument("--tolerance", type=float, default=0.02,
                    help="allowed relative difference between measured and predicted period")
    ap.add_argument("--json", help="also write the result here")
    a = ap.parse_args()

    w, h = (int(v) for v in a.size.split("x"))
    with open(a.frames, "rb") as f:
        frames = read_frames(f.read(), w * h)
    with open(a.log, encoding="utf-8", errors="replace") as f:
        times = read_times(f.read())
    n = min(len(frames), len(times))
    colours = [classify(c) for c in frames[:n]]
    ch = changes(times[:n], colours)

    cycles = predicted_cycles(a.outer)
    predicted = cycles / PAL_CPU_HZ
    result: dict = {"frames": n, "changes": len(ch), "predicted_s": predicted,
                    "predicted_cycles": cycles}
    ok = True
    first = next((c for c in colours if c != "other"), None)
    print(f"frames: {n}, red/green changes: {len(ch)}, first colour seen: {first}")
    if first != "red":
        print("FAIL: the first colour after boot is not red")
        ok = False
    if any(ch[i][1] == ch[i - 1][1] for i in range(1, len(ch))):
        print("FAIL: the colours do not alternate")
        ok = False
    if len(ch) < a.min_changes:
        print(f"FAIL: {len(ch)} changes, at least {a.min_changes} needed")
        ok = False
    else:
        p, se, rms = fit([t for t, _ in ch])
        dev = p / predicted - 1
        result.update(measured_s=p, stderr_s=se, residual_rms_s=rms, deviation=dev)
        print(f"measured:  {p * 1000:.1f} ms per colour (+/- {se * 1000:.1f} ms, 1 sigma;"
              f" residual RMS {rms * 1000:.1f} ms)")
        print(f"predicted: {predicted * 1000:.1f} ms per colour ({cycles:.0f} cycles at"
              f" {PAL_CPU_HZ} Hz, no bus contention)")
        print(f"difference: {dev * 100:+.2f} % (tolerance {a.tolerance * 100:.1f} %)")
        if abs(dev) > a.tolerance:
            print("FAIL: the period is outside the tolerance")
            ok = False
    result["pass"] = ok
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
