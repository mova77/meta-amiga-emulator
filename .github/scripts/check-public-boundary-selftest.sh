#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 The meta-amiga authors
#
# Holds check-public-boundary.sh to its exit-code contract — 0 clean, 1 finding, 2 could
# not run — against throwaway repositories. The case that matters most is the one with no
# symptom: a scan that errors and reports "clean". It runs before the real scan in CI, so
# a regression to failing open fails the job instead of passing it.
#
# The fixtures below build the forbidden strings at runtime, so this file does not trip
# the scan it tests. The private pattern is a made-up key shape, never a real one.

set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
check="$here/check-public-boundary.sh"
fake_key='ZZQ'"-4711"
fake_pattern='ZZQ'"-[0-9]+"
local_path='/Us'"ers/alice/code"

failures=0
cases=0

# new_repo <dir>: an empty repository with one clean commit.
new_repo() {
  mkdir -p "$1"
  git -C "$1" init --quiet
  git -C "$1" config user.name selftest
  git -C "$1" config user.email selftest@example.invalid
  echo clean > "$1/README"
  git -C "$1" add README
  git -C "$1" commit --quiet -m "Initial commit"
}

# expect <name> <exit> <repo> <pattern-or-empty> [args...]
expect() {
  local name=$1 want=$2 repo=$3 pattern=$4
  shift 4
  cases=$((cases + 1))
  local out got
  got=0
  out=$(cd "$repo" && env -u GITHUB_BASE_REF PRIVATE_ID_PATTERN="$pattern" "$check" "$@" 2>&1) \
    || got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL: $name — exit $got, expected $want"
    printf '%s\n' "$out" | sed 's/^/      /'
    failures=$((failures + 1))
    return
  fi
  # Whatever the outcome, the output must never contain the identifier it found.
  if printf '%s\n' "$out" | grep -qF -e "$fake_key" -e "$local_path"; then
    echo "FAIL: $name — the output republished the matched text"
    failures=$((failures + 1))
    return
  fi
  echo "ok:   $name"
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

new_repo "$work/clean"
expect "clean tree, no private pattern"          0 "$work/clean" ""
expect "clean tree, private pattern supplied"    0 "$work/clean" "$fake_pattern"
expect "invalid private pattern fails, not clean" 2 "$work/clean" 'ZZQ-('
expect "unresolvable range fails, not clean"      2 "$work/clean" "" "no-such-ref..HEAD"

new_repo "$work/content"
echo "see $local_path for details" > "$work/content/notes.txt"
git -C "$work/content" add notes.txt
git -C "$work/content" commit --quiet -m "Add notes"
expect "local path in file contents"             1 "$work/content" ""

new_repo "$work/key"
echo "tracked as $fake_key" > "$work/key/notes.txt"
git -C "$work/key" add notes.txt
git -C "$work/key" commit --quiet -m "Add notes"
expect "private key in file contents"            1 "$work/key" "$fake_pattern"
expect "same key, pattern unset, goes unseen"    0 "$work/key" ""

new_repo "$work/name"
mkdir -p "$work/name/d"
echo clean > "$work/name/d/$fake_key.txt"
git -C "$work/name" add "d/$fake_key.txt"
git -C "$work/name" commit --quiet -m "Add a file"
expect "private key in a file name"              1 "$work/name" "$fake_pattern"

new_repo "$work/message"
git -C "$work/message" commit --quiet --allow-empty -m "Fix the thing from $fake_key"
expect "private key in a commit message only"    1 "$work/message" "$fake_pattern"

echo "check-public-boundary self-test — $cases cases"
if [ "$failures" -ne 0 ]; then
  echo "FAIL — $failures case(s) did not behave as the exit-code contract says."
  exit 1
fi
echo "PASS — every case exited as expected and no output republished a match."
