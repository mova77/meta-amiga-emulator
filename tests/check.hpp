// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// A deliberately tiny test harness. The core has no dependencies (ADR-PORT-04 D1) and
// the tests are not worth acquiring one for: each test binary is a `main` that returns
// non-zero on failure, and CTest does the rest. If the suite ever needs fixtures,
// parameterisation or death tests, that is the point to reconsider — with an ADR.

#ifndef META_AMIGA_TESTS_CHECK_HPP
#define META_AMIGA_TESTS_CHECK_HPP

#include <cstdio>

namespace meta::amiga::test {

inline int failures = 0;

inline void report(bool ok, const char* expr, const char* file, int line) {
    if (!ok) {
        ++failures;
        std::fprintf(stderr, "%s:%d: FAILED  %s\n", file, line, expr);
    }
}

inline int summarise(const char* suite) {
    if (failures == 0) {
        std::fprintf(stderr, "%s: ok\n", suite);
        return 0;
    }
    std::fprintf(stderr, "%s: %d failure(s)\n", suite, failures);
    return 1;
}

}  // namespace meta::amiga::test

#define CHECK(expr) ::meta::amiga::test::report((expr), #expr, __FILE__, __LINE__)

#define CHECK_EQ(a, b)                                                     \
    ::meta::amiga::test::report((a) == (b), #a " == " #b, __FILE__, __LINE__)

#endif  // META_AMIGA_TESTS_CHECK_HPP
