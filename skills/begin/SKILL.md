---
name: begin
description: Two-phase start-of-contribution ritual, the opening bookend to /land. Run manually at the start of a new piece of work to sync the base, guard the tree, and open the feature branch when the work is nameable.
disable-model-invocation: true
---

# /begin: start-of-contribution ritual (two phases)

This runs at the very start of a piece of work, in two phases, because the two
halves of "get ready to work" become ready at different times.

**Phase A (base ready)** needs only the repo: guard the tree, sync the default
branch. Run it as early as possible; syncing now, not at PR time, is the
point, because a feature built on a week-old base collides with upstream
right before the PR.

**Phase B (open the branch)** needs a decision: a branch can only be named
once the work is clear enough to name. If there is no direction yet, stopping
after Phase A is a complete, valid outcome; a forced placeholder name outlives
its usefulness. The one ordering that matters: **the branch must exist before
the new work's first commit.** Files scaffolded earlier are harmless, an
uncommitted tree travels with the branch switch; a commit landed on the
default branch is the mistake. `/begin` is deliberately small: sync, guard,
branch. No spec scaffolding; that is a separate concern.

---

## Phase A: base ready

Run this as early as possible, even with zero direction. All three steps below
need only the repository, not a decision about what to build.

### Step A1. Clean-tree guard

Run `git status`. The working tree must be clean before switching branches. If it
is dirty, stop and ask the user to commit or stash first; do not auto-stash. A
silent stash is the kind of surprise that loses someone's uncommitted work or
leaves it stranded on the wrong branch, and the cost of asking is one sentence.

Also check where you are (`git branch --show-current`): if you are already on a
feature branch (not the default branch), stop and ask whether the user is
starting genuinely new work or continuing existing work. Never silently cut a new
branch off another feature branch: that quietly bases the new work on unmerged
commits.

### Step A2. Sync the default branch to latest

Run the shared sync script. Its canonical copy lives in the land skill, which
sits beside this one, so resolve it from this skill's base directory (the path
announced when the skill is invoked); never assume an install location such as
`~/.claude/skills/`:

```
<skill-base>/../land/scripts/sync-base.sh
```

It is pure git (no gh needed) and owns the mechanical half of this step: detect
the mode (an `upstream` remote means **contribution mode**, origin is your fork;
otherwise **maintainer mode**, origin is canonical; the same rule `/land` uses),
derive the default branch from the canonical remote (never assuming `main`),
and fast-forward it to the canonical remote. Crucially, it fast-forwards the
default **in place, without switching your checkout**: if you are sitting on an
occupied lane (Step A1 found you on a feature branch and the user confirmed new
work), the sync brings the default up to date but leaves you on that lane, so
Step B1 below still sees the lane and worktrees the new work off the fresh
default. Only when the default already is your current branch does it fast-forward
by moving HEAD. In contribution mode it also pushes the fork's default branch and
verifies the fork is level with upstream. It prints the derived facts (mode,
canonical remote, default branch, sync result); read them back and use that
default branch name everywhere below in place of `<default>`. `/land`'s refresh
step calls the same script, which is why the base ends up in the identical shape
whether you sync here or there.

A failed fast-forward is not something to work around: it means the local (or
fork) default branch has **diverged** from the canonical one, and the script
aborts non-zero rather than force anything. Stop and report the divergence.
Divergence here usually means a stray commit landed on the default branch and
needs sorting out before new work starts; do not force-push or reset past it to
make the script pass.

The script also aborts on a dirty tree, but that is a backstop: Step A1 already
had the "commit or stash?" conversation with the user, and the script never
auto-stashes on your behalf.

### Step A3. Stop: base is fresh

Once the default branch is synced, Phase A is done. Tell the user plainly that the
base is fresh and up to date, and that they can start discussing or scoping the
work on solid ground.

If the work is **not** yet clear enough to name a branch, this is a complete,
valid stopping point. Say so and stop here; do not invent a branch name to look
productive. Phase B runs later, when the direction has emerged (and before the
new work's first commit).

If the work **is** already clear (the common case, when `/begin` was invoked with
the change already described), flow straight into Phase B in the same run.

---

## Phase B: open the branch

Enter Phase B only when the work is clear enough to give a real
`<type>/<kebab-case>` name that describes it: a feature, a bug fix, a docs audit,
a lint pass, a refactor, anything with a nameable subject. This can be immediately
after Phase A (when the work was already known) or later, when discussion has
produced a direction. The common shape is two invocations: `/begin` on arrival
(Phase A, then stop), discussion, `/begin` again once the work is nameable. The
second invocation re-runs Phase A first, then flows into Phase B: the guard and
sync are idempotent and cheap, and upstream may have moved during the
discussion, so the re-sync is the guarantee refreshing itself, not waste. Skip
straight to Phase B only when Phase A ran moments ago in this same session.

**Hard rules:**

- **Name the branch for real, nameable work.** Never `feat/wip`, `chore/stuff`,
  `feat/new-thing`, or any name you would rename within the hour: the name is a
  commitment to a subject; if you cannot name the subject, you are not in Phase B
  yet.
- **If the user has no direction, stop at Phase A.** Do not push into Phase B to
  feel complete. A missing branch is cheap; a wrong or throwaway branch is not.
- **Open the branch before the new work's first commit.** Scaffolded but
  uncommitted files are harmless, they travel with the branch switch; a commit
  landed on the default branch is the mistake this rule prevents.

### Step B1. One checkout, one lane guard

A "lane" is a checkout with in-flight work on it (a window sitting on a branch
mid-task). Before creating or switching to any branch, check this checkout: if
HEAD is on a non-default branch **and** there is work in flight (dirty tree, or
unpushed commits on that branch), stop and report that this checkout already
hosts an active lane. Do not switch branches in place: a branch switch in a
shared checkout silently moves every window attached to it. Git cannot see
the windows, so "work in flight" stands in for "this checkout is in active use."
Start the new lane in its own worktree instead (creating one is safe: it only
adds a sibling directory, unlike A1's stash which would move the user's work).
Run `git worktree list` to see existing worktrees and pick a non-colliding path,
then, slugifying the branch name for the path (the `/` in `<type>/<kebab-case>`
becomes `-`, since a literal `/` would nest a directory):

```
git worktree add ../<checkout-dir>-<type>-<kebab-case> -b <type>/<kebab-case> <default>
```

Branch explicitly from `<default>` (Phase A already synced it), not from
whatever this checkout's HEAD happens to be: HEAD is sitting on the occupied
lane's branch, and omitting the start-point would silently base the new lane
on that branch's unmerged commits, the same mistake A1 already guards against
for the in-place case.

1. Run the `git worktree add` command above.
2. Switch this session into the new worktree by calling `EnterWorktree` with
   `path` set to the directory just created: it only moves this session's cwd,
   so the original checkout's files, and the lane it was hosting, are
   untouched. (`EnterWorktree`/`ExitWorktree` are Claude Code-specific.
   `EnterWorktree` does not create anything; it only moves this session's cwd
   into the worktree the previous command already made, and every later step
   runs from inside it. On a harness without the tool, say so explicitly and
   make `<path>` the working directory for every step that follows: either
   `cd` into it, or root each later command at `<path>` explicitly. Do not
   silently stay in the original checkout and keep working there.)
   Verify the switch worked before continuing: confirm this session's working
   directory is now the new worktree, resolving `<path>` to an absolute path
   first since `pwd` reports one and `<path>` is relative. If the cwd did not
   move (on a fresh-shell harness a bare `cd` may not persist), root each later
   command at `<path>` explicitly, or stop and report, rather than continuing
   in the original checkout.
3. Tell the user they are now in `<path>` on `<type>/<kebab-case>`;
   `ExitWorktree` with `action: "keep"` returns to the original checkout later
   without discarding either lane's work. On a harness without `ExitWorktree`,
   returning later is just `cd`-ing back to the original checkout directory
   yourself; either way both lanes' work stays intact.

### Step B2. Choose the branch name

The branch must be `<type>/<kebab-case>`, matching the global commit conventions
and the assertion `/land` makes at gate time (`feat/hook-system`,
`fix/honor-pure-stdout`, `docs/audit-readme-links`). `type` is one of feat, fix,
docs, test, refactor, chore, perf, build, ci.

`/begin` is usually invoked because the work is already known, so lead with a
proposal: if the conversation makes the work obvious (a change being proposed, a
feature just described, an audit just scoped), propose a concrete default (e.g.
`feat/nested-dispatch`) and let the user confirm or correct it. Only ask cold when
context is genuinely absent, and if the answer is "I don't know yet," that is the
signal to fall back to Phase A's stopping point rather than press for a name.
Validate the shape before using it.

### Step B3. Open the branch off the fresh base

Cut the branch with an explicit start point, never from whatever HEAD happens
to be:

```
git switch -c <type>/<kebab-case> <default>
```

The start point matters even here: when Phase B runs later in its own session,
HEAD may be parked on a clean, fully-pushed feature branch that B1's lane guard
rightly lets through, and an implicit start point would silently base the new
work on that branch's unmerged commits. Naming `<default>` costs nothing when
you are already on it and prevents the wrong-base mistake when you are not.

Confirm you landed on it (`git branch --show-current`). Do not push an empty
branch: there are no commits yet, and `/land` (or the first real commit) pushes
it. Pushing now just creates an empty remote branch to clean up.

### Step B4. Save the mini-spec, only when one was explicitly requested

A mini-spec is written **on explicit request only**. Exactly two things count
as a request:

- **Spec text passed in the `/begin` command args.** Write that text verbatim,
  as-is; it is the user's words, not a summary of them.
- **The user asking for a mini-spec in so many words.** Write what they give
  you for it, or what they ask you to write up.

Anything else is a no-op: skip this step entirely and say nothing about it. In
particular, **a bare `/begin` at the end of a conversation about the work is
not a request.** Do not distill the chat into a spec, do not draft one to show
them, do not offer one or ask whether they want one. Conversation context is
what makes Step B2's branch name obvious; that is the whole of its job here.

The reason for the hard line: an unasked mini-spec is an unreviewed file, and
on the mini route it later becomes the baseline `/vibe-diff` reviews the diff
against, so the work gets graded against words the user never wrote or
approved. It also burns tokens and litters `.review/` on every branch that
never needed one.

When it does fire, write to `.review/<slug>/mini-spec.md`, where `<slug>` is
the branch name with `/` replaced by `-`, the same slugging B1 uses for the
worktree path (`feat/hook-system` → `.review/feat-hook-system/mini-spec.md`).
This mirrors where `/vibe-diff` and `/land` already keep their own artifacts,
so a later session finds all of a branch's review material in one place. Create
the directory if it does not exist. Tell the user where it was written. This skill
only writes the file and reports the path; whether `.review/` is gitignored is
each repo's own concern, not this skill's.

### Step B5. Hand off

Tell the user the base is fresh and the branch is open, so they can start the work
(including whatever scaffolding this change needs, which now has a branch to be
committed on). Remind them that `/land` at the end refreshes the base
again and runs the gates; they do not need to sync by hand before running it.
