#!/usr/bin/env bash
# Sync the default branch to a fresh, clean base. Shared by /begin (Phase A,
# start-of-contribution) and /ship (Step 1, refresh-before-PR): both need the
# canonical default branch fast-forwarded to its remote before work runs against
# it, and both derive the same facts (mode, canonical remote, default branch) the
# same way, so that logic lives here once instead of drifting between two skills.
#
# The begin skill reaches this file as a sibling
# (<begin-skill-base>/../ship/scripts/sync-base.sh); the canonical copy lives
# here and only here.
#
# Usage: sync-base.sh
#
# Pure git, no gh required. If a project ever needs to override the derived
# default branch, that belongs in the calling skill, not here.
#
# What it does:
#   - Detects mode from the remotes: an `upstream` remote means CONTRIBUTION mode
#     (origin is a fork, upstream is canonical); otherwise MAINTAINER mode (origin
#     is canonical).
#   - Derives the default branch from the canonical remote's HEAD. Never assumes
#     `main`; a repo whose default is `master` or `develop` syncs correctly.
#   - Refuses to run on a dirty working tree. The calling skill owns the
#     "ask the user to commit or stash" conversation; this is only a backstop so
#     the script never switches branches under uncommitted work.
#   - Fast-forwards the default branch to the canonical remote, IN PLACE without
#     moving your current checkout when HEAD is on another branch. A sync is a
#     base-refresh, not a branch change: switching the checkout out from under an
#     occupied feature lane (/begin) or the feature branch being shipped (/ship)
#     is the surprise both callers depend on this script NOT causing. So it only
#     `git switch`es when the default branch already is your current branch;
#     otherwise it fast-forwards the default's ref without checking it out. In
#     contribution mode it also pushes the fork's default branch and verifies the
#     fork is level with upstream. A fast-forward that cannot happen means
#     divergence: the script aborts non-zero and forces nothing.
#
# Exit codes: 0 sync succeeded; non-zero on dirty tree, divergence, or any git
# failure (set -e). Every abort prints a one-line reason prefixed `ABORT:`.
set -euo pipefail

abort() {
  printf 'ABORT: %s\n' "$1" >&2
  exit 1
}

# ---- Preconditions ---------------------------------------------------------

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || abort "not inside a git working tree."

# Dirty tree backstop. --porcelain prints nothing for a clean tree (tracked and
# staged changes; untracked files are ignored here because switching branches
# does not endanger them, matching the skills' clean-tree guard).
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  abort "working tree is dirty. Commit or stash first (the calling skill asks how); this script will not touch your uncommitted work."
fi

# ---- Mode and canonical remote ---------------------------------------------

if git remote get-url upstream >/dev/null 2>&1; then
  MODE="contribution"
  REMOTE="upstream"
else
  MODE="maintainer"
  REMOTE="origin"
fi

git remote get-url "$REMOTE" >/dev/null 2>&1 \
  || abort "no '$REMOTE' remote found; cannot determine the canonical repository."

# ---- Derive the default branch ---------------------------------------------
# Prefer the recorded remote HEAD symref (cheap, offline). If it is unset (a
# fresh clone can lack it), fall back to asking the remote directly.

DEFAULT=""
if ref="$(git symbolic-ref --quiet "refs/remotes/${REMOTE}/HEAD" 2>/dev/null)"; then
  # ref looks like refs/remotes/<remote>/<branch>; strip the prefix.
  DEFAULT="${ref#refs/remotes/${REMOTE}/}"
fi
if [ -z "$DEFAULT" ]; then
  DEFAULT="$(git remote show "$REMOTE" 2>/dev/null \
    | awk '/HEAD branch:/ { print $NF }')"
fi
[ -n "$DEFAULT" ] \
  || abort "could not derive the default branch from remote '$REMOTE' (no remote HEAD; try 'git remote set-head $REMOTE -a')."

# ---- Sync ------------------------------------------------------------------

git fetch "$REMOTE"

# Fast-forward the default branch WITHOUT moving the current checkout. How
# depends on where HEAD is, because the sync must never switch a checkout that
# is hosting other work (an occupied lane, or /ship's feature branch):
#   - Default IS the current branch: fast-forward it in place (--ff-only refuses
#     a merge commit, so a non-fast-forward means divergence).
#   - HEAD is on ANOTHER branch (or detached): update the default's ref straight
#     from the remote via a fast-forward-only refspec, leaving the checkout put.
#     git rejects a non-ff refspec update (divergence) with a nonzero status
#     rather than forcing it, so the divergence guarantee is identical.
# Either path leaves the caller on exactly the branch it started on, so /begin's
# lane guard still sees the occupied lane and /ship stays on its feature branch.
CURRENT="$(git branch --show-current)"   # empty on a detached HEAD

if [ "$CURRENT" = "$DEFAULT" ]; then
  git merge --ff-only "${REMOTE}/${DEFAULT}" \
    || abort "'$DEFAULT' diverged from '${REMOTE}/${DEFAULT}' (fast-forward not possible). A stray commit likely landed on the default branch; sort it out before starting or shipping work. Nothing was forced."
else
  # Whether the default branch is diverged is a question about refs
  # (git rev-parse "$DEFAULT" vs. "${REMOTE}/${DEFAULT}"), not about whether it
  # can be checked out. A ref-update refspec (`git fetch $REMOTE
  # ${DEFAULT}:${DEFAULT}`) fails whenever another worktree has that branch
  # checked out, even when the two revs are already identical, which used to
  # get misreported as "diverged" and abort a perfectly synced base. Compare
  # revs first: already equal means already synced, nothing to update, and the
  # other worktree's checkout is irrelevant to that fact.
  LOCAL_REV="$(git rev-parse --quiet --verify "$DEFAULT" 2>/dev/null || true)"
  REMOTE_REV="$(git rev-parse --quiet --verify "${REMOTE}/${DEFAULT}" 2>/dev/null || true)"
  if [ -n "$LOCAL_REV" ] && [ "$LOCAL_REV" = "$REMOTE_REV" ]; then
    : # Already fast-forwarded; nothing to do, regardless of who else has it checked out.
  else
    git fetch "$REMOTE" "${DEFAULT}:${DEFAULT}" \
      || abort "'$DEFAULT' diverged from '${REMOTE}/${DEFAULT}' (fast-forward not possible), or it is checked out in another worktree. A stray commit likely landed on the default branch; sort it out before starting or shipping work. Nothing was forced, and your current checkout ('${CURRENT:-detached HEAD}') was not moved."
  fi
fi

SYNC="fast-forwarded '$DEFAULT' to '${REMOTE}/${DEFAULT}'"

if [ "$MODE" = "contribution" ]; then
  # Keep the fork's default branch level with upstream, then prove it: a nonzero
  # count means the push did not land the fork where upstream is.
  git push origin "$DEFAULT"
  behind="$(git rev-list --count "origin/${DEFAULT}..${REMOTE}/${DEFAULT}")"
  [ "$behind" = "0" ] \
    || abort "fork 'origin/$DEFAULT' is still $behind commit(s) behind '${REMOTE}/${DEFAULT}' after push."
  SYNC="$SYNC and pushed to 'origin/$DEFAULT' (fork level with upstream)"
fi

# ---- Report derived facts --------------------------------------------------

printf 'mode:            %s\n' "$MODE"
printf 'canonical remote: %s\n' "$REMOTE"
printf 'default branch:  %s\n' "$DEFAULT"
printf 'sync result:     %s\n' "$SYNC"
