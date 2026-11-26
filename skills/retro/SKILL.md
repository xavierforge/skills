---
name: retro
description: Learning loop for the delivery pipeline that turns a repeated mistake into enforced structure instead of more prose. Gathers evidence from a landed change's artifacts, records every occurrence in a tracked lessons ledger, and for a mistake class seen twice proposes the strongest enforcer that can hold it, applying only what the user approves. Run manually as /retro after /land, or when the same mistake happened again; works in any repo, with or without OpenSpec.
disable-model-invocation: true
---

# /retro: turn repeated mistakes into structure

A lesson written as one more sentence of prose gets re-learned; a lesson turned into a script, a check, or a test stays learned. This skill exists to make that conversion, and to refuse it when the evidence is thin, so the rule files every later session loads only grow when something actually recurred.

## Hard gates

These are the places an agent is tempted to cut a corner. Each one is absolute.

- **No evidence, no candidate.** A lesson with no artifact or transcript line behind it is dropped, however plausible it sounds; a remembered mistake is a guess.
- **A first occurrence is recorded and nothing else happens.** No proposal, no rule, no "just a small note" in a skill. One occurrence is an incident; two make a class worth enforcing.
- **Prose is the last rung.** Writing a sentence when a script, check, or test could hold the lesson is the failure this skill exists to stop; every prose item names each higher rung and why it cannot hold.
- **Nothing is applied before the user approves.** This skill edits the rules every later session loads; the only pre-approval write is occurrence lines in the lessons ledger.
- **A check never seen failing is unproven.** A check that was never run against the original mistake may be checking nothing.
- **Never edit an installed copy** (plugin caches, `~/.claude/skills`, `~/.codex`): it is overwritten on the next install and diverges from its source.

## The lessons ledger

`docs/lessons.md` at the repo root, a tracked file, created on first use with a one-line `# Lessons ledger` heading. It lives outside any change directory because recurrence is counted across changes, and change directories get archived. One line per observed occurrence or ruling:

```text
- 2026-11-26 [seen] leftover-debug-output: print() left in src/cli.py, removed after review (evidence: .review/feat-cli-json/review-verdict.json)
- 2026-12-03 [seen] leftover-debug-output: dbg! left in src/loader.rs (evidence: commit 3f2a9c1)
- 2026-12-04 [acted] leftover-debug-output: rung b, diff-scan core pattern, proven failing (supersedes: 2026-12-03 [seen])
```

- Tags: `[seen]` (one occurrence), `[acted]` (an approved enforcer was applied), `[rejected]` (a filter or the user turned it down, with the reason), `[backlog]` (real and recurring, enforcer not buildable now, with what blocks it).
- The class is a kebab-case slug naming the kind of error, not the instance. Before minting a new slug, read every existing slug and reuse one that fits; a near-duplicate slug silently resets the count to one.
- The evidence field names one artifact: a repo path, a commit SHA, a PR URL, or `session` followed by the quoted transcript line when the session is the only evidence.
- Append only. A changed status is a new line that names what it supersedes, never an edit, so the history of a class stays readable.
- The occurrence count of a class is its number of `[seen]` lines. A `[seen]` dated after an `[acted]` means the enforcer leaked: the class goes straight to Step 5 as a failed enforcer, and the new rung must sit at or above the old one.

## Step 1. Resolve the change and its artifact directory

Take the change from the user's words: the branch or change just landed, or the mistake they say happened again. If neither names one, use the most recently merged branch (`git log --merges -1` on the default branch) and say which you picked.

Resolve the artifact directory with the **artifact directory rule** the neighbor skills share: the single active change under `openspec/changes/` (excluding `archive/`) when exactly one exists; otherwise `.review/<slug>/` at the repo root, where `<slug>` is the branch name with `/` turned into `-`. A change already landed is often archived, so when that rule finds nothing for it, also look under `openspec/changes/archive/*<name>/`. With no `openspec/` directory at all, the `.review/<slug>/` tier is the only one, and git history plus the PR carry the rest.

Done when you have named the change, the artifact directory (or stated that none exists), and the commit range (`<base>..<branch tip>`, or the merge commit's parents).

## Step 2. Gather evidence, artifacts first

Read the durable record before the session, because the session's memory of what went wrong is the least reliable source here:

1. `decisions.md` in the artifact directory: `[caveat]`, `[reversal→*]`, and `[included]` lines are rulings that cost a round.
2. `review-verdict.json` and `diff-review.json` there: every finding with `actioned: true` was a mistake that reached review.
3. Preflight's closing status lines and `/land`'s reconciliation lines, found in the PR body's Testing and Notes sections (`gh pr view <n> --json body` when `gh` is available): `not run` and `pending` lines are skipped layers.
4. The branch's corrective commits: `fixup!`/`squash!` subjects and review-driven fixes in the commit range. After `/land` autosquashes they are gone from the log, so also read the PR's review threads and `git reflog` for the branch when it still exists.
5. The session, last: a tool output or exchange in this session that shows the mistake happening, quoted verbatim. A user saying a mistake happened is a pointer to go find its evidence, not the evidence itself.

Each candidate is one sentence naming what went wrong, plus the one artifact that shows it.

Done when every candidate carries an evidence pointer, and every lesson you considered but could not point to is listed as dropped for lack of evidence.

## Step 3. Group into classes and record occurrences

Group candidates by the kind of error, matching existing ledger slugs first (the ledger section's rule). Several candidates of one class in the same change count as one occurrence, since one change repeating a slip is one lapse.

Append one `[seen]` line per class occurrence to the ledger now, without asking: occurrence lines are observations, not rules, and recording them is what makes "twice" checkable next session. When the user says a mistake happened before and points at an artifact for that earlier time (a commit, a history entry, an old PR), record that occurrence too, dated by its artifact; a claim of "before" with no artifact stays unrecorded.

Done when the ledger carries one new `[seen]` line per class occurrence this run found, and no other line was changed.

## Step 4. Filter

Apply both filters and report what each removed, class by class:

- **Recurrence**: a class with one `[seen]` line stops here. Report it as recorded, first occurrence. Do not propose anything for it, not even prose.
- **Durability**: keep a class only if it will still hold in six months (not tied to one file, one dependency version, or a migration already finished) and is not already enforced. Check "already enforced" mechanically: the rule-to-enforcer table (Step 8), the repo's scripts, CI workflows, lint config, and eval cases. A class whose only enforcer is prose that it recurred through is not enforced; that is the signal to climb the ladder. A class removed here gets a `[rejected]` ledger line with the reason.

Done when every class is either removed with a stated filter and reason, or passed to Step 5.

## Step 5. Choose the rung

For each surviving class, pick the highest rung that can actually hold it, and justify each rung above the chosen one in one clause:

- **(a) Structure** removes the possibility: a script owns the step, an artifact is generated instead of hand-written, a template field forces the value.
- **(b) Mechanical check** fails loudly: a lint rule, a CI check, a gate command, a schema, a scan pattern.
- **(c) Test or eval case** reproduces the mistake.
- **(d) Prose** in a skill, AGENTS.md, or CLAUDE.md. Last resort only; "a check is more work" is not a clause that justifies skipping rung b.

Before a rung b or c item counts, it must be shown failing on the original mistake: reproduce the mistake (a throwaway worktree at the commit before the fix, or a minimal fixture), run the check, and capture the command and its failing output; then run it on the fixed tree and show it passing. When the check cannot be run yet (it still needs to be built), mark it `unproven` in the proposal and prove it in Step 7.

A lesson about a skill is applied in that skill's source repo: resolve its install path (`readlink -f`), and when it lands inside the current repo, edit the repo path; otherwise the item becomes a note for that skill's maintainer, never an edit to the installed copy.

Done when every surviving class has one rung, one named enforcer, a one-clause reason per skipped rung, and a proof state (`proven` with command and output, or `unproven`).

## Step 6. Propose, then stop

Present three lists, after the filter report from Step 4:

- **Accepted**: class, occurrence count with evidence pointers, rung, enforcer, skipped-rung clauses, proof state, files it will touch.
- **Rejected**: class and the reason (failed durability, already enforced, or not worth an enforcer).
- **Backlog**: recurring classes whose enforcer cannot be built this run, with what blocks it.

Then stop and wait for the user's ruling on each Accepted item. Do not start any edit to a rule, skill, check, test, or instruction file before it arrives; an unattended run ends here, with the ledger lines as its only writes. The user may move items between lists; their ruling wins.

Done when the three lists are in front of the user and no file other than the ledger has changed.

## Step 7. Apply what was approved

Turn each approved item into a self-contained spec (the class, the evidence, the exact files, the enforcer, the proof command, done-criteria, and "do not commit") and grade it the way `/land` grades its fix bundles: `[dispatch: too-te|sai-hu, reason: <one line>]`. Use `too-te` (the mechanical implementation role) when the change is fully decided, such as adding a named scan pattern or a table row; use `sai-hu` (the judgment-heavy implementation role) when the shape of the script, check, or test is still open. Dispatch one bundle per tier, in parallel when both exist. When the roster is not installed, send each bundle to a fresh general subagent with that tier's one-line contract prepended, as `/land` does.

Accept each returned diff only after rerunning the Step 5 proof: the new check fails on the reproduced mistake and passes on the fixed tree. A check that cannot be made to fail stays `unproven` in the table and the summary. Then append one `[acted]` ledger line per applied class, and a `[backlog]` or `[rejected]` line for each item the user moved.

Do not commit or push. The edits reach the default branch through the repo's normal flow (`/begin` for a branch, `/land` for the PR); say so in the summary.

Done when every approved item is applied, its proof state is final, and the ledger carries its status line.

## Step 8. Maintain the rule-to-enforcer table

Keep one table in the project's agent instruction file: `AGENTS.md` when it exists, otherwise `CLAUDE.md`; when neither exists, creating `AGENTS.md` is itself an item in the Step 6 proposal. The table lives under a `## Rule enforcement` heading:

```text
| Rule | Enforced by | Proven |
|------|-------------|--------|
| No leftover debug output in a diff | scripts/diff-scan.sh core pattern | yes |
| Name the reviewer model in the land summary | prose only | no |
```

One row per rule this skill has touched, and an existing row is updated in place when its enforcer climbs a rung. `prose only` rows are the visible backlog: the next `/retro` reads them first in Step 4, since a recurrence there is the cheapest one to act on.

Done when every class acted on this run has exactly one row naming its enforcer and proof state.

## Step 9. Summary

End every run with these lines, in this order, and nothing after them:

```text
retro: <n> occurrences recorded (<k> first occurrences) in docs/lessons.md
acted on: <class> rung <a|b|c|d> (<enforcer>), ... | none
checks: <p> proven failing, <u> unproven
status: awaiting approval | applied, uncommitted | nothing to propose
```

An unattended run that stopped at Step 6 reports `acted on: none` and `status: awaiting approval`; the proposal above it is what the user rules on.
