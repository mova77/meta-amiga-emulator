// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors

#include "meta_amiga/core/version.hpp"

// THROWAWAY BRANCH — a planted breach of ADR-PORT-04 D1, to verify that the architecture
// test fails on every CI leg. NOT FOR MERGE.
//
// Declared here rather than reached through <cstdlib> on purpose: the include half of the
// check would catch an include and tell us nothing about whether the symbol half works on
// a given platform. With no include to find, only the symbol half can catch this.
extern "C" void* malloc(decltype(sizeof(0)) size);
extern "C" void free(void* p);

namespace {
// A volatile store, so the allocation is observable and the optimiser cannot elide the
// malloc/free pair — which it does, correctly, when the result is unused.
void* volatile sink = nullptr;
}  // namespace

namespace meta::amiga::core {

const char* linkedVersionString() noexcept {
    void* p = malloc(16);
    sink = p;
    free(p);
    return kVersionString;
}

}  // namespace meta::amiga::core
