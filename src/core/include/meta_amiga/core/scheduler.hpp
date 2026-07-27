// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// The single colour-clock timeline every subsystem is scheduled on (ADR-CORE-01 D1).

#ifndef META_AMIGA_CORE_SCHEDULER_HPP
#define META_AMIGA_CORE_SCHEDULER_HPP

#include <array>
#include <cstddef>

#include "meta_amiga/core/types.hpp"

namespace meta::amiga::core {

/// Everything that can be scheduled on the timeline.
///
/// **The order of this enumeration is the tie-break order**, and it is deliberate: when
/// two devices are due on the same colour clock, the one declared first runs first. It
/// mirrors the hardware's DMA slot priority — refresh and disk before audio, audio before
/// sprites, sprites before bitplanes, Copper and Blitter over what remains, and the CPU
/// last. Reordering these enumerators changes emulated behaviour and is a
/// specification-level change, not a tidy-up.
enum class Device : u8 {
    Beam,      ///< Agnus: end-of-line and end-of-frame boundaries, slot table rebuild.
    Refresh,   ///< Memory refresh — claims its slots unconditionally.
    Disk,      ///< Paula floppy DMA.
    Audio0,
    Audio1,
    Audio2,
    Audio3,
    Sprites,   ///< Agnus sprite fetch.
    Bitplanes, ///< Agnus bitplane fetch.
    Copper,
    Blitter,
    CiaA,
    CiaB,
    Cpu,       ///< Lowest priority, as on the hardware.

    Count
};

inline constexpr std::size_t kDeviceCount = static_cast<std::size_t>(Device::Count);

/// Deterministic, allocation-free event scheduler.
///
/// Each device has at most one pending event, which is the shape the hardware actually
/// has: a device is always waiting for exactly one next thing to happen to it. That gives
/// a fixed-size table instead of a heap — no allocation after construction (ADR-PORT-04
/// D1), no ordering that depends on insertion history, and a linear scan over fourteen
/// entries that beats a priority queue at this size.
///
/// Determinism (ADR-CORE-01 D6) rests on two properties: the table is fixed-size and
/// fully ordered, and ties break by `Device` order rather than by anything
/// history-dependent. Given the same schedule calls, the dispatch sequence is identical
/// on every platform and in every build configuration.
class Scheduler {
public:
    /// A device's event callback. `now` is the cycle the event is being dispatched at,
    /// which is exactly the cycle it was scheduled for — never later.
    using Handler = void (*)(void* context, Cycle now) noexcept;

    Scheduler() noexcept;

    Scheduler(const Scheduler&) = delete;
    Scheduler& operator=(const Scheduler&) = delete;

    /// Current position on the timeline, in colour clocks since reset.
    [[nodiscard]] Cycle now() const noexcept { return now_; }

    /// Attach a device's handler. A device with no handler bound may still be scheduled;
    /// its events are dispatched as no-ops, which keeps partially-built configurations
    /// runnable during bring-up.
    void bind(Device device, Handler handler, void* context) noexcept;

    /// Schedule `device`'s next event at an absolute cycle. Replaces any event already
    /// pending for that device — a device has one future, not a queue of them.
    ///
    /// Scheduling in the past is a programming error; in a debug build it asserts, and in
    /// a release build the event is clamped to the current cycle so that a bug degrades
    /// into a visible timing artefact rather than into a silent hang.
    void scheduleAt(Device device, Cycle at) noexcept;

    /// Schedule `device`'s next event `delta` colour clocks from now.
    void scheduleIn(Device device, Cycle delta) noexcept { scheduleAt(device, now_ + delta); }

    /// Withdraw a device's pending event, if any.
    void cancel(Device device) noexcept;

    [[nodiscard]] bool pending(Device device) const noexcept {
        return due_[static_cast<std::size_t>(device)] != kNever;
    }

    /// The cycle a device is next due at, or `kNever`.
    [[nodiscard]] Cycle dueAt(Device device) const noexcept {
        return due_[static_cast<std::size_t>(device)];
    }

    /// The earliest pending event across all devices, or `kNever` when idle.
    [[nodiscard]] Cycle nextDue() const noexcept;

    /// Advance to `deadline`, dispatching every event due at or before it in cycle order,
    /// ties broken by `Device` order.
    ///
    /// A handler may schedule further events, including for itself; a handler's own
    /// pending slot is cleared before it is called, so rescheduling from inside a handler
    /// is the normal way a periodic device works. An event scheduled *at the current
    /// cycle* is dispatched before the timeline advances, which models same-cycle
    /// chaining but will not terminate if a handler does it unconditionally.
    ///
    /// On return, `now()` is exactly `deadline`. Calling with a deadline in the past is a
    /// no-op.
    void runUntil(Cycle deadline) noexcept;

private:
    struct Slot {
        Handler handler = nullptr;
        void* context = nullptr;
    };

    Cycle now_ = 0;
    std::array<Cycle, kDeviceCount> due_{};
    std::array<Slot, kDeviceCount> slots_{};
};

}  // namespace meta::amiga::core

#endif  // META_AMIGA_CORE_SCHEDULER_HPP
