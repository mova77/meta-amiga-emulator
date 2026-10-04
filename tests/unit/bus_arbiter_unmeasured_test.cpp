// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// The bus-protocol assertion that has no source yet, kept visible as SKIPPED rather than
// written against a guess:
//
//   - SPIKE-S0 test 19: with BLTPRI clear, the Blitter yields within its bounded run. The
//     spike states no bound and no document in this repository gives one; it is a hardware
//     measurement. Until it is made, the arbiter runs on the placeholder
//     `kBlitterYieldRunUnmeasured`, and asserting that placeholder would test nothing but
//     itself.

#include <cstdio>

int main() {
    std::fprintf(stderr,
                 "SKIPPED test 19: the Blitter's BLTPRI-clear yield bound is unmeasured "
                 "(kBlitterYieldRunUnmeasured is a placeholder)\n");
    return 77;
}
