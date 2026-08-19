#!/usr/bin/env bash
# Regression test for sync-base.sh's worktree-vs-divergence bug (2026-07-17
# /ship incident): main and origin/main pointed at the identical commit, but
# sync-base.sh aborted claiming divergence because main was checked out in
# another worktree. The old logic (see sync-base.sh history) went straight to
#   git fetch "$REMOTE" "${DEFAULT}:${DEFAULT}"
# whenever HEAD was on another branch, and that ref-update refspec fails any
# time the target branch is checked out elsewhere, identical revs or not, so a
# same-rev worktree collision was misreported as "diverged" and aborted.
#
# This test builds a local bare "remote", clones it into two worktrees so main
# is checked out in one while the other runs the sync, and asserts:
#   1. the same-rev + worktree-elsewhere case succeeds (the fix)
#   2. a genuinely diverged main still aborts non-zero (the guarantee holds)
#
# Pure local filesystem, no network. Usage: test_sync_base.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_BASE="$HERE/sync-base.sh"
SYNC_BASE_CMD=(bash "$SYNC_BASE")

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

# ---- Fixture: bare "remote" with main, plus a clone with two worktrees -----
# Bare repos default HEAD to master; set it to main explicitly so the
# "derive default branch from remote HEAD" logic in sync-base.sh resolves to
# main rather than silently doing nothing on this fixture.

REMOTE="$WORK/remote.git"
git init --bare --quiet "$REMOTE"
git -C "$REMOTE" symbolic-ref HEAD refs/heads/main

SEED="$WORK/seed"
git init --quiet "$SEED"
git -C "$SEED" checkout -q -b main
git -C "$SEED" -c user.email=t@t -c user.name=t commit -q --allow-empty -m "init"
git -C "$SEED" remote add origin "$REMOTE"
git -C "$SEED" push -q origin main

CLONE="$WORK/clone.git"
git clone --quiet --bare "$REMOTE" "$CLONE"
git -C "$CLONE" remote set-head origin main >/dev/null 2>&1 || true
git -C "$CLONE" symbolic-ref HEAD refs/heads/main
git -C "$CLONE" remote add origin "$REMOTE" 2>/dev/null || git -C "$CLONE" remote set-url origin "$REMOTE"
git -C "$CLONE" config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
git -C "$CLONE" fetch --quiet origin
git -C "$CLONE" remote set-head origin main >/dev/null

# worktree-a: sits on main (this is the "other worktree" occupying the branch)
WT_A="$WORK/wt-a"
git -C "$CLONE" worktree add --quiet "$WT_A" main

# worktree-b: a feature branch, this is where sync-base.sh runs from
WT_B="$WORK/wt-b"
git -C "$CLONE" worktree add --quiet -b feat/demo "$WT_B" main

# ---- Case 1: same rev, main occupied elsewhere -----------------------------
# main (local) == origin/main, but wt-a has main checked out. Old logic:
# `git fetch origin main:main` from wt-b fails here (branch checked out
# elsewhere) and gets misreported as divergence. Fixed logic: rev-compare first,
# see they're equal, skip the ref-update, succeed.

set +e
OUT1="$(cd "$WT_B" && "${SYNC_BASE_CMD[@]}" 2>&1)"
RC1=$?
set -e

check "case 1 (same rev, worktree elsewhere): exits 0" "$RC1" "0"
case "$OUT1" in
  *"ABORT:"*) check "case 1: no ABORT in output" "has-abort" "no-abort" ;;
  *) check "case 1: no ABORT in output" "no-abort" "no-abort" ;;
esac

# ---- Case 2: genuine divergence still aborts -------------------------------
# Advance origin/main past local main (both wt-a's main and origin diverge from
# what wt-b's clone-of-main ref stored). Re-derive: make origin/main move ahead
# via the seed repo, then diverge wt-a's local main with its own commit so a
# plain fast-forward is impossible from either direction.

git -C "$SEED" -c user.email=t@t -c user.name=t commit -q --allow-empty -m "upstream moves on"
git -C "$SEED" push -q origin main
git -C "$CLONE" fetch --quiet origin   # refresh clone's remote-tracking ref

git -C "$WT_A" -c user.email=t@t -c user.name=t commit -q --allow-empty -m "local diverges"

set +e
OUT2="$(cd "$WT_B" && "${SYNC_BASE_CMD[@]}" 2>&1)"
RC2=$?
set -e

check "case 2 (genuine divergence): exits non-zero" "$([ "$RC2" -ne 0 ] && echo nonzero || echo zero)" "nonzero"
case "$OUT2" in
  *"ABORT:"*"diverged"*) check "case 2: ABORT mentions divergence" "yes" "yes" ;;
  *) check "case 2: ABORT mentions divergence" "no" "yes" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
