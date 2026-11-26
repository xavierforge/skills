#!/usr/bin/env bash
# Test for diff-scan.sh's exit contract: hits are advisory (exit 0), while a
# scan that could not run exits 2 with a reason on stderr, so a broken scan can
# never be read as a clean one.
#
# Builds a throwaway repo with a main branch and asserts:
#   1. a planted debug line on a feature branch is reported, exit 0
#   2. a clean diff reports no hits, exit 0
#   3. an unresolvable base ref exits 2 with a one-line stderr reason
#   4. a profile that errors exits 2 (run from a copy of the script dir, so the
#      broken profile never lands in the real profiles/ folder)
#
# Pure local filesystem, no network. Usage: test_diff_scan.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIFF_SCAN="$HERE/diff-scan.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

check() {
  local desc="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then
    printf 'PASS: %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf 'FAIL: %s (got=%s want=%s)\n' "$desc" "$got" "$want"
    fail=$((fail + 1))
  fi
}

has() { case "$1" in *"$2"*) echo yes ;; *) echo no ;; esac; }

# Runs diff-scan in $REPO; sets OUT (stdout), ERR (stderr), RC.
scan() {
  local script="$1"
  shift
  set +e
  OUT="$(cd "$REPO" && bash "$script" "$@" 2>"$WORK/stderr")"
  RC=$?
  set -e
  ERR="$(cat "$WORK/stderr")"
}

g() { git -C "$REPO" -c user.email=t@t -c user.name=t "$@"; }

# ---- Fixture: main with one file, then a feature branch per case -----------

REPO="$WORK/repo"
git init --quiet -b main "$REPO"
printf 'fn main() {}\n' > "$REPO/lib.rs"
g add lib.rs
g commit -q -m "feat: init"

# ---- Case 1: planted debug line is reported --------------------------------

g switch -q -c feat/debug main
printf 'fn main() {}\nfn f(x: u8) { dbg!(x); }\n' > "$REPO/lib.rs"
g commit -q -am "feat(lib): add f"
scan "$DIFF_SCAN" main rust

check "case 1 (planted dbg!): exits 0" "$RC" "0"
check "case 1: the dbg! line is reported" "$(has "$OUT" 'lib.rs: fn f(x: u8) { dbg!(x); }')" "yes"
check "case 1: counts one finding" "$(has "$OUT" '1 finding(s).')" "yes"

# ---- Case 2: clean diff reports nothing ------------------------------------

g switch -q -c feat/clean main
printf 'fn main() {}\nfn g() {}\n' > "$REPO/lib.rs"
g commit -q -am "feat(lib): add g"
scan "$DIFF_SCAN" main rust

check "case 2 (clean diff): exits 0" "$RC" "0"
check "case 2: counts zero findings" "$(has "$OUT" '0 finding(s).')" "yes"
check "case 2: stderr is empty" "$ERR" ""

# ---- Case 3: unresolvable base exits 2 -------------------------------------

scan "$DIFF_SCAN" no-such-base
check "case 3 (unresolvable base): exits 2" "$RC" "2"
check "case 3: stderr says the scan did not run" "$(has "$ERR" 'scan did not run')" "yes"
check "case 3: stderr is one line" "$(printf '%s\n' "$ERR" | wc -l | tr -d ' ')" "1"

# ---- Case 4: an erroring profile exits 2 -----------------------------------

COPY="$WORK/scripts"
mkdir -p "$COPY/profiles"
cp "$DIFF_SCAN" "$COPY/diff-scan.sh"
printf 'false\n' > "$COPY/profiles/broken.sh"
scan "$COPY/diff-scan.sh" main broken
check "case 4 (profile errors): exits 2" "$RC" "2"
check "case 4: stderr names the profile" "$(has "$ERR" "profile 'broken' errored")" "yes"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
