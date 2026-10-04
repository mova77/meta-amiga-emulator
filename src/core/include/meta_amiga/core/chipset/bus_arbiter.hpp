// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// Bus arbitration (SPIKE-S0 section 4): who gets a colour clock nobody owns, and when a
// refused device may ask again. The slot allocator answers ownership; this decides the
// rest. Priority is the `Device` enumeration order in scheduler.hpp and is not restated
// here.

#ifndef META_AMIGA_CORE_CHIPSET_BUS_ARBITER_HPP
#define META_AMIGA_CORE_CHIPSET_BUS_ARBITER_HPP

#include <array>
#include <cstddef>

#include "meta_amiga/core/chipset/slot_allocator.hpp"
#include "meta_amiga/core/scheduler.hpp"
#include "meta_amiga/core/types.hpp"

namespace meta::amiga::core::chipset {

// The Blitter's run length, with BLTPRI clear, before it yields a contended free slot to a
// waiting CPU. UNMEASURED AND UNSOURCED: SPIKE-S0 section 4 says the Blitter "yields after a
// bounded run" and states no bound, and none of the sources the project holds (the manual
// extracts S1-S4 in docs/reference/dma-slot-allocation.yaml) gives one. The manual may
// describe it in a part not yet transcribed; that is a lookup for whoever holds it, and
// test 19 waits on it or on a measurement.
//
// 1 is chosen for a property of the code, not of the hardware: it is the smallest run that
// makes the yield path observable, so it cannot be mistaken for a borrowed figure. It is not
// a claim about the machine, and nothing asserts it.
inline constexpr int kBlitterYieldRunUnmeasured = 1;

// The seam SPIKE-S0 section 4.1 asks for. A CPU running off the chipset timeline (a
// 68030/040/060 with fast RAM) is a different implementation of this interface, not a
// change to SlotAllocator. Participants hold a `BusArbiter&` and never name the concrete
// class.
//
// The destructor is protected and non-virtual: nothing owns an arbiter through this
// interface, and a virtual destructor would pull operator delete into the freestanding core
// (ADR-PORT-04 D1) for a deletion that never happens.
class BusArbiter {
public:
    BusArbiter(const BusArbiter&) = delete;
    BusArbiter& operator=(const BusArbiter&) = delete;

    // SPIKE-S0 section 4 `request_bus`. True grants `device` the bus on `cycle`. A refusal
    // leaves the request standing — the device is contending until it is granted or
    // withdraws — and the device retries at `nextSlot`.
    [[nodiscard]] virtual bool requestBus(Device device, Cycle cycle) noexcept = 0;

    // The first cycle after `cycle` on which `device` may ask again.
    [[nodiscard]] virtual Cycle nextSlot(Device device, Cycle cycle) const noexcept = 0;

    // Drop a standing request without being granted, for a device that stops wanting the
    // bus while refused.
    virtual void withdraw(Device device) noexcept = 0;

protected:
    BusArbiter() = default;
    ~BusArbiter() = default;
};

// The device a slot owner fetches for. FREE has none and maps to `Device::Count`.
[[nodiscard]] Device deviceFor(SlotOwner owner) noexcept;

// Arbitration for everything on the chipset timeline: the 68000, and any CPU that shares
// the chip bus synchronously.
//
//   - An owned slot is granted to its owner and refused to everyone else.
//   - A FREE slot is granted unless a higher-priority device is contending it: holding a
//     standing request it is eligible for on this clock, or already granted it. A request
//     on a clock its device may not use is refused and stands too, so a Copper that asks on
//     an odd clock contends the next even one.
//   - The CPU and the Copper are eligible only on even clocks (the 68000's half of the bus,
//     slot_tables.hpp `kCpuOwnsParity`; the Copper's "free even slots", SPIKE-S0 section 4).
//     The Blitter is eligible on every clock.
//   - BLTPRI set: the Blitter's place in `Device` order puts it ahead of the CPU and nothing
//     changes. BLTPRI clear: after `kBlitterYieldRunUnmeasured` consecutive slots won while
//     the CPU waited, the Blitter yields the next one it is eligible for.
//
// Same-cycle requests must arrive in `Device` order. The scheduler's tie-break guarantees
// it for requests made from handlers; a debug build asserts it.
//
// Deterministic (ADR-CORE-01 D6): all state is fixed-size and the outcome is a function
// of the allocator's table and the order of calls, nothing else. No allocation.
class ChipBusArbiter final : public BusArbiter {
public:
    explicit ChipBusArbiter(SlotAllocator& slots) noexcept : slots_(slots) {}

    // The beam's line boundary: rebuilds the slot table for the line starting at `start`
    // and makes it the line requests are resolved against.
    void beginLine(Cycle start, const LineContext& line);

    // DMACON's BLTPRI ("blitter-nasty"), by meaning rather than bit position, as DmaEnables
    // does.
    void setBlitterPriority(bool nasty) noexcept { blitterPriority_ = nasty; }

    [[nodiscard]] bool requestBus(Device device, Cycle cycle) noexcept override;
    [[nodiscard]] Cycle nextSlot(Device device, Cycle cycle) const noexcept override;
    void withdraw(Device device) noexcept override;

    // Whether `device` is holding a refused request.
    [[nodiscard]] bool waiting(Device device) const noexcept {
        return waiting_[static_cast<std::size_t>(device)];
    }

    [[nodiscard]] Cycle lineStart() const noexcept { return lineStart_; }

private:
    [[nodiscard]] int positionOf(Cycle cycle) const noexcept;
    [[nodiscard]] bool higherPriorityContending(Device device, int cck) const noexcept;
    [[nodiscard]] bool blitterYields(int cck) const noexcept;
    bool refuse(Device device) noexcept;
    bool grant(Device device, int cck) noexcept;

    SlotAllocator& slots_;
    Cycle lineStart_ = 0;
    int lineClocks_ = 227;
    bool blitterPriority_ = false;

    std::array<bool, kDeviceCount> waiting_{};

    // The colour clock being arbitrated and what has happened on it so far.
    Cycle cycle_ = kNever;
    Device grantedTo_ = Device::Count;
    Device lastRequester_ = Device::Beam;
    bool blitterYielded_ = false;

    int blitterRun_ = 0;  // consecutive slots the Blitter won while the CPU waited
};

}  // namespace meta::amiga::core::chipset

#endif  // META_AMIGA_CORE_CHIPSET_BUS_ARBITER_HPP
