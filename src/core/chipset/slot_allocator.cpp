// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/chipset/slot_allocator.hpp"

#include "meta_amiga/core/chipset/slot_tables.hpp"

#include <cstddef>
#include <span>

namespace meta::amiga::core::chipset {

SlotAllocator::SlotAllocator() {
    table_.fill(SlotOwner::Free);
}

void SlotAllocator::writeDmaEnables(const DmaEnables& enables) {
    dma_ = enables;
    dirty_ = true;
}

void SlotAllocator::writeDdfstrt(int value) {
    ddfstrt_ = value;
    dirty_ = true;
}

void SlotAllocator::writeDdfstop(int value) {
    ddfstop_ = value;
    dirty_ = true;
}

void SlotAllocator::writeBitplaneMode(const BitplaneMode& mode) {
    bitplanes_ = mode;
    dirty_ = true;
}

void SlotAllocator::writeSpritePosition(int) {
    dirty_ = true;
}

void SlotAllocator::writeAudioPeriod(int) {
    dirty_ = true;
}

void SlotAllocator::setAudioChannelActive(int channel, bool active) {
    audioActive_[static_cast<std::size_t>(channel)] = active;
    dirty_ = true;
}

void SlotAllocator::setDiskDmaActive(bool active) {
    diskActive_ = active;
    dirty_ = true;
}

void SlotAllocator::beginLine(const LineContext& line) {
    if (dirty_ || !(line == line_)) {
        rebuild(line);
    }
}

SlotOwner SlotAllocator::owner(int cck) const {
    if (cck < 0 || cck >= line_.clocks) {
        return SlotOwner::Free;
    }
    return table_[static_cast<std::size_t>(cck)];
}

void SlotAllocator::rebuild(const LineContext& line) {
    table_.fill(SlotOwner::Free);
    placeFixed(line);
    if (dma_.master && dma_.bitplane && line.inDisplayWindow) {
        placeBitplanes(line.clocks);
    }
    line_ = line;
    dirty_ = false;
    ++rebuilds_;
}

void SlotAllocator::claim(int cck, int lineClocks, SlotOwner who) {
    if (cck >= 0 && cck < lineClocks) {
        table_[static_cast<std::size_t>(cck)] = who;
    }
}

// Each fixed slot is claimed only while its device is performing an operation (Figure
// 6-9's footnote). Refresh has no enable and always runs.
void SlotAllocator::placeFixed(const LineContext& line) {
    for (const auto cck : tables::kRefreshSlots) {
        claim(cck, line.clocks, SlotOwner::Refresh);
    }
    if (!dma_.master) {
        return;
    }
    if (dma_.disk && diskActive_) {
        for (const auto cck : tables::kDiskSlots) {
            claim(cck, line.clocks, SlotOwner::Disk);
        }
    }
    for (int ch = 0; ch < 4; ++ch) {
        const auto i = static_cast<std::size_t>(ch);
        if (dma_.audio[i] && audioActive_[i]) {
            claim(tables::kAudioSlots[i], line.clocks, audioOwner(ch));
        }
    }
    if (dma_.sprite) {
        for (int n = 0; n < 8; ++n) {
            if ((line.spritesInWindow >> n) & 1U) {
                for (const auto cck : tables::kSpriteSlots[static_cast<std::size_t>(n)]) {
                    claim(cck, line.clocks, spriteOwner(n));
                }
            }
        }
    }
}

// Word counts follow the manual's DDFSTRT/DDFSTOP relations (reference section 4.3):
// lores DDFSTRT = DDFSTOP - 8 * (words - 1), hires DDFSTRT = DDFSTOP - 4 * (words - 2).
// Bitplane slots overwrite sprite slots, which is how an early fetch start takes sprites
// 1-7 (reference section 5).
//
// UNVERIFIED outside the documented range (reference section 5.1): a stop before the
// start fetches nothing here, a misaligned start is used as written, and the two
// transcribed limits ($18 earliest slot, $D8 last group start) are honoured. Each of
// those is a reading, not a measurement; the out-of-range test is skipped until one exists.
void SlotAllocator::placeBitplanes(int lineClocks) {
    const bool hires = bitplanes_.resolution == Resolution::Hires;
    const int group = hires ? tables::kHiresGroupClocks : tables::kLoresGroupClocks;
    const std::span<const std::uint8_t> pattern =
        hires ? std::span<const std::uint8_t>{tables::kHiresPlaneByOffset}
              : std::span<const std::uint8_t>{tables::kLoresPlaneByOffset};

    if (ddfstop_ < ddfstrt_) {
        return;
    }
    const int words = (ddfstop_ - ddfstrt_) / group + (hires ? 2 : 1);

    for (int w = 0; w < words; ++w) {
        const int base = ddfstrt_ + w * group;
        if (base > tables::kHardwareFetchStop) {
            break;
        }
        for (int offset = 0; offset < group; ++offset) {
            const int plane = pattern[static_cast<std::size_t>(offset)];
            const int cck = base + offset;
            if (plane != 0 && plane <= bitplanes_.planes && cck >= tables::kEarliestFetch) {
                claim(cck, lineClocks, bitplaneOwner(plane));
            }
        }
    }
}

}  // namespace meta::amiga::core::chipset
