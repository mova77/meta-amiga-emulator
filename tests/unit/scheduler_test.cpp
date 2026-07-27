// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// The scheduler is the one component the whole system's correctness rests on
// (ADR-CORE-01), so it is tested before anything is built on it.

#include "meta_amiga/core/scheduler.hpp"

#include <array>
#include <cstddef>

#include "check.hpp"

namespace {

using meta::amiga::core::Cycle;
using meta::amiga::core::Device;
using meta::amiga::core::kNever;
using meta::amiga::core::Scheduler;

/// Records what was dispatched, in the order it was dispatched, with the cycle the
/// handler observed.
struct Trace {
    struct Entry {
        Device device;
        Cycle at;
    };

    std::array<Entry, 32> entries{};
    std::size_t count = 0;

    void record(Device device, Cycle at) noexcept {
        if (count < entries.size()) {
            entries[count++] = Entry{device, at};
        }
    }
};

struct Periodic {
    Scheduler* scheduler = nullptr;
    Trace* trace = nullptr;
    Cycle period = 0;
    Device device = Device::Cpu;
};

void traceCopper(void* context, Cycle now) noexcept {
    static_cast<Trace*>(context)->record(Device::Copper, now);
}

void traceCpu(void* context, Cycle now) noexcept {
    static_cast<Trace*>(context)->record(Device::Cpu, now);
}

void traceBlitter(void* context, Cycle now) noexcept {
    static_cast<Trace*>(context)->record(Device::Blitter, now);
}

void tick(void* context, Cycle now) noexcept {
    auto* periodic = static_cast<Periodic*>(context);
    periodic->trace->record(periodic->device, now);
    periodic->scheduler->scheduleAt(periodic->device, now + periodic->period);
}

void dispatchesInCycleOrder() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Copper, traceCopper, &trace);
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.scheduleAt(Device::Cpu, 100);
    scheduler.scheduleAt(Device::Copper, 50);
    scheduler.runUntil(200);

    CHECK_EQ(trace.count, std::size_t{2});
    CHECK(trace.entries[0].device == Device::Copper);
    CHECK_EQ(trace.entries[0].at, Cycle{50});
    CHECK(trace.entries[1].device == Device::Cpu);
    CHECK_EQ(trace.entries[1].at, Cycle{100});
    CHECK_EQ(scheduler.now(), Cycle{200});
}

/// Ties break by Device order, which is the hardware's DMA priority order. This is the
/// property the whole determinism argument rests on, so it is asserted explicitly:
/// Copper (ordinal 9) must beat Blitter (10), which must beat Cpu (13).
void tiesBreakByDeviceOrder() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Copper, traceCopper, &trace);
    scheduler.bind(Device::Blitter, traceBlitter, &trace);
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    // Scheduled in reverse priority order, to prove insertion order does not leak in.
    scheduler.scheduleAt(Device::Cpu, 42);
    scheduler.scheduleAt(Device::Blitter, 42);
    scheduler.scheduleAt(Device::Copper, 42);
    scheduler.runUntil(43);

    CHECK_EQ(trace.count, std::size_t{3});
    CHECK(trace.entries[0].device == Device::Copper);
    CHECK(trace.entries[1].device == Device::Blitter);
    CHECK(trace.entries[2].device == Device::Cpu);
    for (std::size_t i = 0; i < trace.count; ++i) {
        CHECK_EQ(trace.entries[i].at, Cycle{42});
    }
}

void handlersMayRescheduleThemselves() {
    Scheduler scheduler;
    Trace trace;
    Periodic periodic{&scheduler, &trace, 7, Device::Copper};

    scheduler.bind(Device::Copper, tick, &periodic);
    scheduler.scheduleAt(Device::Copper, 7);
    scheduler.runUntil(30);

    // 7, 14, 21, 28 — and 35 is pending but beyond the deadline.
    CHECK_EQ(trace.count, std::size_t{4});
    CHECK_EQ(trace.entries[0].at, Cycle{7});
    CHECK_EQ(trace.entries[3].at, Cycle{28});
    CHECK_EQ(scheduler.dueAt(Device::Copper), Cycle{35});
    CHECK_EQ(scheduler.now(), Cycle{30});
}

void eventsBeyondTheDeadlineStayPending() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.scheduleAt(Device::Cpu, 500);
    scheduler.runUntil(100);

    CHECK_EQ(trace.count, std::size_t{0});
    CHECK(scheduler.pending(Device::Cpu));
    CHECK_EQ(scheduler.dueAt(Device::Cpu), Cycle{500});
    CHECK_EQ(scheduler.now(), Cycle{100});

    scheduler.runUntil(500);
    CHECK_EQ(trace.count, std::size_t{1});
    CHECK_EQ(trace.entries[0].at, Cycle{500});
    CHECK(!scheduler.pending(Device::Cpu));
}

void schedulingReplacesRatherThanQueues() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.scheduleAt(Device::Cpu, 10);
    scheduler.scheduleAt(Device::Cpu, 20);
    scheduler.runUntil(100);

    CHECK_EQ(trace.count, std::size_t{1});
    CHECK_EQ(trace.entries[0].at, Cycle{20});
}

void cancelWithdrawsAnEvent() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.scheduleAt(Device::Cpu, 10);
    CHECK(scheduler.pending(Device::Cpu));
    scheduler.cancel(Device::Cpu);
    CHECK(!scheduler.pending(Device::Cpu));

    scheduler.runUntil(100);
    CHECK_EQ(trace.count, std::size_t{0});
}

void idleSchedulerReportsNever() {
    Scheduler scheduler;
    CHECK_EQ(scheduler.nextDue(), kNever);
    scheduler.scheduleAt(Device::Beam, 9);
    CHECK_EQ(scheduler.nextDue(), Cycle{9});
}

/// A device with no handler bound is still scheduled and still consumes its event, so a
/// partially-built machine runs instead of crashing during bring-up.
void unboundDevicesDispatchAsNoOps() {
    Scheduler scheduler;
    scheduler.scheduleAt(Device::Sprites, 5);
    scheduler.runUntil(10);
    CHECK(!scheduler.pending(Device::Sprites));
    CHECK_EQ(scheduler.now(), Cycle{10});
}

void runningBackwardsIsANoOp() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.runUntil(100);
    scheduler.scheduleAt(Device::Cpu, 150);
    scheduler.runUntil(50);

    CHECK_EQ(scheduler.now(), Cycle{100});
    CHECK_EQ(trace.count, std::size_t{0});
}

/// SPIKE-S0 test 11. The determinism claim is that the dispatch trace is a pure function
/// of the schedule calls — so running the same schedule twice, with the calls issued in a
/// different order the second time, must produce identical traces.
void identicalSchedulesProduceIdenticalTraces() {
    const auto run = [](bool reversed, Trace& trace) {
        Scheduler scheduler;
        Periodic copper{&scheduler, &trace, 11, Device::Copper};
        Periodic blitter{&scheduler, &trace, 13, Device::Blitter};
        Periodic cpu{&scheduler, &trace, 7, Device::Cpu};

        scheduler.bind(Device::Copper, tick, &copper);
        scheduler.bind(Device::Blitter, tick, &blitter);
        scheduler.bind(Device::Cpu, tick, &cpu);

        if (reversed) {
            scheduler.scheduleAt(Device::Cpu, 7);
            scheduler.scheduleAt(Device::Blitter, 13);
            scheduler.scheduleAt(Device::Copper, 11);
        } else {
            scheduler.scheduleAt(Device::Copper, 11);
            scheduler.scheduleAt(Device::Blitter, 13);
            scheduler.scheduleAt(Device::Cpu, 7);
        }
        scheduler.runUntil(31);
    };

    Trace first;
    Trace second;
    run(false, first);
    run(true, second);

    CHECK(first.count > 0);
    CHECK_EQ(first.count, second.count);
    for (std::size_t i = 0; i < first.count && i < second.count; ++i) {
        CHECK(first.entries[i].device == second.entries[i].device);
        CHECK_EQ(first.entries[i].at, second.entries[i].at);
    }

    // Cpu at 7, 14, 21, 28; Copper at 11, 22; Blitter at 13, 26 — so the earliest event
    // is the Cpu's, despite it being the lowest-priority device.
    CHECK(first.entries[0].device == Device::Cpu);
    CHECK_EQ(first.entries[0].at, Cycle{7});
}

}  // namespace

int main() {
    dispatchesInCycleOrder();
    tiesBreakByDeviceOrder();
    handlersMayRescheduleThemselves();
    eventsBeyondTheDeadlineStayPending();
    schedulingReplacesRatherThanQueues();
    cancelWithdrawsAnEvent();
    idleSchedulerReportsNever();
    unboundDevicesDispatchAsNoOps();
    runningBackwardsIsANoOp();
    identicalSchedulesProduceIdenticalTraces();
    return meta::amiga::test::summarise("scheduler");
}
