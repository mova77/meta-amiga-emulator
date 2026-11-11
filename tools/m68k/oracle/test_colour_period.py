#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
"""Tests for colour_period.py on synthetic captures: a grey boot screen, then red and green
alternating at a known period, sampled at 50 frames per second.

Run: python3 -m unittest discover -s tools/m68k/oracle -p 'test_*.py'
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import colour_period as cp  # noqa: E402

GREY, RED, GREEN = (68, 68, 68), (255, 0, 0), (0, 255, 0)


def capture(period: float, boot: float = 5.0, seconds: float = 30.0, first=RED,
            fps: float = 50.0, size: int = 4) -> tuple[bytes, str]:
    """Frames and a showinfo-style log for a screen that shows grey until `boot`, then
    alternates `first` and the other colour every `period` seconds."""
    other = GREEN if first == RED else RED
    raw = bytearray()
    log = []
    n = int(seconds * fps)
    for i in range(n):
        t = i / fps
        if t < boot:
            c = GREY
        else:
            c = first if int((t - boot) / period) % 2 == 0 else other
        raw += bytes(c) * size
        log.append(f"[Parsed_showinfo_0 @ 0x0] n:{i} pts:{i} pts_time:{t:.6f} duration:1")
    return bytes(raw), "\n".join(log) + "\n"


class ColourPeriod(unittest.TestCase):
    def test_prediction_matches_the_spike(self):
        # SPIKE-S3 section 8 gives about 0.74 s per colour for 8 passes.
        self.assertAlmostEqual(cp.predicted_cycles(8) / cp.PAL_CPU_HZ, 0.7391, places=4)

    def test_fit_recovers_the_period(self):
        raw, log = capture(0.7445)
        times = cp.read_times(log)
        colours = [cp.classify(c) for c in cp.read_frames(raw, 4)]
        ch = cp.changes(times, colours)
        self.assertGreaterEqual(len(ch), 30)
        self.assertEqual(ch[0][1], "green")  # the first change is red to green; grey is not one
        p, se, _ = cp.fit([t for t, _ in ch])
        self.assertAlmostEqual(p, 0.7445, delta=0.002)
        self.assertLess(se, 0.002)

    def run_cli(self, raw: bytes, log: str, *args: str) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as d:
            fr, lg = os.path.join(d, "f.rgb"), os.path.join(d, "c.log")
            with open(fr, "wb") as f:
                f.write(raw)
            with open(lg, "w", encoding="utf-8") as f:
                f.write(log)
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "colour_period.py")
            return subprocess.run([sys.executable, "-I", script, fr, lg, "--size", "2x2", *args],
                                  capture_output=True, text=True, check=False)

    def test_passes_within_tolerance(self):
        r = self.run_cli(*capture(0.7445))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_fails_outside_tolerance(self):
        r = self.run_cli(*capture(0.80))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("outside the tolerance", r.stdout)

    def test_fails_when_green_comes_first(self):
        r = self.run_cli(*capture(0.7445, first=GREEN))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("not red", r.stdout)

    def test_fails_on_too_few_changes(self):
        r = self.run_cli(*capture(0.7445, seconds=8.0))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("needed", r.stdout)


if __name__ == "__main__":
    unittest.main()
