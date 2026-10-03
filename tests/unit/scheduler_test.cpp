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

// Only used by the release-only regression test below; guarded so a debug build does not
// warn about an unused function under -Werror.
#ifdef NDEBUG
/// Always reschedules itself into the past — a programming error the scheduler must
/// survive rather than hang on.
void reschedulesIntoThePast(void* context, Cycle now) noexcept {
    auto* periodic = static_cast<Periodic*>(context);
    periodic->trace->record(periodic->device, now);
    periodic->scheduler->scheduleAt(periodic->device, 0);
}
#endif

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

/// The deadline is exclusive of `now()`: SPIKE-S0 §2.3 returns at once when
/// `deadline <= now`. So an event due exactly at `now()` waits for the next call with a
/// later deadline, and still observes its own cycle when it runs.
void aDeadlineAtNowDispatchesNothing() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);

    scheduler.runUntil(100);
    scheduler.scheduleAt(Device::Cpu, 100);
    scheduler.runUntil(100);

    CHECK_EQ(trace.count, std::size_t{0});
    CHECK(scheduler.pending(Device::Cpu));
    CHECK_EQ(scheduler.now(), Cycle{100});

    scheduler.runUntil(101);
    CHECK_EQ(trace.count, std::size_t{1});
    CHECK_EQ(trace.entries[0].at, Cycle{100});
    CHECK_EQ(scheduler.now(), Cycle{101});
}

/// A delta that would carry past `kNever` saturates rather than wrapping. Wrapped, it would
/// land in the past, which in a release build fires on the very next cycle.
void scheduleInSaturatesAtNever() {
    Scheduler scheduler;
    Trace trace;
    scheduler.bind(Device::Cpu, traceCpu, &trace);
    scheduler.runUntil(10);

    scheduler.scheduleIn(Device::Cpu, kNever);
    CHECK_EQ(scheduler.dueAt(Device::Cpu), kNever);
    CHECK(!scheduler.pending(Device::Cpu));

    scheduler.scheduleIn(Device::Cpu, kNever - 9);  // one past the largest exact delta
    CHECK_EQ(scheduler.dueAt(Device::Cpu), kNever);

    scheduler.scheduleIn(Device::Cpu, kNever - 11);  // exact, does not saturate
    CHECK_EQ(scheduler.dueAt(Device::Cpu), kNever - 1);

    scheduler.scheduleIn(Device::Cpu, kNever);
    scheduler.runUntil(1000);
    CHECK_EQ(trace.count, std::size_t{0});
}

/// SPIKE-S0 test 11. The determinism claim is that the dispatch trace is a pure function
/// of the schedule calls — so running the same schedule twice, with the calls issued in a
/// different order the second time, must produce identical traces. The periods collide
/// (all three at 12 and 24, Blitter and Cpu at 6 and 18), so the order within a
/// cycle is decided by the tie-break and not by which call happened to come first.
void identicalSchedulesProduceIdenticalTraces() {
    const auto run = [](bool reversed, Trace& trace) {
        Scheduler scheduler;
        Periodic copper{&scheduler, &trace, 4, Device::Copper};
        Periodic blitter{&scheduler, &trace, 3, Device::Blitter};
        Periodic cpu{&scheduler, &trace, 6, Device::Cpu};

        scheduler.bind(Device::Copper, tick, &copper);
        scheduler.bind(Device::Blitter, tick, &blitter);
        scheduler.bind(Device::Cpu, tick, &cpu);

        if (reversed) {
            scheduler.scheduleAt(Device::Cpu, 6);
            scheduler.scheduleAt(Device::Blitter, 3);
            scheduler.scheduleAt(Device::Copper, 4);
        } else {
            scheduler.scheduleAt(Device::Copper, 4);
            scheduler.scheduleAt(Device::Blitter, 3);
            scheduler.scheduleAt(Device::Cpu, 6);
        }
        scheduler.runUntil(24);
    };

    Trace first;
    Trace second;
    run(false, first);
    run(true, second);

    // Blitter 3..24 (8), Copper 4..24 (6), Cpu 6..24 (4).
    CHECK_EQ(first.count, std::size_t{18});
    CHECK_EQ(first.count, second.count);
    for (std::size_t i = 0; i < first.count && i < second.count; ++i) {
        CHECK(first.entries[i].device == second.entries[i].device);
        CHECK_EQ(first.entries[i].at, second.entries[i].at);
    }

    // Within a cycle, dispatch follows Device order. Count the ties so the test fails if
    // a change of periods ever stops producing them.
    std::size_t ties = 0;
    for (std::size_t i = 1; i < first.count; ++i) {
        if (first.entries[i].at == first.entries[i - 1].at) {
            ++ties;
            CHECK(first.entries[i - 1].device < first.entries[i].device);
        }
    }
    CHECK_EQ(ties, std::size_t{6});

    // The three-way collision at 12, spelled out.
    std::size_t at12 = 0;
    while (at12 < first.count && first.entries[at12].at != Cycle{12}) {
        ++at12;
    }
    CHECK(at12 + 2 < first.count);
    if (at12 + 2 < first.count) {
        CHECK(first.entries[at12].device == Device::Copper);
        CHECK(first.entries[at12 + 1].device == Device::Blitter);
        CHECK(first.entries[at12 + 2].device == Device::Cpu);
    }
}

/// Scheduling in the past is a bug, and in a debug build the assertion catches it first.
/// In a release build it must still terminate: clamping to the *current* cycle would
/// re-dispatch the same event forever, so the clamp lands on the next cycle and runUntil
/// keeps advancing. Skipped where assertions are live, because the assert fires by design.
#ifdef NDEBUG
void aPastScheduleAdvancesRatherThanHanging() {
    Scheduler scheduler;
    Trace trace;
    Periodic backwards{&scheduler, &trace, 0, Device::Cpu};

    scheduler.bind(Device::Cpu, reschedulesIntoThePast, &backwards);
    scheduler.scheduleAt(Device::Cpu, 5);
    scheduler.runUntil(20);  // hangs if the clamp lands on now_ instead of now_ + 1

    // Fires once per cycle from 5 to 20 inclusive, then stops at the deadline.
    CHECK_EQ(trace.count, std::size_t{16});
    CHECK_EQ(trace.entries[0].at, Cycle{5});
    CHECK_EQ(trace.entries[trace.count - 1].at, Cycle{20});
    CHECK_EQ(scheduler.now(), Cycle{20});
}
#endif

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
    aDeadlineAtNowDispatchesNothing();
    scheduleInSaturatesAtNever();
    identicalSchedulesProduceIdenticalTraces();
#ifdef NDEBUG
    aPastScheduleAdvancesRatherThanHanging();
#endif
    return meta::amiga::test::summarise("scheduler");
}
