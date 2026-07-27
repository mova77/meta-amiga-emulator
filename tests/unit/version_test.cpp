// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 The meta-amiga authors
//
// A smoke test for the build foundation. It asserts almost nothing about the emulator
// and everything about the toolchain: that the version header is generated, that the
// include paths reach it, that the core library compiles and links under the strict
// warning set, and that the compiled-in version agrees with the header the caller saw.

#include "meta_amiga/core/version.hpp"

#include <string>
#include <string_view>

#include "check.hpp"

namespace {

using meta::amiga::core::kVersionFix;
using meta::amiga::core::kVersionRelease;
using meta::amiga::core::kVersionString;
using meta::amiga::core::kVersionYear;
using meta::amiga::core::linkedVersionString;

/// The version scheme is <yy>.<rel>.<fix> — a two-digit release year, not a semantic
/// major. A year outside this range means the scheme has been misread as semver, which
/// is the mistake this assertion exists to catch.
void versionSchemeIsYearReleaseFix() {
    CHECK(kVersionYear >= 26);
    CHECK(kVersionYear < 100);
    CHECK(kVersionRelease >= 0);
    CHECK(kVersionFix >= 0);
}

/// The string and the components are generated from the same CMake variables, so a
/// mismatch means the template and the project version have drifted apart.
void versionStringMatchesItsComponents() {
    const std::string_view actual{kVersionString};
    const std::string expected = std::to_string(kVersionYear) + "." +
                                 std::to_string(kVersionRelease) + "." +
                                 std::to_string(kVersionFix);
    CHECK(actual == expected);
}

/// Proves the core library was actually built and linked, not merely that its headers
/// were found — the failure mode a header-only smoke test cannot detect.
void linkedVersionMatchesTheHeader() {
    CHECK(std::string_view{linkedVersionString()} == std::string_view{kVersionString});
}

}  // namespace

int main() {
    versionSchemeIsYearReleaseFix();
    versionStringMatchesItsComponents();
    linkedVersionMatchesTheHeader();
    return meta::amiga::test::summarise("version");
}
