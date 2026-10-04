// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/chipset/bus_arbiter.hpp"

#include "meta_amiga/core/chipset/slot_tables.hpp"

#include <cassert>
#include <cstddef>

namespace meta::amiga::core::chipset {

namespace {

constexpr std::size_t index(Device device) noexcept {
    return static_cast<std::size_t>(device);
}

// SPIKE-S0 section 4: the Copper "takes free even slots". The 68000's parity is the
// transcribed one; the Copper's is stated in the spike and happens to be the same.
constexpr int kCopperParity = 0;

constexpr bool eligible(Device device, int cck) noexcept {
    switch (device) {
        case Device::Cpu:
            return cck % 2 == tables::kCpuOwnsParity;
        case Device::Copper:
            return cck % 2 == kCopperParity;
        default:
            return true;
    }
}

}  // namespace

Device deviceFor(SlotOwner owner) noexcept {
    switch (owner) {
        case SlotOwner::Free:
            return Device::Count;
        case SlotOwner::Refresh:
            return Device::Refresh;
        case SlotOwner::Disk:
            return Device::Disk;
        case SlotOwner::Audio0:
            return Device::Audio0;
        case SlotOwner::Audio1:
            return Device::Audio1;
        case SlotOwner::Audio2:
            return Device::Audio2;
        case SlotOwner::Audio3:
            return Device::Audio3;
        case SlotOwner::Sprite0:
        case SlotOwner::Sprite1:
        case SlotOwner::Sprite2:
        case SlotOwner::Sprite3:
        case SlotOwner::Sprite4:
        case SlotOwner::Sprite5:
        case SlotOwner::Sprite6:
        case SlotOwner::Sprite7:
            return Device::Sprites;
        case SlotOwner::Bitplane1:
        case SlotOwner::Bitplane2:
        case SlotOwner::Bitplane3:
        case SlotOwner::Bitplane4:
        case SlotOwner::Bitplane5:
        case SlotOwner::Bitplane6:
            return Device::Bitplanes;
    }
    return Device::Count;
}

void ChipBusArbiter::beginLine(Cycle start, const LineContext& line) {
    slots_.beginLine(line);
    lineStart_ = start;
    lineClocks_ = line.clocks;
}

int ChipBusArbiter::positionOf(Cycle cycle) const noexcept {
    assert(cycle >= lineStart_ && cycle - lineStart_ < static_cast<Cycle>(lineClocks_) &&
           "bus request outside the current line");
    return static_cast<int>(cycle - lineStart_);
}

bool ChipBusArbiter::higherPriorityContending(Device device, int cck) const noexcept {
    if (grantedTo_ != Device::Count) {
        return true;
    }
    for (std::size_t i = 0; i < index(device); ++i) {
        const auto other = static_cast<Device>(i);
        if (!waiting_[i] || !eligible(other, cck)) {
            continue;
        }
        if (other == Device::Blitter && blitterYielded_) {
            continue;
        }
        return true;
    }
    return false;
}

bool ChipBusArbiter::blitterYields(int cck) const noexcept {
    return !blitterPriority_ && waiting_[index(Device::Cpu)] && eligible(Device::Cpu, cck) &&
           blitterRun_ >= kBlitterYieldRunUnmeasured;
}

bool ChipBusArbiter::refuse(Device device) noexcept {
    waiting_[index(device)] = true;
    return false;
}

bool ChipBusArbiter::grant(Device device, int cck) noexcept {
    if (device == Device::Blitter) {
        if (waiting_[index(Device::Cpu)] && eligible(Device::Cpu, cck)) {
            ++blitterRun_;
        }
    } else if (device == Device::Cpu) {
        blitterRun_ = 0;
    }
    waiting_[index(device)] = false;
    grantedTo_ = device;
    return true;
}

bool ChipBusArbiter::requestBus(Device device, Cycle cycle) noexcept {
    if (cycle != cycle_) {
        cycle_ = cycle;
        grantedTo_ = Device::Count;
        lastRequester_ = Device::Beam;
        blitterYielded_ = false;
    }
    assert(index(device) >= index(lastRequester_) &&
           "same-cycle bus requests must arrive in Device order");
    lastRequester_ = device;

    const int cck = positionOf(cycle);
    if (!eligible(device, cck)) {
        return refuse(device);
    }

    const SlotOwner owner = slots_.owner(cck);
    if (owner != SlotOwner::Free) {
        return deviceFor(owner) == device ? grant(device, cck) : refuse(device);
    }

    if (higherPriorityContending(device, cck)) {
        return refuse(device);
    }
    if (device == Device::Blitter && blitterYields(cck)) {
        blitterYielded_ = true;
        return refuse(device);
    }
    return grant(device, cck);
}

Cycle ChipBusArbiter::nextSlot(Device device, Cycle cycle) const noexcept {
    // The next line is assumed to be as long as this one. Only parity depends on that, and
    // clock 0 of the next line is even whichever length it has, so a mismatch cannot move
    // the answer.
    Cycle next = cycle + 1;
    if (device != Device::Cpu && device != Device::Copper) {
        return next;
    }
    Cycle cck = next - lineStart_;
    if (cck >= static_cast<Cycle>(lineClocks_)) {
        cck -= static_cast<Cycle>(lineClocks_);
    }
    if (!eligible(device, static_cast<int>(cck % 2U))) {
        ++next;
    }
    return next;
}

void ChipBusArbiter::withdraw(Device device) noexcept {
    waiting_[index(device)] = false;
    if (device == Device::Cpu) {
        blitterRun_ = 0;
    }
}

}  // namespace meta::amiga::core::chipset
