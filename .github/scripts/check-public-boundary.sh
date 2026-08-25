#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# This repository is public. The private process harness that drives it must never appear
# here — not in file contents, and not in git metadata either. Commit messages and branch
# names are permanent and world-readable, and a force-push does not undo a leak: the
# orphaned commit stays fetchable by its SHA.
#
# The control used to be "run a scan by hand and remember to look at it". That caught a
# real leak once, which is exactly why it should not depend on anyone remembering.
#
# Exit 0 clean, 1 on a finding.

set -uo pipefail

# Patterns are deliberately narrow. A check that fires on innocent text gets switched off
# within a week, and a disabled check is worse than none. The first draft of this script
# used a generic tracker-key shape, [A-Z]{3}-[0-9]+, which matched GPL-3, SHA-1 and this
# project's own ADR-CORE-01 — 100+ false positives on a clean tree.
PATTERNS=(
  'atlassian\.net'      # the tracker host
  '/Users/[a-z]'        # a developer's local filesystem path, macOS
  '/home/[a-z]+/code'   # ditto, Linux
)

# The tracker's project key would be the most useful pattern of all, and it is precisely
# the thing that cannot be written down here: naming it in a public file leaks the
# identifier the check exists to protect. So it is supplied out of band, as a repository
# variable, and the check degrades gracefully when it is absent.
#
#   gh variable set PRIVATE_ID_PATTERN --body '<extended-regex>'
#
# Absent, the static patterns above still run. Present, its value is never echoed — only
# the file and line of a match, so a failure log cannot leak it either.
if [ -n "${PRIVATE_ID_PATTERN:-}" ]; then
  PATTERNS+=("$PRIVATE_ID_PATTERN")
  echo "── Private identifier pattern: supplied"
else
  echo "── Private identifier pattern: not set — tracker keys are NOT being checked"
  echo "   set the PRIVATE_ID_PATTERN repository variable to enable it"
fi

JOINED=$(IFS='|'; echo "${PATTERNS[*]}")

# This script names the strings it forbids, so it must not scan itself.
EXCLUDE=':(exclude).github/scripts/check-public-boundary.sh'

status=0

echo "── Scanning tracked file contents"
if hits=$(git grep -nIE "$JOINED" -- . "$EXCLUDE" 2>/dev/null) && [ -n "$hits" ]; then
  echo "::error::Private identifiers found in tracked files:"
  # Report location only. Echoing the matched line could republish the very identifier.
  echo "$hits" | cut -d: -f1,2 | sort -u
  status=1
else
  echo "   clean"
fi

# On a pull request, check everything the branch adds; otherwise the recent history.
range=""
if [ -n "${GITHUB_BASE_REF:-}" ]; then
  git fetch --quiet --depth=200 origin "$GITHUB_BASE_REF" 2>/dev/null || true
  range="origin/${GITHUB_BASE_REF}..HEAD"
elif [ -n "${1:-}" ]; then
  range="$1"
fi

echo "── Scanning commit messages${range:+ ($range)}"
if [ -n "$range" ]; then
  messages=$(git log --format='%H %s%n%b' "$range" 2>/dev/null)
else
  messages=$(git log --format='%H %s%n%b' -100 2>/dev/null)
fi

if hits=$(echo "$messages" | grep -cE "$JOINED") && [ "$hits" -gt 0 ]; then
  echo "::error::Private identifiers found in $hits commit-message line(s)."
  echo "Run the scan locally to see which — the log is public, so it is not printed here."
  status=1
else
  echo "   clean"
fi

if [ "$status" -ne 0 ]; then
  cat <<'GUIDANCE'

A force-push will not fix this once it is pushed — the commit stays reachable by SHA
through the GitHub API. Rewrite the history before it leaves your machine, or treat the
identifier as public from now on.
GUIDANCE
fi

exit "$status"
