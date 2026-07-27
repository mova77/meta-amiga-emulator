// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// Beam geometry and clock constants. See specification §3 and ADR-CORE-01.

#ifndef META_AMIGA_CORE_TIMING_HPP
#define META_AMIGA_CORE_TIMING_HPP

#include "meta_amiga/core/types.hpp"

namespace meta::amiga::core {

/// Colour clock frequencies. The 68000 runs at exactly twice the colour clock, which is
/// why the colour clock — not the CPU clock — is the project's unit of time.
inline constexpr u32 kPalColourClockHz = 3'546'895;
inline constexpr u32 kNtscColourClockHz = 3'579'545;

enum class VideoStandard : u8 { Pal, Ntsc };

/// Raster geometry in colour clocks.
///
/// PAL is exact and fully relied upon: 227 colour clocks on every line, 312 lines in a
/// short frame and 313 in a long (interlace) frame.
///
/// NTSC averages 227.5 colour clocks per line by alternating 227 and 228. The *phase* of
/// that alternation — which line carries the extra clock — is recorded here as a
/// hypothesis and must be confirmed against hardware before the display subsystem relies
/// on it; it is an open question on ADR-CORE-01. Nothing outside this header currently
/// depends on it.
struct BeamGeometry {
    u32 ccksPerLine;      ///< Base colour clocks per scanline.
    bool longLinesAlternate;  ///< NTSC: odd lines carry one extra colour clock.
    u32 shortFrameLines;  ///< Lines in a non-interlaced (short) frame.
    u32 longFrameLines;   ///< Lines in a long frame.

    [[nodiscard]] constexpr u32 ccksInLine(u32 line) const noexcept {
        return ccksPerLine + ((longLinesAlternate && (line % 2U) == 1U) ? 1U : 0U);
    }

    [[nodiscard]] constexpr u32 linesInFrame(bool longFrame) const noexcept {
        return longFrame ? longFrameLines : shortFrameLines;
    }

    [[nodiscard]] constexpr Cycle ccksInFrame(bool longFrame) const noexcept {
        const u32 lines = linesInFrame(longFrame);
        Cycle total = 0;
        for (u32 line = 0; line < lines; ++line) {
            total += ccksInLine(line);
        }
        return total;
    }
};

inline constexpr BeamGeometry kPalGeometry{
    .ccksPerLine = 227, .longLinesAlternate = false, .shortFrameLines = 312, .longFrameLines = 313};

inline constexpr BeamGeometry kNtscGeometry{
    .ccksPerLine = 227, .longLinesAlternate = true, .shortFrameLines = 262, .longFrameLines = 263};

[[nodiscard]] constexpr BeamGeometry geometryFor(VideoStandard standard) noexcept {
    return standard == VideoStandard::Pal ? kPalGeometry : kNtscGeometry;
}

[[nodiscard]] constexpr u32 colourClockHz(VideoStandard standard) noexcept {
    return standard == VideoStandard::Pal ? kPalColourClockHz : kNtscColourClockHz;
}

/// Position of the video beam, in whole colour clocks from the start of the line.
struct BeamPosition {
    u32 line;
    u32 cck;

    friend constexpr bool operator==(const BeamPosition&, const BeamPosition&) = default;
};

}  // namespace meta::amiga::core

#endif  // META_AMIGA_CORE_TIMING_HPP
