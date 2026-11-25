# Eval evolution log

A condensed history of how each skill was measured and reshaped by those
measurements. Every round asked one question: what does the skill add, at a
fixed model, over the same model with no skill? Each entry records the round,
the pass rates (with_skill / without_skill and the gain Δ), and what the number
drove: a skill fix, an eval-design fix, or a decision.

This file holds two strata, neither of them the live baseline (that is
[`EVALUATION.md`](./EVALUATION.md)'s table, measured at `claude-sonnet-5`).

The **per-skill sections below** are the measurements taken *before* the
2026-07-24 contract re-alignment (role renames, starting-layer semantics).
Their result files have been removed, and iteration numbers restart from the
reruns, so those figures are history only and are **not directly comparable**
to any new result. Read them as the development trail.

The [**2026-07-25 round**](#the-2026-07-25-round) at the end is the whole
previous headline table, retired on 2026-08-06 when the baseline moved to
`claude-sonnet-5`. It is a complete, self-consistent round and its result
files are still in `results/<suite>/iteration-1/` (and `iteration-2`,
`iteration-3` for `preflight`); it is retired for the model change alone, not
for any defect in the round.

## `begin`

- **iter-2** (Sonnet, n=2, full-assertion): 1.00 / 0.51, Δ+0.49. Eval-2's
  lane-preservation assertion validated the `sync-base.sh` fix (fast-forward the
  default in place, never switch an off-default checkout); with the fix the
  skill was followed literally and the shared lane was preserved.
- **iter-3** (Sonnet, n=1, machine subset): 0.78 / 0.58, Δ+0.19. Surfaced two
  eval-2 calibration gaps: a `ref_equals` row that penalized the correct
  stop-to-ask behavior, and an `EnterWorktree` `text_contains` that failed on
  correct behavior (the tool is unavailable in-sandbox and the run stopped to
  confirm, describing the worktree in prose).
- **iter-4** (Sonnet, n=1, full-assertion after backfill): 1.00 / 0.38, Δ+0.62
  (machine subset 1.00 / 0.25). Both calibration gaps fixed: the `ref_equals`
  row removed, the `EnterWorktree` check promoted to `llm_judged`. That turned
  eval-2 from non-discriminating into a clean discriminator on the surviving
  `head_branch` check; deferred rows resolved by a backfill grader (sonnet).

## `land`

This suite was named `ship` until the skill was renamed to `land`. Its
recorded iterations moved to `results/land/` unchanged, so their
grading and benchmark JSON still carry `"skill_name": "ship"` and the
skill's old name in their wording; read those as the same suite.

- **iter-2** (Sonnet, n=2, full-assertion): 1.00 / 0.42, Δ+0.58. Caught an
  autonomous rewrite of the default branch (an early run reset `main` and moved
  commits onto a new branch, scoring 1/4). Step 0b was sharpened to report, hand
  to `/begin`, and leave commits in place with no self-repair; the re-run scored
  4/4.
- **iter-3** (Sonnet, n=1, machine subset, now including the Step 0c
  reconciliation case moved in from `review-artifacts`): 0.83 / 0.42, Δ+0.42.
  Surfaced two drop-items: a push-detection `text_contains` that matched git's
  own boilerplate, and eval-2's review-model report missing, a genuine skill
  defect (the reviewer model was never named in the final reply).
- **iter-4** (Sonnet, n=1, full-assertion after backfill): 1.00 / 0.42, Δ+0.58
  (machine subset 1.00 / 0.39). Fixes: push-detection promoted to `llm_judged`;
  the skill now carries the reviewer model into the final summary (Step 7's
  `adversarial review: <model>` line, `skill_commit 3654c63`), which turned the
  review-model check green on an unchanged check, a direct machine confirmation
  of the skill-side fix.

## `section`

- **iter-2** (Sonnet, n=2, full-assertion): 1.00 / 0.86, Δ+0.14. The small delta
  read as marginal, but `section` is designed for the cheap execution model, so
  Sonnet was the wrong tier to judge it on.
- **iter-3** (Haiku, the target tier, full-assertion): 0.71 / 0.33, Δ+0.38,
  roughly tripling the delta. Two conclusions: the skill is not marginal (its
  measured value concentrates in cheap-model failures like uncommitted work and
  unticked checkboxes), and there is a ceiling (a skill raises a weak model's
  floor but cannot substitute for capability).
- **iter-4** (Sonnet, n=1, machine subset): 1.00 / 0.81, Δ+0.19. Clean
  git-state discriminators (the baseline executed sections but never landed the
  commit), no calibration gaps this round.

## `factory`

- **iter-1** (Sonnet, n=1): 0.96 / 0.33, Δ+0.62, measured against the
  pre-hardening `SKILL.md`. The single with_skill miss (the ledger's total
  wall-time row dropped) traced to phrasing; the ledger spec now ends with an
  explicit closing `total` row.
- **iter-2** (Sonnet, n=2, machine subset): 1.00 ± 0.00 / 0.50 ± 0.46, Δ+0.50.
  The n=2 round was added to expose baseline variance, which it did (the
  baseline swung 0.0 to 1.0 across runs).

## `vibe-diff`

Carved out of the former cross-skill `review-artifacts` suite so every suite
names one skill.

- **review-artifacts iter-1** (Sonnet, n=1, baseline = the old `main` SKILL.md):
  measured the pre-hardening fallback-landing contract, with_skill 4/4 vs
  old_skill 2/4. Eval-2 was then re-specified to the hardened refusal contract
  (commit `e8bf4fb`), which made a spec source a precondition to run.
- **native iter-1** (machine subset): 1.00 (4/4) / 0.75 (3/4), Δ+0.25 under the
  current hardened refusal contract, run natively rather than as a regrade of
  the retained `review-artifacts` runs.

## `cross-check`

Also carved out of `review-artifacts`; the skill was renamed `spec-review`
to `cross-check` after that round ran.

- **review-artifacts iter-1** (Sonnet, n=1, as `spec-review`, baseline = no
  skill): with_skill 4/4 / without_skill 1/4. The baseline independently
  invented a machine-readable verdict but not the convention, so the skill's
  value is the fixed two-axis landing rule and shape, not the reviewing ability
  itself.
- **native iter-1** (machine subset): 1.00 (4/4) / 0.25 (1/4), Δ+0.75 under the
  current native two-axis contract.

## `spec-viewer`

- **iter-1** (Sonnet, n=1, fully mechanical, nothing deferred): 1.00 / 0.13,
  Δ+0.88, the widest gap measured. This is the suite the two new check types
  (`file_size` and `json_check.min_keys`) were added for; both decided
  correctly on live runs. The gap is wide because the skill's whole job (drive
  the generator, author a zh-TW gloss) is one a bare model does not do
  unprompted.

## `preflight`

- **iter-1** (Sonnet, n=1): 1.00 / 0.6667, delta +0.33. Scored with an honesty
  assertion that checked `decisions.md` for absence language; it passed on a
  coincidence, matching a `[caveat]` line about an unrelated finding that
  quoted the words "no test suite". The assertion was removed rather than
  narrowed, and the round was never regraded.
- **iter-2** (Sonnet, n=1): 0.8334 / 0.6111, delta +0.22, run after `SKILL.md`
  made the absent-layer ledger line a contract. The restored assertion is
  anchored on the `[caveat]` tag plus a named layer, and it now separates the
  arms on real behavior. The triage case dropped three rows because the run
  handed the reversal request and the tracked finding to the user without
  writing a ledger line for either, a gap in Step 5's tag vocabulary that this
  round deliberately left open.
- **iter-3** (Sonnet, n=1): 1.00 / 0.5555, delta +0.44, run after the tag
  vocabulary gained `[reversal→pending]` for a reversal still sitting with the
  user. The three rows iter-2 lost came back in one round, which is the
  evidence that the gap was in the contract rather than in run-to-run variance:
  the run recorded the reversal request and the tracked finding as pending
  ledger lines instead of leaving the ledger silent.

## <a id="the-2026-07-25-round"></a>The 2026-07-25 round (EVAL_MODEL `sonnet`)

The headline table from 2026-07-25 to 2026-08-06, retired when the baseline
moved to `claude-sonnet-5`. It was the first full round after the 2026-07-24
measurement-contract realignment; `section` and `factory` had been rerun under
the rosterless dispatch fallback contract (PR #37), and the other six suites
carried that round forward unchanged.

| Skill | Iter | n | with_skill | without_skill | Δ | Provenance |
|-------|------|---|-----------|---------------|---|-----------|
| `begin` | 1 | 1 | **1.00** | 0.9333 | +0.07 | full assertion set, total (automation) |
| `land` | 1 | 1 | **1.00** | 0.3889 | **+0.61** | full assertion set, total (hybrid) |
| `section` | 1 | 1 | **1.00** | 0.7778 | +0.22 | full assertion set, total; rosterless fallback contract (judgment) |
| `factory` | 1 | 2 | **0.9844 ± 0.0442** | 0.4494 ± 0.2645 | **+0.54** | full assertion set, total; rosterless fallback contract; eval-1 with_skill was initially misgraded by a harness stale-transcript bug, corrected on regrade (judgment) |
| `vibe-diff` | 1 | 1 | **1.00** | 0.3125 | **+0.69** | full assertion set, total (hybrid) |
| `cross-check` | 1 | 1 | **1.00** | 0.25 | **+0.75** | machine subset (judgment) |
| `spec-viewer` | 1 | 1 | **1.00** | 0.125 | **+0.88** | machine subset (automation) |
| `preflight` | 3 | 1 | **1.00** | 0.5555 | **+0.44** | full assertion set, total (judgment) |

`preflight` moved through three rounds inside this stratum. Iteration-2 made
the absent-layer `[caveat]` line a contract and measured it; its triage case
then lost three rows to a single cause, since the run handed the reversal
request and the tracked finding to the user but wrote no ledger line for
either, the tag vocabulary having no state for a ruling still with the user.
Iteration-3 added `[reversal→pending]` and rebuilt the round: all three rows
returned and the suite reached 1.00 against 0.5555. The iteration-1 numbers are
not comparable to either, since that round was scored with an honesty assertion
later removed for passing on a coincidence, and it was never regraded.

**One defect outlived this stratum.** `land` iter-3 (in the per-skill section
above) had already caught the reviewer model going unreported, and iter-4 fixed
it by carrying an `adversarial review: <model>` line into Step 7's summary. The
2026-08-06 round found the same hole in a new shape: the line was present but
filled with the subagent type (`adversarial review: general-purpose`) rather
than the model, because the skill never said what that slot holds when no
`agents/` roster is installed and the reviewer degrades to a plain general
subagent. Fixed in `3cc9579`, which makes the model mandatory and the type an
optional suffix, and confirmed by `land` iteration-3 on an unchanged assertion:
the row flipped green, the run wrote `adversarial review: opus (general-purpose,
no roster)`, and the other two cases held. A fix that closes the case for one
environment can leave the slot ambiguous in another.

**A second finding on the rerun, and the eval was the one that was wrong.**
`preflight` iteration-5 committed the accepted fixes in both scenarios, failing
a lands-no-commits assertion on the same `skill_commit` (`d899536`) and model
that iteration-4 had passed it with. The first reading was that `SKILL.md`
contradicted itself, and the no-commit rule was hardened to match the
assertion. Checking how the two skills actually compose overturned that:
`/land`'s Step 2 scan and Step 4 adversarial review both read
`<base>...HEAD`, so a fix left uncommitted is invisible to both and never
reaches the PR, and `/land`'s Step 5 already says it expects to squash fixup
commits it finds on the branch. Leaving fixes in the tree was the reading that
did not compose. The contract is now explicit in the other direction, preflight
commits each accepted fix as a fixup against what it corrects and stops short
of pushing or opening a PR, and the two assertions that encoded the old
expectation were rewritten with it (`71c2889`).

Two lessons, and the second is the expensive one. A single clean round is not
evidence that a contract holds, because iteration-4 passed on an ambiguity
rather than on compliance. And an assertion is an instrument for measuring a
skill, never a definition of it: this one was specific enough to sound
authoritative, and following it drove a skill change in the wrong direction
before anyone checked whether the neighbouring skill could receive what it
described.

**A rubric cannot turn a semantic judge into a mechanical one.** `begin`
eval-2 carried an `llm_judged` row for "the occupied lane is handled by a
worktree or by stopping", alongside a `head_branch` check that decides the same
property from git state. Across iterations 2 to 5 the machine check was right
every time and the judge was wrong every time, passing a baseline that had run
`git checkout -b` in the shared checkout. Three rubric revisions failed in three
different ways: it read `git checkout -b` as "a real second branch checkout";
then, told that was not a worktree, it argued the run had switched to the
default branch first so it never branched *on* the occupied checkout; then,
given a hard gate to read HEAD first and stop, it read HEAD, acknowledged it was
wrong, and overrode the gate with the reflog. (The second failure was
self-inflicted: the gate was prepended while a clause telling the judge to score
the row as a prose property was left in place, so the rubric contradicted
itself.) The row was deleted in iteration-6, leaving ancestry to the two
judged rows and the shared checkout to `head_branch`, and the verdicts agree
for the first time. The rule this leaves: a property that git state already
decides does not get a second, softer opinion. Related to the `text_contains`
promotion that created this row in the first place, which traded a false
negative for a false positive.

**A note on n.** Removing that row lowered `begin` eval-2's baseline from 0.80
to 0.6667, but the suite's baseline mean still rose (0.5167 to 0.6389), because
eval-1's baseline swung 0.0 to 0.50 between the two rounds on its own. At n=1
the run-to-run swing is larger than the correction, so single-round baseline
movements are not evidence about a fix unless the affected case is read
directly.

