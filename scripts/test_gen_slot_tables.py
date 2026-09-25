#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Tests for gen_slot_tables.py: that it is deterministic, that it carries UNVERIFIED data
# through as absent rather than as a number, and that it refuses tables breaking an
# invariant the transcription states.

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import yaml
except ImportError:
    print("test_gen_slot_tables: PyYAML is not installed, skipping", file=sys.stderr)
    sys.exit(77)

import gen_slot_tables as gen

YAML_TEXT = gen.YAML_PATH.read_text(encoding="utf-8")


def data() -> dict:
    return copy.deepcopy(yaml.safe_load(YAML_TEXT))


class Rendering(unittest.TestCase):
    def test_is_deterministic(self):
        self.assertEqual(gen.render_all(YAML_TEXT), gen.render_all(YAML_TEXT))

    def test_embeds_the_yaml_digest(self):
        import hashlib

        digest = hashlib.sha256(YAML_TEXT.encode("utf-8")).hexdigest()
        for text in gen.render_all(YAML_TEXT).values():
            self.assertIn(f"yaml-sha256: {digest}", text)

    def test_unplaced_refresh_slot_is_not_given_an_index(self):
        core = gen.render_core(data(), "x")
        self.assertIn("kRefreshSlots{0x01, 0x03, 0x05}", core)
        self.assertIn("kRefreshSlotsUnplaced = 1", core)

    def test_null_aga_pattern_emits_no_aga_table(self):
        core = gen.render_core(data(), "x")
        self.assertNotIn("kAga", core)
        self.assertIn("AGA fetch modes: no table", core)

    def test_null_out_of_range_behaviour_is_marked_unverified(self):
        self.assertIn("kOutOfRangeDdfVerified = false", gen.render_core(data(), "x"))

    def test_free_offsets_render_as_zero(self):
        self.assertIn("kLoresPlaneByOffset{0, 4, 6, 2, 0, 3, 5, 1}", gen.render_core(data(), "x"))


class Refusals(unittest.TestCase):
    def test_refuses_a_fixed_slot_on_the_cpu_parity(self):
        d = data()
        d["fixed_allocations"]["disk"]["slots"][0] = 0x08
        with self.assertRaisesRegex(gen.TableError, "68000"):
            gen.render_core(d, "x")

    def test_refuses_two_devices_on_one_slot(self):
        d = data()
        d["fixed_allocations"]["audio"]["slots_by_channel"][0] = 0x07
        with self.assertRaisesRegex(gen.TableError, "both claim"):
            gen.render_core(d, "x")

    def test_refuses_a_pattern_missing_a_plane(self):
        d = data()
        d["bitplane_fetch"]["lores"]["plane_by_offset"][2] = None
        with self.assertRaisesRegex(gen.TableError, "planes 1..6"):
            gen.render_core(d, "x")

    def test_refuses_a_pattern_of_the_wrong_length(self):
        d = data()
        d["bitplane_fetch"]["hires"]["plane_by_offset"].append(None)
        with self.assertRaisesRegex(gen.TableError, "group is 4"):
            gen.render_core(d, "x")


if __name__ == "__main__":
    unittest.main()
