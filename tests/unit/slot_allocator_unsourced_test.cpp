// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// The slot-allocator assertions that have no source yet, kept visible as SKIPPED rather
// than written against a guess:
//
//   - SPIKE-S0 test 16: DDFSTRT/DDFSTOP outside the documented range must follow what the
//     hardware does, not a clamp. The manual gives only the $18 and $D8 limits; the rest
//     is a measurement nobody has made (reference section 5.1).
//   - SPIKE-S0 test 13, AGA half: 1-8 planes under the AGA fetch modes. Those postdate the
//     Hardware Reference Manual 3rd edition and no permitted source is held (section 4.4).
//
// Each unskips itself when the generated tables say its data exists, and then fails until
// the assertion is written, so the skip cannot outlive its reason.

#include <cstdio>

#include "meta_amiga/core/chipset/slot_tables.hpp"

namespace tables = meta::amiga::core::chipset::tables;

int main() {
    if (tables::kOutOfRangeDdfVerified) {
        std::fprintf(stderr, "out-of-range DDF behaviour is now sourced: write test 16\n");
        return 1;
    }
    std::fprintf(stderr,
                 "SKIPPED test 16: out-of-range DDFSTRT/DDFSTOP behaviour is unmeasured\n"
                 "SKIPPED test 13 (AGA): no permitted source for the AGA fetch modes\n");
    return 77;
}
