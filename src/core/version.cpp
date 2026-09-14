// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/version.hpp"

// THROWAWAY BRANCH — a planted D1 breach, to verify the check goes red on every leg for
// the exception machinery specifically. NOT FOR MERGE.
//
// `throw` adds no include, so the source scan cannot see it; the exception object is
// heap-allocated, so the symbol half must. The MSVC spelling (_CxxThrowException) differs
// from the Itanium one (__cxa_allocate_exception / __cxa_throw), and only the Windows leg
// can confirm the denylist names it correctly.
namespace {
struct BadAddress {};
}  // namespace

namespace meta::amiga::core {

void probeThrow();
void probeThrow() {
    throw BadAddress{};
}

const char* linkedVersionString() noexcept {
    return kVersionString;
}

}  // namespace meta::amiga::core
