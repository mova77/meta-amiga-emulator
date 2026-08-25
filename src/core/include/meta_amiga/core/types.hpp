// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#ifndef META_AMIGA_CORE_TYPES_HPP
#define META_AMIGA_CORE_TYPES_HPP

#include <cstdint>

namespace meta::amiga::core {

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using i8 = std::int8_t;
using i16 = std::int16_t;
using i32 = std::int32_t;
using i64 = std::int64_t;

/// Colour clocks elapsed since reset. This is the only notion of time in the core
/// (ADR-CORE-01 D1): every subsystem advances by being scheduled against it.
///
/// A `u64` at the PAL colour-clock rate wraps after roughly 165 000 years of emulated
/// time, so wraparound is not a case the core handles.
using Cycle = u64;

/// A cycle value that will never be reached — used to mean "no event pending".
inline constexpr Cycle kNever = static_cast<Cycle>(-1);

/// Amiga chip-bus address. The 68000 drives 24 address lines; wider CPUs are handled by
/// the memory map, not by this type.
using Address = u32;

}  // namespace meta::amiga::core

#endif  // META_AMIGA_CORE_TYPES_HPP
