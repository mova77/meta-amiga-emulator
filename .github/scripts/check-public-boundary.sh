#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# This repository is public. The private process harness that drives it must never appear
# here — not in file contents, not in file names, and not in git metadata either. Commit
# messages and branch names are permanent and world-readable, and a force-push does not
# undo a leak: the orphaned commit stays fetchable by its SHA.
#
# The control used to be "run a scan by hand and remember to look at it". That caught a
# real leak once, which is exactly why it should not depend on anyone remembering.
#
# Exit 0 clean, 1 on a finding, 2 when the scan could not run. A scan that could not run
# is never reported as clean: a check that fails open is worse than no check, because it
# looks like coverage. check-public-boundary-selftest.sh holds it to that.
#
# Usage: check-public-boundary.sh [<commit-range>]

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
# secret, and the check degrades — loudly — when it is absent.
#
#   gh secret set PRIVATE_ID_PATTERN --body '<extended-regex>'
#
# A secret, not a repository variable: the Actions log prints a step's env block in clear
# text, so a variable would be published in every run log. A secret is masked there. This
# script never prints the pattern either — not in a finding, and not in an error, which is
# why every grep below discards stderr and reports the failure in its own words.
if [ -n "${PRIVATE_ID_PATTERN:-}" ]; then
  # Validate before use. An invalid regex must stop the job, not quietly match nothing.
  printf '' | grep -E -- "$PRIVATE_ID_PATTERN" >/dev/null 2>&1
  if [ "$?" -ge 2 ]; then
    echo "::error::PRIVATE_ID_PATTERN is not a valid extended regular expression." \
         "The scan cannot run; fix the repository secret."
    exit 2
  fi
  PATTERNS+=("$PRIVATE_ID_PATTERN")
  echo "── Private identifier pattern: supplied"
else
  # An annotation, not just a log line: a green job's log is never read, so the gap has
  # to show on the run summary or it is not being stated at all.
  echo "::warning::PRIVATE_ID_PATTERN is not set — tracker keys are NOT being checked." \
       "Set the repository secret to enable it."
  echo "── Private identifier pattern: not set — tracker keys are NOT being checked"
fi

JOINED=$(IFS='|'; echo "${PATTERNS[*]}")

# This script names the strings it forbids, so it must not scan itself.
SELF='.github/scripts/check-public-boundary.sh'

status=0

cannot_run() {
  echo "::error::$1 The scan cannot run, so the tree is NOT known to be clean."
  exit 2
}

# Fails the job unless the last command was a clean grep result: 0 (match) or 1 (none).
grep_ok() {
  [ "$1" -le 1 ] || cannot_run "$2 failed (exit $1)."
}

echo "── Scanning tracked file names"
if ! paths=$(git ls-files 2>/dev/null); then
  cannot_run "git ls-files failed."
fi
# Report the position in `git ls-files`, never the name: the name is what matched.
path_hits=$(printf '%s\n' "$paths" | grep -nE -- "$JOINED" 2>/dev/null)
grep_ok $? "The file-name scan"
if [ -n "$path_hits" ]; then
  echo "::error::Private identifiers found in tracked file names, at these entries of 'git ls-files':"
  printf '%s\n' "$path_hits" | cut -d: -f1
  status=1
else
  echo "   clean"
fi

echo "── Scanning tracked file contents"
content_hits=$(git grep -nIE -e "$JOINED" -- . ":(exclude)$SELF" 2>/dev/null)
grep_ok $? "git grep over tracked contents"
if [ -n "$content_hits" ]; then
  echo "::error::Private identifiers found in tracked files:"
  # Report location only. Echoing the matched line could republish the very identifier,
  # and so could a file name that itself matches — that one is reported above by number.
  printf '%s\n' "$content_hits" | cut -d: -f1,2 | sort -u | while IFS= read -r loc; do
    file=${loc%:*}
    if printf '%s\n' "$file" | grep -qE -- "$JOINED" 2>/dev/null; then
      echo "<file name withheld, see above>:${loc##*:}"
    else
      echo "$loc"
    fi
  done
  status=1
else
  echo "   clean"
fi

# On a pull request, check everything the branch adds; otherwise the recent history.
range=""
if [ -n "${GITHUB_BASE_REF:-}" ]; then
  git fetch --quiet --depth=200 origin "$GITHUB_BASE_REF" >/dev/null 2>&1 \
    || cannot_run "Could not fetch the base branch."
  range="origin/${GITHUB_BASE_REF}..HEAD"
elif [ -n "${1:-}" ]; then
  range="$1"
fi

echo "── Scanning commit messages${range:+ ($range)}"
if [ -n "$range" ]; then
  messages=$(git log --format='%H %s%n%b' "$range" 2>/dev/null) \
    || cannot_run "git log could not resolve the range."
else
  messages=$(git log --format='%H %s%n%b' -100 2>/dev/null) \
    || cannot_run "git log failed."
fi

hits=$(printf '%s\n' "$messages" | grep -cE -- "$JOINED" 2>/dev/null)
grep_ok $? "The commit-message scan"
if [ "$hits" -gt 0 ]; then
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
