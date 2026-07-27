// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/timing.hpp"

#include "check.hpp"

namespace {

using meta::amiga::core::BeamGeometry;
using meta::amiga::core::Cycle;
using meta::amiga::core::geometryFor;
using meta::amiga::core::kNtscGeometry;
using meta::amiga::core::kPalGeometry;
using meta::amiga::core::u32;
using meta::amiga::core::VideoStandard;

void palIsUniformAndExact() {
    // Every PAL line is 227 colour clocks; 312 lines short, 313 long.
    for (u32 line = 0; line < 313; ++line) {
        CHECK_EQ(kPalGeometry.ccksInLine(line), u32{227});
    }
    CHECK_EQ(kPalGeometry.ccksInFrame(false), Cycle{227} * 312);  // 70 824
    CHECK_EQ(kPalGeometry.ccksInFrame(true), Cycle{227} * 313);   // 71 051
}

/// NTSC averages 227.5 colour clocks per line by alternating 227 and 228. The average is
/// the part that is certain, so that is what is asserted; the phase of the alternation is
/// an open question on ADR-CORE-01 and is deliberately not pinned down by a test that
/// would only enshrine a guess.
void ntscAveragesTwoTwentySevenAndAHalf() {
    const Cycle shortFrame = kNtscGeometry.ccksInFrame(false);
    CHECK_EQ(shortFrame, Cycle{59'605});
    CHECK_EQ(shortFrame * 2, Cycle{455} * 262);  // 227.5 × 262, without the fraction
}

void geometrySelection() {
    CHECK_EQ(geometryFor(VideoStandard::Pal).shortFrameLines, kPalGeometry.shortFrameLines);
    CHECK_EQ(geometryFor(VideoStandard::Ntsc).shortFrameLines, kNtscGeometry.shortFrameLines);
    CHECK(!geometryFor(VideoStandard::Pal).longLinesAlternate);
    CHECK(geometryFor(VideoStandard::Ntsc).longLinesAlternate);
}

/// The 68000 runs at exactly twice the colour clock. That relationship is why the colour
/// clock is the project's unit of time, so it is worth asserting rather than assuming.
void cpuClockIsTwiceTheColourClock() {
    CHECK_EQ(meta::amiga::core::colourClockHz(VideoStandard::Pal) * 2, u32{7'093'790});
    CHECK_EQ(meta::amiga::core::colourClockHz(VideoStandard::Ntsc) * 2, u32{7'159'090});
}

void geometryIsUsableAtCompileTime() {
    static_assert(kPalGeometry.ccksInFrame(false) == 70'824);
    static_assert(kPalGeometry.ccksInLine(1) == 227);
    static_assert(BeamGeometry{227, true, 262, 263}.ccksInLine(1) == 228);
    CHECK(true);
}

}  // namespace

int main() {
    palIsUniformAndExact();
    ntscAveragesTwoTwentySevenAndAHalf();
    geometrySelection();
    cpuClockIsTwiceTheColourClock();
    geometryIsUsableAtCompileTime();
    return meta::amiga::test::summarise("timing");
}
