// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// SPIKE-S0 tests 12, 13 and 15, plus the determinism and feeding-input obligations.
//
// These assert the MANUAL, not the machine. Every expected value comes from
// docs/reference/dma-slot-allocation.yaml, transcribed from the Hardware Reference Manual
// and never measured on hardware. A pass means the allocator reproduces the paper.

#include "meta_amiga/core/chipset/slot_allocator.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdlib>
#include <span>

#include "check.hpp"
#include "meta_amiga/core/chipset/slot_tables.hpp"
#include "slot_table_expectations.hpp"

namespace {

namespace chipset = meta::amiga::core::chipset;
namespace tables = meta::amiga::core::chipset::tables;
namespace expect = meta::amiga::test::slot_tables;

using chipset::BitplaneMode;
using chipset::DmaEnables;
using chipset::LineContext;
using chipset::Resolution;
using chipset::SlotAllocator;
using chipset::SlotOwner;

constexpr std::uint8_t kAllSprites = 0xFF;

DmaEnables everything() {
    return DmaEnables{true, true, true, true, {true, true, true, true}};
}

SlotAllocator activeDevices() {
    SlotAllocator a;
    a.setDiskDmaActive(true);
    for (int ch = 0; ch < 4; ++ch) {
        a.setAudioChannelActive(ch, true);
    }
    return a;
}

void normalWindow(SlotAllocator& a, Resolution res) {
    const bool hires = res == Resolution::Hires;
    a.writeDdfstrt(hires ? tables::kHiresDdfstrtNormal : tables::kLoresDdfstrtNormal);
    a.writeDdfstop(hires ? tables::kHiresDdfstopNormal : tables::kLoresDdfstopNormal);
}

// --- Test 12: fixed allocations, every DMA enable combination -------------------------

void expectFixed(const SlotAllocator& a, const DmaEnables& e, std::uint8_t sprites) {
    for (const auto cck : tables::kRefreshSlots) {
        CHECK(a.owner(cck) == SlotOwner::Refresh);
    }
    for (const auto cck : tables::kDiskSlots) {
        CHECK(a.owner(cck) == (e.master && e.disk ? SlotOwner::Disk : SlotOwner::Free));
    }
    for (int ch = 0; ch < 4; ++ch) {
        const auto i = static_cast<std::size_t>(ch);
        CHECK(a.owner(tables::kAudioSlots[i]) ==
              (e.master && e.audio[i] ? chipset::audioOwner(ch) : SlotOwner::Free));
    }
    for (int n = 0; n < 8; ++n) {
        const bool on = e.master && e.sprite && ((sprites >> n) & 1U);
        for (const auto cck : tables::kSpriteSlots[static_cast<std::size_t>(n)]) {
            CHECK(a.owner(cck) == (on ? chipset::spriteOwner(n) : SlotOwner::Free));
        }
    }
}

void fixedAllocationsMatchTheTableForEveryEnableCombination() {
    // master, disk, sprite, four audio channels: 2^7 combinations.
    for (unsigned bits = 0; bits < 128; ++bits) {
        const DmaEnables e{(bits & 1U) != 0, false, (bits & 2U) != 0, (bits & 4U) != 0,
                           {(bits & 8U) != 0, (bits & 16U) != 0, (bits & 32U) != 0,
                            (bits & 64U) != 0}};
        for (const std::uint8_t sprites : {std::uint8_t{0}, std::uint8_t{0xA5}, kAllSprites}) {
            SlotAllocator a = activeDevices();
            a.writeDmaEnables(e);
            a.beginLine(LineContext{227, false, sprites});
            expectFixed(a, e, sprites);
        }
    }
}

// An enabled channel with no operation in progress takes no slot (Figure 6-9 footnote).
void enabledButIdleDevicesTakeNoSlot() {
    SlotAllocator a;
    a.writeDmaEnables(everything());
    a.beginLine(LineContext{227, false, 0});
    for (const auto cck : tables::kDiskSlots) {
        CHECK(a.owner(cck) == SlotOwner::Free);
    }
    for (const auto cck : tables::kAudioSlots) {
        CHECK(a.owner(cck) == SlotOwner::Free);
    }
}

// The 68000 owns the even clock (S1, S4), so no fixed allocation may sit on one.
void everyFixedAllocationIsOnTheNonCpuParity() {
    SlotAllocator a = activeDevices();
    a.writeDmaEnables(everything());
    a.beginLine(LineContext{227, false, kAllSprites});
    int claimed = 0;
    for (int cck = 0; cck < 227; ++cck) {
        if (a.owner(cck) != SlotOwner::Free) {
            ++claimed;
            CHECK(cck % 2 != tables::kCpuOwnsParity);
        }
    }
    CHECK_EQ(claimed, expect::kFixedOddSlots - tables::kRefreshSlotsUnplaced);
}

// --- Test 13: bitplane slots per fetch mode and plane count ---------------------------

void bitplaneSlotsMatchThePattern(Resolution res, int planes) {
    const bool hires = res == Resolution::Hires;
    const int group = hires ? tables::kHiresGroupClocks : tables::kLoresGroupClocks;
    const std::span<const std::uint8_t> pattern =
        hires ? std::span<const std::uint8_t>{tables::kHiresPlaneByOffset}
              : std::span<const std::uint8_t>{tables::kLoresPlaneByOffset};
    const int start = hires ? tables::kHiresDdfstrtNormal : tables::kLoresDdfstrtNormal;
    const int words = hires ? tables::kHiresWordsNormal : tables::kLoresWordsNormal;

    SlotAllocator a;
    a.writeDmaEnables(DmaEnables{true, true, false, false, {}});
    a.writeBitplaneMode(BitplaneMode{res, planes});
    normalWindow(a, res);
    a.beginLine(LineContext{227, true, 0});

    for (int cck = 0; cck < 227; ++cck) {
        SlotOwner want = SlotOwner::Free;
        if (cck >= start && cck < start + words * group) {
            const int plane = pattern[static_cast<std::size_t>((cck - start) % group)];
            if (plane != 0 && plane <= planes) {
                want = chipset::bitplaneOwner(plane);
            }
        }
        if (std::find(tables::kRefreshSlots.begin(), tables::kRefreshSlots.end(), cck) !=
            tables::kRefreshSlots.end()) {
            want = SlotOwner::Refresh;
        }
        CHECK(a.owner(cck) == want);
    }
}

void bitplaneSlotsMatchThePatternForEveryPlaneCount() {
    for (int planes = 1; planes <= tables::kLoresMaxPlanes; ++planes) {
        bitplaneSlotsMatchThePattern(Resolution::Lores, planes);
    }
    for (int planes = 1; planes <= tables::kHiresMaxPlanes; ++planes) {
        bitplaneSlotsMatchThePattern(Resolution::Hires, planes);
    }
}

// S1's own arithmetic, which the transcribed pattern was not fitted to: four lores planes
// take 80 cycles, all on the non-CPU parity.
void fourLoresPlanesTakeEightyCyclesOffTheCpuParity() {
    SlotAllocator a;
    a.writeDmaEnables(DmaEnables{true, true, false, false, {}});
    a.writeBitplaneMode(BitplaneMode{Resolution::Lores, 4});
    normalWindow(a, Resolution::Lores);
    a.beginLine(LineContext{227, true, 0});
    int taken = 0;
    for (int cck = 0; cck < 227; ++cck) {
        const SlotOwner o = a.owner(cck);
        if (o >= SlotOwner::Bitplane1) {
            ++taken;
            CHECK(cck % 2 != tables::kCpuOwnsParity);
        }
    }
    CHECK_EQ(taken, 80);
}

// Reference section 5: a fetch starting at the earliest point takes sprites 1-7 and
// leaves sprite 0, audio and disk alone.
void anEarlyFetchTakesSpritesOneToSeven() {
    SlotAllocator a = activeDevices();
    a.writeDmaEnables(everything());
    a.writeBitplaneMode(BitplaneMode{Resolution::Lores, 6});
    a.writeDdfstrt(tables::kEarliestFetch);
    a.writeDdfstop(tables::kLoresDdfstopNormal);
    a.beginLine(LineContext{227, true, kAllSprites});
    for (const auto cck : tables::kSpriteSlots[0]) {
        CHECK(a.owner(cck) == SlotOwner::Sprite0);
    }
    for (std::size_t n = 1; n < 8; ++n) {
        for (const auto cck : tables::kSpriteSlots[n]) {
            CHECK(a.owner(cck) >= SlotOwner::Bitplane1);
        }
    }
    for (const auto cck : tables::kDiskSlots) {
        CHECK(a.owner(cck) == SlotOwner::Disk);
    }
    for (int ch = 0; ch < 4; ++ch) {
        CHECK(a.owner(tables::kAudioSlots[static_cast<std::size_t>(ch)]) ==
              chipset::audioOwner(ch));
    }
}

void noBitplaneSlotsOutsideTheDisplayWindowOrWithBitplaneDmaOff() {
    SlotAllocator a;
    a.writeDmaEnables(DmaEnables{true, true, false, false, {}});
    a.writeBitplaneMode(BitplaneMode{Resolution::Lores, 6});
    normalWindow(a, Resolution::Lores);
    a.beginLine(LineContext{227, false, 0});
    CHECK(std::none_of(a.table().begin(), a.table().end(),
                       [](SlotOwner o) { return o >= SlotOwner::Bitplane1; }));

    a.writeDmaEnables(DmaEnables{true, false, false, false, {}});
    a.beginLine(LineContext{227, true, 0});
    CHECK(std::none_of(a.table().begin(), a.table().end(),
                       [](SlotOwner o) { return o >= SlotOwner::Bitplane1; }));
}

// --- The predicted CPU-slot column (reference section 7) ------------------------------

SlotAllocator predictedLine(expect::Mode mode, int planes) {
    SlotAllocator a = activeDevices();
    DmaEnables e = everything();
    e.bitplane = mode != expect::Mode::Off;
    a.writeDmaEnables(e);
    const Resolution res = mode == expect::Mode::Hires ? Resolution::Hires : Resolution::Lores;
    a.writeBitplaneMode(BitplaneMode{res, planes});
    normalWindow(a, res);
    a.beginLine(LineContext{expect::kPalClocks, true, kAllSprites});
    return a;
}

int freeOnParity(const SlotAllocator& a, int parity) {
    int n = 0;
    for (int cck = parity; cck < expect::kPalClocks; cck += 2) {
        n += a.owner(cck) == SlotOwner::Free ? 1 : 0;
    }
    return n;
}

// The even column is exact: the unplaced refresh slot is on the odd parity.
void evenClocksLeftToTheCpuMatchThePrediction() {
    for (const auto& row : expect::kEvenLeftToCpu) {
        CHECK_EQ(freeOnParity(predictedLine(row.mode, row.planes), 0), row.value);
    }
}

void oddClocksFreeMatchThePredictionWithinItsStatedUncertainty() {
    for (const auto& row : expect::kOddFreeAllDmaEnabled) {
        const int got = freeOnParity(predictedLine(row.mode, row.planes), 1);
        CHECK(std::abs(got - row.value) <= expect::kUncertainty);
    }
}

// --- Test 15: writes mark dirty; N writes before the line boundary cost one rebuild ---

void aCopperBurstOfEightWritesCostsOneRebuild() {
    SlotAllocator a;
    const LineContext line{227, true, 0};
    a.beginLine(line);
    const auto before = a.rebuildCount();
    const auto snapshot = a.table();

    a.writeDmaEnables(everything());
    a.writeDdfstrt(tables::kLoresDdfstrtNormal);
    a.writeDdfstop(tables::kLoresDdfstopNormal);
    a.writeBitplaneMode(BitplaneMode{Resolution::Lores, 4});
    a.writeSpritePosition(0);
    a.writeAudioPeriod(2);
    a.setAudioChannelActive(1, true);
    a.setDiskDmaActive(true);

    CHECK(a.dirty());
    CHECK_EQ(a.rebuildCount(), before);
    CHECK(a.table() == snapshot);

    a.beginLine(line);
    CHECK(!a.dirty());
    CHECK_EQ(a.rebuildCount(), before + 1);
}

void aCleanLineWithTheSameContextDoesNotRebuild() {
    SlotAllocator a;
    const LineContext line{227, true, 0x0F};
    a.beginLine(line);
    const auto before = a.rebuildCount();
    a.beginLine(line);
    a.beginLine(line);
    CHECK_EQ(a.rebuildCount(), before);

    a.beginLine(LineContext{227, false, 0x0F});
    CHECK_EQ(a.rebuildCount(), before + 1);
}

// --- Determinism (ADR-CORE-01 D6) ------------------------------------------------------

void identicalStateGivesAnIdenticalTableWhateverTheWriteHistory() {
    SlotAllocator direct = activeDevices();
    direct.writeDmaEnables(everything());
    direct.writeBitplaneMode(BitplaneMode{Resolution::Hires, 3});
    normalWindow(direct, Resolution::Hires);
    direct.beginLine(LineContext{227, true, 0x3C});

    SlotAllocator winding;
    winding.writeBitplaneMode(BitplaneMode{Resolution::Lores, 6});
    winding.writeDdfstop(0x20);
    winding.beginLine(LineContext{228, false, 0});
    winding.setDiskDmaActive(true);
    for (int ch = 3; ch >= 0; --ch) {
        winding.setAudioChannelActive(ch, true);
        winding.writeAudioPeriod(ch);
    }
    normalWindow(winding, Resolution::Hires);
    winding.writeDmaEnables(DmaEnables{});
    winding.writeDmaEnables(everything());
    winding.writeBitplaneMode(BitplaneMode{Resolution::Hires, 3});
    winding.beginLine(LineContext{227, true, 0x3C});

    CHECK(direct.table() == winding.table());
}

// --- ADR-ACCEL-07 D4: the feeding inputs are queryable data ----------------------------

void theFeedingInputSetIsCompleteAndDistinct() {
    auto inputs = chipset::kFeedingInputs;
    std::sort(inputs.begin(), inputs.end());
    CHECK(std::adjacent_find(inputs.begin(), inputs.end()) == inputs.end());
    CHECK_EQ(static_cast<int>(inputs.back()) + 1, static_cast<int>(inputs.size()));
}

void theTablesAreMarkedUnverified() {
    CHECK(!tables::kHardwareVerified);
}

}  // namespace

int main() {
    fixedAllocationsMatchTheTableForEveryEnableCombination();
    enabledButIdleDevicesTakeNoSlot();
    everyFixedAllocationIsOnTheNonCpuParity();
    bitplaneSlotsMatchThePatternForEveryPlaneCount();
    fourLoresPlanesTakeEightyCyclesOffTheCpuParity();
    anEarlyFetchTakesSpritesOneToSeven();
    noBitplaneSlotsOutsideTheDisplayWindowOrWithBitplaneDmaOff();
    evenClocksLeftToTheCpuMatchThePrediction();
    oddClocksFreeMatchThePredictionWithinItsStatedUncertainty();
    aCopperBurstOfEightWritesCostsOneRebuild();
    aCleanLineWithTheSameContextDoesNotRebuild();
    identicalStateGivesAnIdenticalTableWhateverTheWriteHistory();
    theFeedingInputSetIsCompleteAndDistinct();
    theTablesAreMarkedUnverified();
    return meta::amiga::test::summarise("slot_allocator");
}
