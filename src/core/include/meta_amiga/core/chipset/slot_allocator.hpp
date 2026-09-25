// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// Per-line DMA slot allocator (SPIKE-S0 section 3.1). It answers who owns each colour
// clock of the current line; it does not decide who wins a FREE slot, which is bus
// arbitration (SPIKE-S0 section 4). It holds no slot indices of its own: every position
// comes from slot_tables.hpp, generated from docs/reference/dma-slot-allocation.yaml.

#ifndef META_AMIGA_CORE_CHIPSET_SLOT_ALLOCATOR_HPP
#define META_AMIGA_CORE_CHIPSET_SLOT_ALLOCATOR_HPP

#include <array>
#include <cstdint>

namespace meta::amiga::core::chipset {

// The longest supported line: NTSC long lines alternate 227/228 colour clocks.
inline constexpr int kMaxLineClocks = 228;

enum class SlotOwner : std::uint8_t {
    Free,
    Refresh,
    Disk,
    Audio0, Audio1, Audio2, Audio3,
    Sprite0, Sprite1, Sprite2, Sprite3, Sprite4, Sprite5, Sprite6, Sprite7,
    Bitplane1, Bitplane2, Bitplane3, Bitplane4, Bitplane5, Bitplane6,
};

constexpr SlotOwner audioOwner(int channel) {
    return static_cast<SlotOwner>(static_cast<int>(SlotOwner::Audio0) + channel);
}
constexpr SlotOwner spriteOwner(int sprite) {
    return static_cast<SlotOwner>(static_cast<int>(SlotOwner::Sprite0) + sprite);
}
constexpr SlotOwner bitplaneOwner(int plane) {
    return static_cast<SlotOwner>(static_cast<int>(SlotOwner::Bitplane1) + plane - 1);
}

// Every input the table is a function of. A write to any of them marks the table dirty.
// Exposed as data so a batching bound can be computed against it (ADR-ACCEL-07 D4).
enum class Input : std::uint8_t {
    Dmacon,
    Ddfstrt,
    Ddfstop,
    Bplcon0,
    SpritePosition0, SpritePosition1, SpritePosition2, SpritePosition3,
    SpritePosition4, SpritePosition5, SpritePosition6, SpritePosition7,
    AudioPeriod0, AudioPeriod1, AudioPeriod2, AudioPeriod3,
    AudioChannelState,
    DiskDmaState,
};

inline constexpr std::array<Input, 18> kFeedingInputs{
    Input::Dmacon,          Input::Ddfstrt,         Input::Ddfstop,
    Input::Bplcon0,         Input::SpritePosition0, Input::SpritePosition1,
    Input::SpritePosition2, Input::SpritePosition3, Input::SpritePosition4,
    Input::SpritePosition5, Input::SpritePosition6, Input::SpritePosition7,
    Input::AudioPeriod0,    Input::AudioPeriod1,    Input::AudioPeriod2,
    Input::AudioPeriod3,    Input::AudioChannelState, Input::DiskDmaState,
};

// DMACON's enables, by meaning rather than bit position.
struct DmaEnables {
    bool master = false;
    bool bitplane = false;
    bool sprite = false;
    bool disk = false;
    std::array<bool, 4> audio{};

    friend constexpr bool operator==(const DmaEnables&, const DmaEnables&) = default;
};

enum class Resolution : std::uint8_t { Lores, Hires };

// What BPLCON0 contributes: resolution and bitplane count. OCS/ECS only; AGA fetch modes
// are not transcribed.
struct BitplaneMode {
    Resolution resolution = Resolution::Lores;
    int planes = 0;

    friend constexpr bool operator==(const BitplaneMode&, const BitplaneMode&) = default;
};

// What the beam knows about the line that is starting. Window membership comes from
// registers this allocator does not decode (the display window, each sprite's vertical
// start and stop), so the caller supplies it.
struct LineContext {
    int clocks = 227;
    bool inDisplayWindow = false;
    std::uint8_t spritesInWindow = 0;  // bit n set: sprite n is in its vertical window

    friend constexpr bool operator==(const LineContext&, const LineContext&) = default;
};

class SlotAllocator {
public:
    using Table = std::array<SlotOwner, kMaxLineClocks>;

    SlotAllocator();

    void writeDmaEnables(const DmaEnables& enables);
    void writeDdfstrt(int value);
    void writeDdfstop(int value);
    void writeBitplaneMode(const BitplaneMode& mode);
    void writeSpritePosition(int sprite);
    void writeAudioPeriod(int channel);
    void setAudioChannelActive(int channel, bool active);
    void setDiskDmaActive(bool active);

    // Called at the line boundary. Rebuilds only when an input was written since the last
    // rebuild or the line's context differs from it; writes never rebuild on their own.
    void beginLine(const LineContext& line);

    // Owner of colour clock `cck` in the current line; FREE past the line's end.
    SlotOwner owner(int cck) const;

    const Table& table() const { return table_; }
    bool dirty() const { return dirty_; }
    std::uint64_t rebuildCount() const { return rebuilds_; }

private:
    void rebuild(const LineContext& line);
    void placeFixed(const LineContext& line);
    void placeBitplanes(int lineClocks);
    void claim(int cck, int lineClocks, SlotOwner who);

    Table table_{};
    LineContext line_{};
    DmaEnables dma_{};
    BitplaneMode bitplanes_{};
    int ddfstrt_ = 0;
    int ddfstop_ = 0;
    std::array<bool, 4> audioActive_{};
    bool diskActive_ = false;
    bool dirty_ = true;
    std::uint64_t rebuilds_ = 0;
};

}  // namespace meta::amiga::core::chipset

#endif  // META_AMIGA_CORE_CHIPSET_SLOT_ALLOCATOR_HPP
