// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// SPIKE-S0 section 4, the bus arbitration protocol: tests 17, 18 and 20, emergent CPU
// timing (ADR-CORE-01 D5, ADR-CPU-02 D4), the asynchronous seam of section 4.1, and
// determinism (ADR-CORE-01 D6). Test 19 is in bus_arbiter_unmeasured_test.cpp, skipped.
//
// No CPU, Blitter or Copper exists yet. Each is a test double that does only what
// section 4 says it does, driven by the real Scheduler so that a stall is elapsed colour
// clocks on the timeline rather than a return value. Slot ownership comes from the real
// SlotAllocator, so every expected cycle below rests on the transcribed MANUAL tables,
// not on hardware measurement.

#include "meta_amiga/core/chipset/bus_arbiter.hpp"

#include <algorithm>
#include <array>
#include <cstddef>

#include "check.hpp"
#include "meta_amiga/core/chipset/slot_allocator.hpp"
#include "meta_amiga/core/chipset/slot_tables.hpp"
#include "meta_amiga/core/scheduler.hpp"

namespace {

namespace chipset = meta::amiga::core::chipset;
namespace tables = meta::amiga::core::chipset::tables;

using chipset::BitplaneMode;
using chipset::BusArbiter;
using chipset::ChipBusArbiter;
using chipset::DmaEnables;
using chipset::LineContext;
using chipset::Resolution;
using chipset::SlotAllocator;
using chipset::SlotOwner;
using meta::amiga::core::Cycle;
using meta::amiga::core::Device;
using meta::amiga::core::Scheduler;

constexpr Cycle kLine = 227;  // PAL
constexpr LineContext kDisplayLine{.clocks = 227, .inDisplayWindow = true, .spritesInWindow = 0};

struct Log {
    struct Entry {
        Device device;
        Cycle at;
        bool granted;
        friend constexpr bool operator==(const Entry&, const Entry&) = default;
    };
    std::array<Entry, 1024> entries{};
    std::size_t count = 0;

    void record(Device device, Cycle at, bool granted) noexcept {
        if (count < entries.size()) {
            entries[count++] = Entry{device, at, granted};
        }
    }
    bool operator==(const Log& other) const noexcept {
        return count == other.count &&
               std::equal(entries.begin(), entries.begin() + static_cast<std::ptrdiff_t>(count),
                          other.entries.begin());
    }
};

// The machine around the arbiter: a scheduler, the slot table, and Agnus's line boundary
// as a Beam event that rebuilds the table every line.
struct Machine {
    Scheduler scheduler;
    SlotAllocator slots;
    ChipBusArbiter arbiter{slots};
    LineContext line = kDisplayLine;
    Log log;

    Machine() {
        scheduler.bind(Device::Beam, &Machine::beam, this);
        scheduler.scheduleAt(Device::Beam, 0);
    }

    void display(Resolution resolution, int planes) {
        slots.writeDmaEnables(DmaEnables{.master = true, .bitplane = true});
        slots.writeBitplaneMode(BitplaneMode{resolution, planes});
        const bool hires = resolution == Resolution::Hires;
        slots.writeDdfstrt(hires ? tables::kHiresDdfstrtNormal : tables::kLoresDdfstrtNormal);
        slots.writeDdfstop(hires ? tables::kHiresDdfstopNormal : tables::kLoresDdfstopNormal);
    }

    static void beam(void* context, Cycle now) noexcept {
        auto* m = static_cast<Machine*>(context);
        m->arbiter.beginLine(now, m->line);
        m->scheduler.scheduleAt(Device::Beam, now + static_cast<Cycle>(m->line.clocks));
    }
};

// SPIKE-S0 section 4, CPU: request; on refusal stall and retry on the next slot. One bus
// cycle is two colour clocks, so back-to-back accesses ask again two clocks after a grant.
// It holds the interface only, which is what lets the section 4.1 stub stand in below.
struct CpuDouble {
    Scheduler* scheduler;
    BusArbiter* arbiter;
    Log* log;
    int remaining = 0;
    Cycle firstGrant = 0;
    Cycle done = 0;
    int stalls = 0;

    void start(Cycle at, int accesses) {
        remaining = accesses;
        scheduler->bind(Device::Cpu, &CpuDouble::run, this);
        scheduler->scheduleAt(Device::Cpu, at);
    }

    static void run(void* context, Cycle now) noexcept {
        auto* cpu = static_cast<CpuDouble*>(context);
        const bool granted = cpu->arbiter->requestBus(Device::Cpu, now);
        cpu->log->record(Device::Cpu, now, granted);
        if (!granted) {
            ++cpu->stalls;
            cpu->scheduler->scheduleAt(Device::Cpu, cpu->arbiter->nextSlot(Device::Cpu, now));
            return;
        }
        if (cpu->firstGrant == 0) {
            cpu->firstGrant = now;
        }
        if (--cpu->remaining == 0) {
            cpu->done = now + 2;
            return;
        }
        cpu->scheduler->scheduleAt(Device::Cpu, now + 2);
    }
};

// SPIKE-S0 section 4, Blitter: takes free slots, one word per granted clock.
struct BlitterDouble {
    Scheduler* scheduler;
    BusArbiter* arbiter;
    Log* log;
    int remaining = 0;
    Cycle done = 0;

    void start(Cycle at, int words) {
        remaining = words;
        scheduler->bind(Device::Blitter, &BlitterDouble::run, this);
        scheduler->scheduleAt(Device::Blitter, at);
    }

    static void run(void* context, Cycle now) noexcept {
        auto* blitter = static_cast<BlitterDouble*>(context);
        const bool granted = blitter->arbiter->requestBus(Device::Blitter, now);
        blitter->log->record(Device::Blitter, now, granted);
        if (granted && --blitter->remaining == 0) {
            blitter->done = now + 1;
            return;
        }
        blitter->scheduler->scheduleAt(Device::Blitter,
                                       blitter->arbiter->nextSlot(Device::Blitter, now));
    }
};

// SPIKE-S0 section 4, Copper: stalls on WAIT until the beam comparison passes, then takes
// free even slots. The comparison itself is the Copper's, which does not exist: the double
// turns the compared beam position into the cycle it occurs on and sleeps until then.
struct CopperDouble {
    Scheduler* scheduler;
    BusArbiter* arbiter;
    Log* log;
    Cycle released = 0;
    bool fetchEveryClock = false;  // keep asking after each grant, to map every slot it gets

    void wait(Cycle lineStart, Cycle cck) {
        scheduler->bind(Device::Copper, &CopperDouble::run, this);
        scheduler->scheduleAt(Device::Copper, lineStart + cck);
    }

    static void run(void* context, Cycle now) noexcept {
        auto* copper = static_cast<CopperDouble*>(context);
        const bool granted = copper->arbiter->requestBus(Device::Copper, now);
        copper->log->record(Device::Copper, now, granted);
        if (granted && copper->released == 0) {
            copper->released = now;
        }
        if (!granted || copper->fetchEveryClock) {
            copper->scheduler->scheduleAt(Device::Copper,
                                          copper->arbiter->nextSlot(Device::Copper, now));
        }
    }
};

// The slot table's own prediction, independent of the arbiter but NOT of the CPU double:
// walk the table for the colour clock of the `accesses`-th CPU-parity FREE slot from
// `start`, assuming every line has the table of the current one and, like the double, that
// the CPU cannot ask again until one bus cycle (two clocks) after a grant. Returns elapsed
// clocks to the end of that bus cycle.
Cycle predictedCpuElapsed(const SlotAllocator& slots, int start, int accesses) {
    int found = 0;
    for (Cycle t = 0;; ++t) {
        const int cck = static_cast<int>((static_cast<Cycle>(start) + t) % kLine);
        if (cck % 2 == tables::kCpuOwnsParity && slots.owner(cck) == SlotOwner::Free) {
            if (++found == accesses) {
                return t + 2;
            }
            t += 1;  // the CPU's own cadence: next request two clocks after a grant
        }
    }
}

// --- SPIKE-S0 section 4, request_bus ------------------------------------------------------

void ownedSlotsGoToTheirOwnerOnly() {
    Machine m;
    m.display(Resolution::Hires, 4);
    m.scheduler.runUntil(1);  // Beam has run line 0

    // $01 is refresh's (fixed, odd); $3C is plane 4's in the hires group, and even.
    CHECK(m.arbiter.requestBus(Device::Refresh, 0x01));
    CHECK(!m.arbiter.requestBus(Device::Blitter, 0x01));
    CHECK(m.arbiter.requestBus(Device::Bitplanes, 0x3C));
    CHECK(!m.arbiter.requestBus(Device::Copper, 0x3C));
    CHECK(!m.arbiter.requestBus(Device::Blitter, 0x3C));
    CHECK(!m.arbiter.requestBus(Device::Cpu, 0x3C));
    CHECK(m.arbiter.waiting(Device::Cpu));

    // Refused requests stand. With the Copper's and the Blitter's withdrawn, the waiting CPU
    // is the only contender for $DC, which is past the fetch window and free.
    CHECK(m.arbiter.waiting(Device::Copper));
    m.arbiter.withdraw(Device::Copper);
    m.arbiter.withdraw(Device::Blitter);
    CHECK(m.arbiter.requestBus(Device::Cpu, 0xDC));
    CHECK(!m.arbiter.waiting(Device::Cpu));
}

void aFreeSlotGoesToTheHighestPriorityContender() {
    Machine m;
    m.scheduler.runUntil(1);

    // Same clock, Device order: the Copper is ahead of the CPU.
    CHECK(m.arbiter.requestBus(Device::Copper, 0x40));
    CHECK(!m.arbiter.requestBus(Device::Cpu, 0x40));

    // A standing Copper request contends even slots it is not asking for this clock...
    CHECK(!m.arbiter.requestBus(Device::Copper, 0x41));  // odd: ineligible, now waiting
    CHECK(!m.arbiter.requestBus(Device::Cpu, 0x42));
    // ...but not odd ones, where it may not fetch, so the Blitter below it gets those.
    CHECK(m.arbiter.requestBus(Device::Blitter, 0x43));
    // The Copper withdraws and the CPU is the highest contender left.
    m.arbiter.withdraw(Device::Copper);
    CHECK(m.arbiter.requestBus(Device::Cpu, 0x44));
}

// --- SPIKE-S0 test 17 ---------------------------------------------------------------------

void aRefusedCpuStallsOnTheTimeline() {
    Machine m;
    m.display(Resolution::Hires, 4);  // every clock $3C..$DB is a bitplane fetch
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    cpu.start(0x3C, 1);
    m.scheduler.runUntil(kLine - 1);

    // Refused at every even clock $3C..$DA (80 of them), granted at the first free one.
    CHECK_EQ(cpu.stalls, 80);
    CHECK_EQ(cpu.firstGrant, Cycle{0xDC});
    CHECK_EQ(m.log.entries[0].at, Cycle{0x3C});
    CHECK(!m.log.entries[0].granted);
    CHECK_EQ(m.log.entries[1].at, Cycle{0x3E});  // retried on the next CPU slot, not $3D
}

// --- SPIKE-S0 test 18 ---------------------------------------------------------------------

void bltpriPutsTheBlitterAheadOfTheCpu() {
    Machine m;  // no display: every slot from $40 on is FREE
    m.arbiter.setBlitterPriority(true);
    BlitterDouble blitter{&m.scheduler, &m.arbiter, &m.log};
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    blitter.start(0x40, 40);
    cpu.start(0x40, 1);
    m.scheduler.runUntil(kLine - 1);

    // The Blitter takes all 40 clocks $40..$67 back to back; the CPU, contending each even
    // one, gets the first even clock after it finishes.
    CHECK_EQ(blitter.done, Cycle{0x68});
    CHECK_EQ(cpu.stalls, 20);
    CHECK_EQ(cpu.firstGrant, Cycle{0x68});
}

// The placeholder BLTPRI-clear path is exercised, not asserted: the CPU is not locked out
// of a long blit. When it gets in is the unmeasured bound, which test 19 owns.
void bltpriClearDoesNotLockTheCpuOut() {
    Machine m;
    BlitterDouble blitter{&m.scheduler, &m.arbiter, &m.log};
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    blitter.start(0x40, 40);
    cpu.start(0x40, 1);
    m.scheduler.runUntil(kLine - 1);

    CHECK(cpu.firstGrant != 0);
    CHECK(cpu.firstGrant < blitter.done - 1);
}

// The shape of the BLTPRI-clear path, still without asserting the bound: through a long
// blit the CPU gets in repeatedly, and every wait (request to grant) equals the first,
// whatever the bound is. A run that did not restart after each CPU grant would let later
// requests in sooner than the first.
void bltpriClearYieldsRepeatedlyAtASteadyInterval() {
    Machine m;
    BlitterDouble blitter{&m.scheduler, &m.arbiter, &m.log};
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    blitter.start(0x40, 80);
    cpu.start(0x40, 6);
    m.scheduler.runUntil(kLine - 1);

    std::array<Cycle, 6> grants{};
    std::size_t n = 0;
    for (std::size_t i = 0; i < m.log.count && n < grants.size(); ++i) {
        const auto& e = m.log.entries[i];
        if (e.device == Device::Cpu && e.granted) {
            grants[n++] = e.at;
        }
    }
    CHECK_EQ(n, grants.size());
    CHECK(blitter.done != 0);
    CHECK(grants[n - 1] < blitter.done);  // every CPU grant came during the blit
    const Cycle firstWait = grants[0] - 0x40;
    CHECK(firstWait > 0);
    for (std::size_t i = 1; i < n; ++i) {
        CHECK_EQ(grants[i] - (grants[i - 1] + 2), firstWait);  // asked two clocks after
    }
}

// --- SPIKE-S0 test 20 ---------------------------------------------------------------------

// The arbiter's half of test 20: once the compared position is reached, the first free even
// clock at or after it is granted — the position itself when that clock is even and free.

void copperWaitReleasesAtTheComparedPosition() {
    {
        Machine m;
        CopperDouble copper{&m.scheduler, &m.arbiter, &m.log};
        copper.wait(2 * kLine, 0x40);  // WAIT for line 2, clock $40: even and free
        m.scheduler.runUntil(3 * kLine);
        CHECK_EQ(copper.released, 2 * kLine + 0x40);
        CHECK_EQ(m.log.count, std::size_t{1});  // no early request: it slept until then
    }
    {
        Machine m;  // compared position odd: the comparison passes, the bus waits a clock
        CopperDouble copper{&m.scheduler, &m.arbiter, &m.log};
        copper.wait(2 * kLine, 0x41);
        m.scheduler.runUntil(3 * kLine);
        CHECK_EQ(copper.released, 2 * kLine + 0x42);
    }
    {
        Machine m;  // compared position inside a hires fetch: first free even slot after
        m.display(Resolution::Hires, 4);
        CopperDouble copper{&m.scheduler, &m.arbiter, &m.log};
        copper.wait(2 * kLine, 0x40);
        m.scheduler.runUntil(3 * kLine);
        CHECK_EQ(copper.released, 2 * kLine + 0xDC);
    }
}

void copperTakesOnlyFreeEvenSlots() {
    Machine m;
    m.line.spritesInWindow = 0xFF;
    m.slots.writeDmaEnables(DmaEnables{true, true, true, true, {true, true, true, true}});
    m.slots.setDiskDmaActive(true);
    for (int ch = 0; ch < 4; ++ch) {
        m.slots.setAudioChannelActive(ch, true);
    }
    m.slots.writeBitplaneMode(BitplaneMode{Resolution::Lores, 6});
    m.slots.writeDdfstrt(tables::kLoresDdfstrtNormal);
    m.slots.writeDdfstop(tables::kLoresDdfstopNormal);

    CopperDouble copper{&m.scheduler, &m.arbiter, &m.log};
    copper.fetchEveryClock = true;
    copper.wait(0, 0);
    m.scheduler.runUntil(kLine - 1);

    int freeEven = 0;
    for (int cck = 0; cck < static_cast<int>(kLine); cck += 2) {
        freeEven += m.slots.owner(cck) == SlotOwner::Free ? 1 : 0;
    }
    int granted = 0;
    for (std::size_t i = 0; i < m.log.count; ++i) {
        const auto& e = m.log.entries[i];
        CHECK(e.at % 2 == 0);  // never even asks on an odd clock
        if (e.granted) {
            ++granted;
            CHECK(m.slots.owner(static_cast<int>(e.at)) == SlotOwner::Free);
        }
    }
    CHECK_EQ(granted, freeEven);
    CHECK(freeEven < static_cast<int>(kLine + 1) / 2);  // planes 5 and 6 took some
}

// --- ADR-CORE-01 D5: CPU timing emerges from the slot table --------------------------------

// The same 40 back-to-back bus cycles from $38, under three display modes. Nothing in the
// CPU double knows the mode; the difference is the table's. (The transcribed hires table
// has four planes at most, so "starved in hires" is shown with four.)
Cycle cpuElapsed(Resolution resolution, int planes, Cycle* predicted) {
    Machine m;
    m.display(resolution, planes);
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    cpu.start(0x38, 40);
    m.scheduler.runUntil(3 * kLine);
    *predicted = predictedCpuElapsed(m.slots, 0x38, 40);
    return cpu.done - 0x38;
}

void cpuTimingEmergesFromTheDisplayMode() {
    Cycle predicted = 0;
    // No planes: every even clock is free. 40 cycles = 80 clocks.
    CHECK_EQ(cpuElapsed(Resolution::Lores, 0, &predicted), Cycle{80});
    CHECK_EQ(predicted, Cycle{80});

    // Six lores planes: 5 and 6 take offsets 2 and 6 of each 8-clock group from $38, the
    // CPU keeps 0 and 4 — two cycles a group. 40 cycles = 20 groups; the last is at group
    // 19 offset 4 = $D4 and ends at $D6, 158 clocks after $38. 78 clocks slower.
    CHECK_EQ(cpuElapsed(Resolution::Lores, 6, &predicted), Cycle{158});
    CHECK_EQ(predicted, Cycle{158});

    // Four hires planes: $3C..$DB is all fetch. The CPU gets $38 and $3A, then $DC..$E2
    // (4). After the grant at $E2, the line's last clock, the double asks again two clocks
    // later, at the next line's odd $01, and gets $02, so that line gives $02..$3A (29),
    // then $DC..$E2 (4) again: 39. The 40th is at $02 of the line after, ending at $04:
    // 2 * 227 + $04 - $38 = 402 clocks. The line-end step is the double's cadence, not the
    // arbiter's (docs/architecture/scheduler.md section 4 item 7), and rests on the
    // unverified 227-clock PAL line.
    CHECK_EQ(cpuElapsed(Resolution::Hires, 4, &predicted), Cycle{402});
    CHECK_EQ(predicted, Cycle{402});
}

// --- SPIKE-S0 section 4.1: a second implementation, no allocator --------------------------

// What an asynchronous CPU's arbiter could be: it never consults the chip slot table. It
// exists to prove the seam compiles and runs; it is not a model of anything.
class AsyncCpuStub final : public BusArbiter {
public:
    bool requestBus(Device, Cycle) noexcept override { return true; }
    Cycle nextSlot(Device, Cycle cycle) const noexcept override { return cycle + 1; }
    void withdraw(Device) noexcept override {}
};

void anAsynchronousArbiterNeedsNoAllocator() {
    Machine m;
    m.display(Resolution::Hires, 4);  // would starve a chip-bus CPU, as above
    AsyncCpuStub async;
    CpuDouble cpu{&m.scheduler, &async, &m.log};
    cpu.start(0x38, 40);
    m.scheduler.runUntil(kLine);
    CHECK_EQ(cpu.done - 0x38, Cycle{80});
    CHECK_EQ(cpu.stalls, 0);
}

// --- ADR-CORE-01 D6 ------------------------------------------------------------------------

Log contendedRun() {
    Machine m;
    m.display(Resolution::Lores, 6);
    BlitterDouble blitter{&m.scheduler, &m.arbiter, &m.log};
    CpuDouble cpu{&m.scheduler, &m.arbiter, &m.log};
    CopperDouble copper{&m.scheduler, &m.arbiter, &m.log};
    blitter.start(0x30, 60);
    cpu.start(0x31, 30);
    copper.wait(0, 0x50);
    m.scheduler.runUntil(2 * kLine);
    return m.log;
}

void identicalRequestsProduceIdenticalGrants() {
    const Log first = contendedRun();
    const Log second = contendedRun();
    CHECK(first == second);

    int grants = 0;
    int refusals = 0;
    for (std::size_t i = 0; i < first.count; ++i) {
        (first.entries[i].granted ? grants : refusals) += 1;
    }
    CHECK(grants > 0);
    CHECK(refusals > 0);  // the run actually contended, so the comparison means something
}

}  // namespace

int main() {
    ownedSlotsGoToTheirOwnerOnly();
    aFreeSlotGoesToTheHighestPriorityContender();
    aRefusedCpuStallsOnTheTimeline();
    bltpriPutsTheBlitterAheadOfTheCpu();
    bltpriClearDoesNotLockTheCpuOut();
    bltpriClearYieldsRepeatedlyAtASteadyInterval();
    copperWaitReleasesAtTheComparedPosition();
    copperTakesOnlyFreeEvenSlots();
    cpuTimingEmergesFromTheDisplayMode();
    anAsynchronousArbiterNeedsNoAllocator();
    identicalRequestsProduceIdenticalGrants();
    return meta::amiga::test::summarise("bus_arbiter");
}
