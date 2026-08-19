#!/usr/bin/env bash
# Pre-PR mechanical scan: greps the diff against the base branch for the
# "embarrassing class" of mistakes that disproportionately erode reviewer trust.
#
# Usage: diff-scan.sh <base-ref> [profile ...]
#
# The base ref is required on purpose: defaulting to `main` would silently
# scan the wrong range on a repo whose default branch is master or develop.
#
# The checks split into two layers:
#   - a universal core that runs for every project (leftover debug markers,
#     Conventional Commits subject shape). These encode rules that hold
#     regardless of language or owner, so they live here. Personal style
#     rules do not belong in the core; put them in a profile.
#   - zero or more language PROFILES named on the command line. Each profile
#     <name> sources scripts/profiles/<name>.sh, which adds its own `check`
#     calls. The calling skill derives which profiles apply from the repo's
#     markers (e.g. Cargo.toml means rust); a Markdown-only project passes
#     none. To ship a new language regularly, add a profile file rather than
#     eyeballing the diff.
#
# Advisory only. Exit code 0 always. Every hit needs an explicit decision:
# fix it, or write the justification into the PR body's Notes section.
# Patterns are deliberately loose; a false positive costs one glance,
# a false negative costs reviewer trust.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${1:?usage: diff-scan.sh <base-ref> [profile ...]}"
shift || true
PROFILES=("$@")
RANGE="${BASE}...HEAD"
TOTAL=0

added_lines() {
  # Print "file: line" for every line added in the diff, restricted to a pathspec.
  git diff "$RANGE" -- "$@" | awk '
    /^\+\+\+ b\// { file = substr($0, 7) }
    /^\+[^+]/     { print file ": " substr($0, 2) }
  '
}

check() {
  local title="$1" pattern="$2"
  shift 2
  local matches
  matches=$(added_lines "$@" | grep -E "$pattern" || true)
  printf '\n== %s ==\n' "$title"
  if [ -n "$matches" ]; then
    printf '%s\n' "$matches"
    TOTAL=$((TOTAL + $(printf '%s\n' "$matches" | wc -l | tr -d ' ')))
  else
    echo "clean"
  fi
}

# ---- Universal core (runs for every project) -------------------------------

check "Leftover debug or placeholder markers" \
  'TODO|FIXME|XXX' '*'

# ---- Project profiles ------------------------------------------------------
# Each profile file is sourced with `check`, `added_lines`, `RANGE`, and `TOTAL`
# already defined, so it only needs to call `check "..." '<pattern>' <pathspec>`.

# Guard the expansion: under `set -u`, older bash (macOS ships 3.2) errors on an
# empty array, which is exactly the Markdown-only case where no profile is passed.
if [ "${#PROFILES[@]}" -gt 0 ]; then
  for profile in "${PROFILES[@]}"; do
    profile_file="${SCRIPT_DIR}/profiles/${profile}.sh"
    if [ -f "$profile_file" ]; then
      printf '\n--- profile: %s ---\n' "$profile"
      # shellcheck source=/dev/null
      source "$profile_file"
    else
      printf '\n== profile: %s ==\nWARNING: no profile file at %s (skipped). Add one, or drop the profile argument.\n' \
        "$profile" "$profile_file"
    fi
  done
fi

# ---- Commit-level checks (language-agnostic, always run) -------------------

printf '\n== Commit subjects: Conventional Commits shape ==\n'
BAD_SUBJECTS=$(git log --format='%h %s' "${BASE}..HEAD" \
  | grep -Ev '^[0-9a-f]+ (feat|fix|docs|test|refactor|chore|perf|build|ci)(\([a-z0-9_-]+\))?(!)?: ' || true)
if [ -n "$BAD_SUBJECTS" ]; then
  printf '%s\n' "$BAD_SUBJECTS"
  TOTAL=$((TOTAL + $(printf '%s\n' "$BAD_SUBJECTS" | wc -l | tr -d ' ')))
else
  echo "clean"
fi

printf '\n---\n%d finding(s). Each one gets fixed or justified in the PR Notes; none may be silently ignored.\n' "$TOTAL"
