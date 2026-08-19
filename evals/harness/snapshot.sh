#!/usr/bin/env bash
# Objective post-run git-state snapshot for grading.
# Usage: snapshot.sh <sandbox> <outdir>
set -uo pipefail
SB="${1:?sandbox}"; OUT="${2:?outdir}"
mkdir -p "$OUT"
{
  echo "## branch (current)"; git -C "$SB" branch --show-current
  echo; echo "## all branches -vv"; git -C "$SB" branch -vv
  echo; echo "## status --porcelain"; git -C "$SB" status --porcelain
  echo; echo "## log --oneline --all --decorate"; git -C "$SB" log --oneline --all --decorate
  echo; echo "## reflog (top 15)"; git -C "$SB" reflog --oneline | head -15
  echo; echo "## worktree list"; git -C "$SB" worktree list 2>/dev/null
  echo; echo "## HEAD show --stat"; git -C "$SB" show --stat --format='%H%n%an%n%s%n%b' HEAD 2>/dev/null
  # If a default branch exists, show the unmerged range and diffstat
  for def in main trunk master; do
    if git -C "$SB" show-ref --verify --quiet "refs/heads/$def"; then
      echo; echo "## commits on HEAD not on $def (git log $def..HEAD)"
      git -C "$SB" log --oneline "$def..HEAD" 2>/dev/null
      echo; echo "## diffstat $def...HEAD"
      git -C "$SB" diff --stat "$def...HEAD" 2>/dev/null
      break
    fi
  done
  # tasks.md files (section/ship)
  for f in $(git -C "$SB" ls-files '*tasks.md' 2>/dev/null); do
    echo; echo "## $f"; cat "$SB/$f"
  done
  echo; echo "## active change dirs (excluding archive)"
  ls -d "$SB"/openspec/changes/*/ 2>/dev/null | grep -v '/archive/$' || echo "(none)"
  echo; echo "## src/greetings.py"; cat "$SB/src/greetings.py" 2>/dev/null
  echo; echo "## tests present"; ls "$SB/tests" 2>/dev/null
} > "$OUT/git-state.txt" 2>&1
echo "snapshot -> $OUT/git-state.txt"
