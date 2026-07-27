// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/scheduler.hpp"

#include <cassert>

namespace meta::amiga::core {

Scheduler::Scheduler() noexcept {
    due_.fill(kNever);
}

void Scheduler::bind(Device device, Handler handler, void* context) noexcept {
    slots_[static_cast<std::size_t>(device)] = Slot{handler, context};
}

void Scheduler::scheduleAt(Device device, Cycle at) noexcept {
    assert(at >= now_ && "scheduled an event in the past");
    due_[static_cast<std::size_t>(device)] = (at < now_) ? now_ : at;
}

void Scheduler::cancel(Device device) noexcept {
    due_[static_cast<std::size_t>(device)] = kNever;
}

Cycle Scheduler::nextDue() const noexcept {
    Cycle earliest = kNever;
    for (const Cycle at : due_) {
        if (at < earliest) {
            earliest = at;
        }
    }
    return earliest;
}

void Scheduler::runUntil(Cycle deadline) noexcept {
    if (deadline <= now_) {
        return;
    }

    for (;;) {
        // Lowest cycle wins; on a tie the lower Device ordinal wins, which is what makes
        // the dispatch order reproducible (ADR-CORE-01 D6). A strict `<` comparison over
        // the array in declaration order gives exactly that.
        std::size_t next = kDeviceCount;
        Cycle earliest = kNever;
        for (std::size_t i = 0; i < kDeviceCount; ++i) {
            if (due_[i] < earliest) {
                earliest = due_[i];
                next = i;
            }
        }

        if (next == kDeviceCount || earliest > deadline) {
            break;
        }

        now_ = earliest;

        // Clear before dispatching so a handler can reschedule itself — the ordinary way
        // a periodic device keeps running.
        due_[next] = kNever;

        const Slot& slot = slots_[next];
        if (slot.handler != nullptr) {
            slot.handler(slot.context, now_);
        }
    }

    now_ = deadline;
}

}  // namespace meta::amiga::core
