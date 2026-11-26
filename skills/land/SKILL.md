---
name: land
description: Cross-project workflow that turns a finished feature branch into a reviewed PR through deterministic pre-PR gates. Run manually as /land at the end of the Verify & Land phase.
disable-model-invocation: true
---

# /land: cross-project PR landing workflow

This skill runs at the end of the Verify & Land phase, after `/verify` has passed
and cross-check findings are fixed. Its job is to make the boring parts of
landing a branch deterministic, because basic mistakes (a leftover debug line, a
dead parameter) damage reviewer trust far more than deep issues do. Every gate
below exists to eliminate that class before a human reviewer ever sees the diff.

## Step 0a. Derive the project facts

Everything per-project that this skill needs is derived at run time; there is
no per-project config file to create or maintain.

- **Mode and remotes.** An `upstream` remote means **contribution mode**
  (origin is a fork; the PR targets upstream; never push to upstream).
  Otherwise **maintainer mode** (the PR targets origin's default branch).
  Step 1's sync script derives and prints these same facts.
- **Quality gate commands.** If the project's agent instructions (AGENTS.md,
  CLAUDE.md) already state them, use those. Otherwise derive them from the
  repo's own build surface, whichever of justfile, Makefile, package.json
  scripts, Cargo.toml, pyproject.toml, or the CI workflow the repo carries,
  then confirm the derived commands with the user before treating them as
  the gate. After confirmation, offer (never insist) to record them in the
  project's agent instructions file so future runs skip the probe; when the
  project is not yours to add files to, just re-derive next time, the probe
  costs one directory listing and one file read.
- **Spec location.** The reviewer-facing spec Step 4 feeds its reviewer. If
  `openspec/changes/` exists, it is the active change (the same resolution
  the neighbor skills use); otherwise ask the user where the spec lives
  rather than guessing.
- **Scan profiles.** Derived from repo markers: `Cargo.toml` means `rust`.
  No marker, no profile; Step 2's universal core still runs.

## Step 0b. Entry assertions

The branch and a fresh base should already exist: syncing the base and cutting the
feature branch off it is the job of the start-of-contribution ritual (`/begin`,
whose Phase A syncs the base and whose Phase B opens the branch), not this skill.
These are gate-time assertions that it happened, not where it happens.

- The branch must be a feature branch named `<type>/<kebab-case>`
  (e.g. `feat/hook-system`, `fix/honor-pure-stdout`), never the default branch.
  If you are on the default branch, the branch was never opened properly: report
  that plainly and hand the fix to `/begin`'s Phase B (open the branch off the
  freshly-synced base), then stop. Leave the commits exactly where they are.
  Repairing this yourself, resetting the default branch, moving the commits onto
  a new branch, or any other history rewrite, is off-limits: those commits may
  already be shared, the default branch is the one ref every other checkout
  tracks, and an autonomous rewrite of it is precisely the kind of surprise this
  gate exists to prevent. Pointing at `/begin` keeps the decision (and the
  `git reset`) with the human who can see the whole picture.
- `git status` must be clean or contain only the work being landed.
- Confirm a verification pass and a review-fix pass already happened (in this
  setup, `/verify` and `/cross-check`). This is a hard
  precondition, not a courtesy check, so do not treat it as a question you may
  skip when running unattended. You must be able to point to concrete evidence:
  an artifact Step 0c's reconciliation finds on disk, a verify run earlier in
  this session, or the user stating it passed. If you
  have no such evidence, stop and say so explicitly in your output (a one-line
  "BLOCKED: no evidence verification passed") and let a human decide; do not proceed
  on the assumption that it probably passed. Silently skipping this is how
  unverified code reaches a PR in an autonomous run.
- **Detect an already-merged branch first.** Run
  `git merge-base --is-ancestor <branch> upstream/<default>` (or
  `origin/<default>` in maintainer mode) after fetching, where `<default>` is the
  derived default branch, not a hardcoded `main`: derive it from the canonical
  remote (`git symbolic-ref refs/remotes/<remote>/HEAD`), the same name Step 1's
  script prints. On a repo whose default is
  `master` or `develop`, `main` would be wrong or absent. If it succeeds, the
  branch is fully merged;
  stop and tell the user there is nothing to land. If only some commits are
  merged (a fixup landed on a merged branch, the common case), you are in
  **trailing-commit mode**: everything below operates on the unmerged commits
  only (`git log <base>..HEAD`), not the branch's whole history. Skipping this
  check is how an agent re-submits an entire already-merged feature.

## Step 0c. Review reconciliation: read the artifacts, not the claims

Each review layer in this setup leaves a machine-readable artifact on disk;
this step reads them back so the PR record rests on files, never on a
recollection that a review "passed". Resolve the artifact dir with the
**artifact directory rule** the neighbor skills write by: the active openspec
change directory (Step 0a's spec location) if one exists, else
`.review/<slug>/` at the repo root, where `<slug>` is the branch name with
`/` replaced by `-` (`feat/hook-system` → `.review/feat-hook-system/`).

Check these three layers, in this order:

1. **vibe-diff**: `<artifact_dir>/diff-review.json`. Summary line: the test
   status plus the gist of the overview (or the risk count), e.g.
   `vibe-diff: tests pass (cargo test, 14), 2 risks, 1 unverified claim`.
2. **cross-check**: `<artifact_dir>/review-verdict.json`, the two-axis
   verdict: `layer`, `fixed_point`, and `findings[]` each carrying `axis`,
   `title`, `severity`, `actioned`. Summary line: findings per axis and how
   many were actioned, e.g. `cross-check: 5 findings (standards 3, spec 2),
   4 actioned, since abc1234`.
3. **verify**: `.review/<slug>/verify.md`, always at this fixed path
   regardless of which tier holds the JSON artifacts: `/verify` is a built-in
   skill that cannot be taught the artifact directory rule, so the convention
   is that the verify session (or the user) drops its evidence there by hand.
   Summary line: its verdict line or first heading.

For every layer found, add its one-line summary to the derived-facts readback
and carry the same line into the PR body (Step 6, Testing section); for every
layer whose artifact is missing, the line is `<layer>: not run`. The step is
complete only when the readback carries exactly three layer lines, one per
layer, found or not: an absent layer stated plainly is honest, a silently
omitted one reads as "probably fine". A present artifact doubles as the
concrete evidence Step 0b's verification precondition asks for; a verbal "the
review passed" with nothing on disk is exactly the claim this step exists to
stop trusting.

**A missing artifact blocks nothing on its own, unless this branch came
through the pipeline.** The mechanical test is the same active-change
detection Step 0a already ran: exactly one entry under `openspec/changes/`,
excluding `archive/`. When there is one, this branch belongs to the
`/factory` → `/preflight` → `/land` pipeline, where cross-check and vibe-diff
are gates rather than options, so a missing `review-verdict.json` or
`diff-review.json` does not mean the layer never applied, it means a gate was
skipped. Stop and ask the user once, naming every missing layer in the same
question: run them now, or continue without them. If they waive it, the run
continues, the `<layer>: not run` line stays in the readback, and the waiver
goes into the PR body's Notes section (Step 6), so a reviewer reads what was
skipped instead of inferring it from a line that is simply absent. Off the
pipeline (no active openspec change, the `.review/<slug>/` tier), a missing
artifact is just a layer this branch never used: report it, continue, and add
no friction.

## Step 1. Refresh base and drift check

The initial sync (fast-forward the default branch, open the feature branch off
it) happened at the start of the contribution. This step is not that: time has
passed and upstream may have moved, so refresh the base again before the scan and
PR run against it. Step 2's scan diffs with a merge-base, and the PR merges into
the current base, so both need the default branch fresh right now, not as it was
when you started.

Run the same shared sync script `/begin`'s Phase A uses, from this skill's base
directory:

```
<skill-base>/scripts/sync-base.sh
```

It detects the mode, derives the default branch from the canonical remote (never
assuming `main`), fetches, and fast-forwards it; in contribution mode it also
pushes the fork's default branch and verifies the fork is level with upstream. It
prints the mode, canonical remote, default branch, and sync result. Because you
are on the feature branch here, the script fast-forwards the default **in place
and leaves you on the feature branch** (it does not switch you to the default),
so `<branch>` below and Step 2's `<base>...HEAD` keep resolving to the work you
are landing, with no manual switch-back. The `git fetch` it runs is a no-op if
Step 0b's already-merged check already fetched; re-running it is harmless. A
failed fast-forward means the default branch diverged: the script aborts non-zero
and forces nothing, so stop and report it rather than pushing past it just to
open the PR.

Then check whether the feature branch is behind the freshly-synced base, using
the `<default>` name the script just printed:

```
git rev-list --count <branch>..<default>   # commits the base has that the branch lacks
```

If behind and the overlap looks conflict-prone, probe it first (see Generic
conflict probing at the bottom) before rebasing.

## Step 2. Mechanical diff scan

Run `<skill-base>/scripts/diff-scan.sh <base> <profiles...>` with the repo as
cwd, never by a bare `scripts/...` path (that resolves against the repo root's
own unrelated `scripts/`). The base ref is required (a default would silently
assume `main`) and must be Step 1's freshly-refreshed default branch; the
trailing profiles are Step 0a's (e.g. `rust` on a Cargo project), or none.
The script diffs with a merge-base (`<base>...HEAD`), so output covering
commits you know already merged means Step 1 was skipped or mis-synced.

The scan runs in two layers. A **universal core** always runs: leftover
TODO/debug markers and non-conventional commit subjects, rules that hold for
any project and any owner. Then each derived **profile** sources
`<skill-base>/scripts/profiles/<name>.sh` for language-specific patterns (the
`rust` profile: leftover `dbg!`/`todo!`/`unimplemented!`, newly added
`#[allow]`). A Markdown-only project passes no profile and still gets the
core; for a language you use regularly, add a profile file rather than
eyeballing the diff. The core carries only rules true for everyone, a profile
only rules true for its whole language; personal style rules and one project's
traumas belong in the instructions that govern the writing, not in a shared
scanner.

Hits never fail the script (exit 0); triage every one explicitly: fix it, or
write the justification into the PR body's Notes section. Silently ignoring a
hit defeats the gate's purpose. The patterns are loose on purpose; a false
positive costs one glance, a false negative costs reviewer trust. A non-zero
exit (2, reason on stderr) means **the scan did not run**, never "clean": fix
the cause (not a git repo, unresolvable base, an erroring profile) and rerun,
because this gate has passed only when the scan actually ran.

## Step 3. Quality gate

Run the gate commands confirmed in Step 0a, fully green, no substitutions (a
bare compile proves nothing; run the project's checks and tests as confirmed).

## Step 4. Adversarial review gate

Dispatch ONE fresh-context general subagent (on Claude Code this is the Agent
tool with `subagent_type: general-purpose`; the `too-te`/`sai-hu` roles named
later are defined in `agents/` and select the same `subagent_type` field) on
the strongest review-grade model available, the tier the
delegation policy reserves for final review, and state in your output which
model you actually dispatched: a shallow review traced back to a weak reviewer
is a debugging fact the user needs, not something to reconstruct from logs.
Naming it once mid-run is not enough; it must survive into the final run
summary you report to the user (Step 7), as a fixed line naming the reviewer
model, in the form `adversarial review: <model>`, where `<model>` is the name
of the model that actually ran the review. A summary that omits it has lost the
fact the moment this session ends. The subagent type is not a substitute for
the model: `adversarial review: general-purpose` fills the slot with the wrong
fact and loses the one this line exists to carry. When no roster is installed
and the reviewer is therefore a plain general subagent, still name the model
and append the type, `adversarial review: <model> (general-purpose, no roster)`.
The prompt contains only the diff, the spec, and a reviewer persona. Provide
the diff as the literal output of `git diff <base>...HEAD` embedded in the
prompt (small diffs) or as a file path the subagent reads (large ones). The
spec location comes from Step 0a. This is a narrow-scope review; spec
compliance and general code quality were already covered by the earlier
cross-check pass. It looks only for: portability, security, API and naming
clarity, and any design point a reviewer would ask "why" about.

Persona, contribution mode:

> You are the upstream maintainer of this project, reviewing a PR from an
> outside contributor. You have not seen any of the development conversation.
> Find: portability problems, security problems, API and naming clarity
> problems, and any design point you would ask "why" about in review. Hold it
> to a maintainer's standard; do not go easy on it.

Maintainer mode: same axes, persona becomes an incoming external contributor
reading the codebase for the first time.

Why fresh context: a reviewer who watched the implementation inherits its
blind spots. In practice this pass catches what both the earlier review and
the human reviewer miss.

Each finding resolves one of two ways, and neither is hand-fixed inline in
this session:

- **A "why" you can answer is not a code change.** Pre-answer it in the PR
  description or a doc comment, so the reviewer does not ask again; an answer
  that stays in this conversation does not exist for them. The main session
  holds the design rationale, so it writes these itself, not a subagent.
- **A real finding deliberately not actioned this time is recorded, not
  dropped.** When you judge a finding true but out of scope for this PR (a
  pre-existing issue the diff merely exposes, a cleanup that deserves its own
  branch, a call too risky this close to opening the PR), record it in the PR
  body's Notes section (Step 2's triage rule). That is the authoritative record: it is
  versioned and travels with the PR, so the deferred truth does not evaporate
  when this branch merges. If the finding deserves tracking beyond this PR,
  offer to open a GitHub issue for it and open one only after the user confirms;
  never open an issue autonomously. Do not keep a separate committed backlog
  file for deferred findings.
- **A finding that needs a code change is dispatched, not iterated here.** By
  the time /land runs, this session already carries the entire implementation
  context, and iterating small review fixes inside it re-reads all of that per
  edit: it is the single most expensive part of landing a branch. So package
  the fixes and hand them off:
  1. Turn each code finding into a self-contained spec: the finding, the exact
     file and the hunk it refers to (the relevant slice of
     `git diff <base>...HEAD`), the done-criteria, and an explicit "do not
     commit" (the accept-before-commit gate in point 3 depends on it). The
     subagent inherits none of this conversation, so the spec must stand alone.
     Grade it the same way a `tasks.md` section is graded: `[dispatch:
     too-te|sai-hu, reason: <one-line grading rationale>]`. Mark
     `too-te` only when the fix is already fully decided (the finding
     names the exact change, e.g. a typo, a stray debug line, a missing
     import); mark `sai-hu` when the finding names a problem without
     settling how to fix it (a portability or naming call, an error-handling
     shape) so the fix still carries judgment.
  2. Split the graded specs into up to two bundles and dispatch each to its
     tier: a `too-te` bundle for the fully-decided fixes,
     a `sai-hu` bundle for the judgment-carrying ones. Skip a bundle that
     has no findings in it; run both in parallel when both exist. Neither
     subagent commits; commit organization (Step 5) stays with the main
     session, which owns the branch's history. If a tier's role type is not
     installed (a bare environment with no `agents/` roster), the dispatch would
     fail with the role not found; do not stall the run. Send that bundle to a
     fresh general subagent instead, still passing no `model` or `effort`,
     prepending the tier's one-line contract (`too-te`: apply the graded fixes
     exactly as specced, taking on no scope beyond them; `sai-hu`: settle the
     fix's open judgment within the finding's constraints), and note the tier in
     fallback form (`too-te (fallback: general)`) when you report the accepted
     fixes.
  3. Accept before committing: rerun the Step 3 quality gate to green and
     spot-check the returned diffs against the specs. A failed gate, or a fix
     that misread its spec, is re-dispatched to a fresh subagent at the same
     tier with the correction, not patched inline here. Once both hold and the
     branch has not been pushed yet (the normal case at this point in the
     flow), fold each accepted fix into the commit it corrects automatically,
     no confirmation needed: `git commit --fixup <target-commit>` per fix,
     then `GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash <base>` to fold
     them in one pass. This is a history rewrite on a branch nobody else has
     pulled, the same category `/begin`'s lane guard already treats as safe;
     ask first only if the branch turns out to already be pushed and shared.

## Step 5. Commit organization

Commit discipline lives in the global CLAUDE.md and applies while working,
not just here; this step only repairs what slipped through:

- Conventional Commits, one-line subject, imperative mood, lowercase scope
  matching the subsystem: `feat(hooks): add the /hooks slash command`.
- One commit per coherent section of work. Squash fixup commits into the
  commit they amend before opening the PR. Judge "fixup" by intent, not by file
  overlap: a fixup exists only to correct or complete an earlier commit on this
  branch (a typo, a missed file, an addressed review point) and has no
  standalone reviewable value, so fold it in. A commit that introduces its own
  distinct concern stands on its own even when small, so keep it and just fix
  its subject. When unsure, ask whether a reviewer would be confused why this
  is not simply part of the earlier commit: if yes, squash; if it reads as its
  own step, keep it. A different touched file is a weak signal either way, not
  the deciding one.

## Step 6. PR description

Write the body to a file and use `--body-file` (shell quoting mangles
multi-line bodies). Within each paragraph or bullet, write prose as a single
unwrapped line: no manual line breaks mid-sentence. GitHub renders a body at
the viewer's own width, so a hard-wrapped paragraph (one `\n` per ~80-100
chars, a common docs convention) shows up as broken mid-sentence line breaks
instead of flowing text. Only break the line between
paragraphs, list items, or headings. Structure:

```
## Summary
(1-3 sentences)

## Motivation
(what users could not do before, why the base repo should want this)

## Design decisions
(pre-answer the top three "why" questions a reviewer would ask)

## Testing
(bullet list: test coverage added, live verification actually performed,
then the Step 0c reconciliation lines, one per review layer, including
any "<layer>: not run" lines verbatim)

## Reviewing
(reading order, where to start, what is mechanical vs interesting)

## Notes
(caveats, follow-ups, justified scan findings from steps 2 and 4, and any
review layer the user waived at Step 0c, named as waived)
```

Title: under 70 chars, same Conventional Commits shape as commits. Design
decisions settled in conversation (especially via AskUserQuestion) must appear
here or as doc comments; a decision that lives only in a session log does not
exist for the reviewer.

Dispatch note: once the content exists, assembling the body (writing the file
in the structure above, enforcing the single-unwrapped-line and no-dash rules)
is mechanical, so it can go to a `too-te` subagent to keep it off the
expensive main session. But the judgment content, the design decisions and the
Step 4 "why" answers, lives in this session; put it in the dispatch spec,
because a subagent that never saw the conversation cannot reconstruct it.

## Step 7. Open the PR

Build the PR command from the mode (contribution mode targets the upstream
repo: `gh pr create -R <upstream> --base <default> --head <fork-owner>:<branch>`;
maintainer mode is a plain `gh pr create --base <default>`). The upstream repo
and fork owner come straight from the remote URLs. This step requires the
GitHub CLI (`gh`), the only hard dependency in the begin/land pair. Push the
branch to origin first. Report the PR URL, and alongside it the fixed line
naming the model that ran Step 4's adversarial review (e.g. `adversarial review: <model>`), so the final summary carries which reviewer the diff went
through. Do not post review-thread comments on the user's behalf;
draft text and let the user paste it.

## Step 8. After opening

- Ask the user for exactly one confirmation here: that the PR merged. Do not
  ask again per teardown item; once merge is confirmed, teardown is the
  default action, not a menu of prompts. Run all of the following that apply,
  skip whatever this branch never used, and report what was removed:
  - `git worktree remove <path>`, if the branch was opened in its own
    worktree (`/begin`'s Phase B1 lane guard).
  - `git branch -d <branch>` for the local feature branch (`-d`, not `-D`: a
    refusal to delete means it is not actually merged, which is worth
    stopping over, not forcing past).
  - Delete the remote branch, unless the merge already deleted it (GitHub's
    "delete branch" button, or `gh pr merge --delete-branch` if that is how
    Step 7 merged it): `git push origin --delete <branch>`.
  - If the project uses OpenSpec, the post-merge ritual is archiving the
    change (e.g. `/opsx:archive`); remind, don't run it here, and when that
    later post-merge session runs it, it is mechanical bookkeeping: dispatch
    it to a `too-te` subagent rather than spending the main session on
    it.
- If landing this branch surfaced a lesson that will outlive this PR (a new
  convention, a new gate), record it in memory or the relevant CLAUDE.md; otherwise
  record nothing.

## Generic conflict probing

The generic technique: fetch
the other change (`git fetch upstream pull/<N>/head:pr<N>` or the branch),
trial-merge in a throwaway worktree, inspect the overlap, then decide between
rebase and `git apply --3way`. Never resolve conflicts on the real branch
before understanding the overlap.
