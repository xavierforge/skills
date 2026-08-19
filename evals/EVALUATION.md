# Skill evaluations: results & specification

This directory holds the **behavioral evaluations** for the workflow skills in
this repo, and it is the **single source of truth** for how those evals are
shaped, run, scored, and reported. Each eval measures one thing: **what does the
skill add, at a fixed model, over the same model with no skill?** The reusable,
version-controlled inputs are the case files ([`cases/`](./cases/)) and the
sandbox builder ([`harness/`](./harness/)); the grader / analyzer / aggregator
come from Anthropic's installed `skill-creator` skill.

**Read the numbers first, the method second.** The total table below is the
headline; the per-suite detail follows; ["How the evals work"](#how-the-evals-work)
(schema, check types, discipline, iron rules) sits at the bottom for when you
need it.

## Results: the eight skills

One row per skill. `with_skill` / `without_skill` are pass rates (mean ± stddev
where n > 1); `Δ` is the gain the skill buys. Two measurement regimes coexist
and are **not directly comparable** (see [the note below](#two-regimes)): a
**machine-subset** number scores only the mechanical checks `check.py` decides
(every `llm_judged` row deferred and excluded), while a **full-assertion**
number scores the whole assertion set (the machine checks plus the `llm_judged`
rows, resolved either by the new pipeline's `backfill.py` grader or, historically,
by an older LLM-graded round). Each row says which regime it is and links its
provenance; a backfilled row reports the full-assertion total with the machine
subset in parentheses.

Measured 2026-08-06 at EVAL_MODEL `claude-sonnet-5`, one strictly serial round
over all eight suites (iteration-2 everywhere except `preflight`, which was
already at 3). Every arm ran clean: `rc=0`, no auth or limit signal. Two suites
were then re-measured within the round: `ship` at iteration-3 to verify a fix
this round surfaced, and `preflight` at iteration-5 so its tightened rubric was
the one in force. Every suite with deferred rows has since been backfilled, so
each row reports the full-assertion total with the machine subset in
parentheses; `cross-check` and `spec-viewer` are fully mechanical suites with
nothing to defer, so their single number is already the whole assertion set.

The whole previous table was measured at EVAL_MODEL `sonnet` and is **not
comparable across the model change**; those rounds now live in
[`history.md`](./history.md), result files included.

| Skill | Latest iter | n | with_skill | without_skill | Δ | Provenance |
|-------|-------------|---|-----------|---------------|---|-----------|
| `begin` | 6 | 1 | **1.00** | 0.6389 | +0.36 | full assertion set, total (machine subset 1.00 / 0.4722) ([results](./results/begin/iteration-6/)); eval-2's lane-handling `llm_judged` row was removed after passing the baseline wrongly in three consecutive rounds against the `head_branch` check that decides the same property mechanically, so this round's three verdicts finally agree. Baseline movement between rounds is dominated by run-to-run variance, not by that correction (see history) (automation) |
| `ship` | 3 | 1 | **1.00** | 0.3889 | **+0.61** | full assertion set, total (machine subset 1.00 / 0.4722) ([results](./results/ship/iteration-3/)); iteration-2 scored 0.9167 on one genuine skill defect (eval-2's reviewer-model line); this round re-measured it after the `3cc9579` fix on an unchanged assertion (hybrid) |
| `section` | 2 | 1 | **1.00** | 0.7222 | +0.28 | full assertion set, total (machine subset 1.00 / 0.8056) ([results](./results/section/iteration-2/)) (judgment) |
| `factory` | 2 | 1 | **1.00** | 0.4940 | **+0.51** | full assertion set, total (machine subset 1.00 / 0.7167) ([results](./results/factory/iteration-2/)); eval-1's one-subagent-deep row was graded under an earlier rubric that a do-nothing run satisfied vacuously, since tightened, so the recorded without_skill total is if anything generous and the row's stored `rubric_sha256` no longer matches the case file (judgment) |
| `vibe-diff` | 2 | 1 | **1.00** | 0.25 | **+0.75** | full assertion set, total (machine subset identical) ([results](./results/vibe-diff/iteration-2/)) (hybrid) |
| `cross-check` | 2 | 1 | **1.00** | 0.25 | **+0.75** | whole assertion set; fully mechanical suite, nothing deferred ([results](./results/cross-check/iteration-2/)) (judgment) |
| `spec-viewer` | 2 | 1 | **1.00** | 0.125 | **+0.88** | whole assertion set; fully mechanical suite, nothing deferred ([results](./results/spec-viewer/iteration-2/)) (automation) |
| `preflight` | 6 | 1 | **1.00** | 0.6111 | +0.39 | full assertion set, total (machine subset 1.00 / 0.4167) ([results](./results/preflight/iteration-6/)); first round on the corrected contract, in which preflight commits each accepted fix as a fixup and stops short of pushing. Both with_skill runs scored the whole assertion set, landing a `fixup!` against the commit each fix corrected plus a separate `docs` commit for the ledger, on a clean tree. Not comparable to iterations 4 and 5, which were measured against the superseded lands-no-commits expectation (judgment) |

Two readings this round forced, both of which the backfill decided:

- **The machine subset understates the judgment-class skills.** `factory`'s Δ
  went from +0.28 on the machine subset to +0.51 on the full assertion set, and
  `section`'s from +0.19 to +0.28, because the discriminating assertions are
  exactly the deferred ones. The sharpest case is `factory` eval-3's
  without_skill arm: machine subset 1.00, full assertion 0.3333. The bare model
  passed every mechanical check (commit count, files present) while the grader
  found the plan gate never ran at all.
- **Backfilling does not always widen Δ.** It widened `factory` (+0.28 to
  +0.51) and `section` (+0.19 to +0.28) but narrowed `preflight` (+0.58 to
  +0.39), because there the grader read the bare model's prose more generously
  than the machine checks read its git state. Which way a suite moves is a fact
  about its assertions, not a rule of the method, so read both regimes per
  suite rather than assuming the total is the kinder number.
- **A stronger baseline compresses Δ, and that is not a reason to grow the
  skill.** On `claude-sonnet-5` the without_skill arm reaches 1.00 on
  `factory` eval-2, `factory` eval-3 (machine subset) and `section` eval-2: the
  bare model now refuses correctly on the guard scenarios these cases were
  built for. Per the regime note below, those rows stay as drift sentinels; the
  answer to a compressed Δ is to measure at the cheap tier the skill actually
  dispatches to, not to add rules until the baseline fails again.

Δ measures added capability for skills that teach the model a judgment
structure it lacks. For ritual-automation skills that codify a repetitive
prompt the user would otherwise retype by hand, the real KPI is with_skill
compliance and run-to-run predictability, not Δ; begin's 1.00 with_skill is
that number. Suites split three ways: ritual-automation (begin, spec-viewer),
hybrid where both measures apply (ship, vibe-diff), and judgment-structure
where delta is the measure (cross-check, factory, section, preflight). The
table's Provenance column tags each row automation, hybrid, or judgment to
match.

Some expectations pass on both arms and register a zero Δ; these stay in the
assertion set by design, since they act as compliance guards for the codified
rituals and as sentinels for model drift, not as dead weight to prune.

All eight suites are now on the new pipeline. `vibe-diff` and `cross-check` are
**native** runs of their carved-out suites (current hardened refusal / two-axis
contracts), not a regrade of the retired `review-artifacts` iteration-1 runs,
which is retained as history and context in the
[per-suite section](#per-suite-results). See the directory the table's
Provenance column links for each suite's raw grading, and
[`history.md`](./history.md) for the narrative behind each number and for the
retired rounds.

## Per-suite results

### `factory` (under the driver + check.py, machine subset, prior round)

`factory` iteration-2 holds **1.00 ± 0.00** on the machine subset across all six
runs; the baseline swings **0.50 ± 0.46** (factory/1 0.33/0.67, factory/2 1.0/1.0,
factory/3 0.0/0.0), the variance the n=2 round was added to expose. On the
iteration-1 **total-row miss**: that round's transcripts were observed to show an
explicit `total` wall-time row (3m 32s / 3m 55s) closing both factory/1 with_skill
ledgers, but that evidence lives only in the (gitignored) run workspace, so the
**formal verdict awaits the `llm_judged` supplemental grader** folding it into
`grading.json`: the assertion is judgment-graded and deferred by check.py. All
twelve runs recorded `rc=0` / `stderr_scan=clean`. Results are regenerated by
rerunning the suite; see [`history.md`](./history.md#factory) for this round's
narrative.

### `review-artifacts` iteration-1: the split's history (machine subset)

The `review-artifacts` suite was **dissolved** into per-skill suites (`ship/3`,
`vibe-diff/1`, `cross-check/1`) so every suite names one skill. Its
iteration-1 grading was recorded, then dropped with the rest of the
pre-2026-07-24 result sets; [`history.md`](./history.md) carries its narrative
under `vibe-diff` and `cross-check`. Those two suites have **since been run
natively** under their own hardened contracts, so this table is now history and
provenance, not the live source for those rows:

| Eval (old id) | now in suite | with_skill | without_skill |
|---------------|--------------|-----------|---------------|
| ship-step0-reconciliation | `ship/3` | 2/2 | 1/2 |
| vibe-diff-no-spec-source-refusal | `vibe-diff/1` | 4/4\* | 3/4\* |
| cross-check-two-axis-verdict | `cross-check/1` | 4/4 | 2/4 |

\*eval-2 was **re-specified to the hardened refusal contract** after this round
ran (commit `e8bf4fb`). The `iteration-1` grading held the pre-rewrite
`fallback-landing` scoring (with_skill 1/3) before it was dropped with the rest
of the pre-2026-07-24 result sets; the values above are the **regrade of
the same retained runs** under the current case file, condensed in
[`history.md`](./history.md#vibe-diff). The next `vibe-diff` round records the
new contract natively.

### Historical full-assertion rounds (`begin` / `ship` / `section`, pre-checker)

All three have **since been run under `check.py`** (begin and ship at
iteration-4, with their `llm_judged` rows backfilled into a full-assertion total;
section at iteration-4, machine subset); those new-pipeline rounds are the ones
condensed in [`history.md`](./history.md). What this section retains is the **earlier full-assertion
LLM-graded rounds** on their entries in [`history.md`](./history.md)
([`begin`](./history.md#begin), [`ship`](./history.md#ship),
[`section`](./history.md#section)), which predate the
checker and stay as history. Across those rounds the skills held ~100% with the
whole spread in the baseline, because a capable model already nails happy paths
unaided and the skills' measured value concentrates in the guard scenarios a bare
model gets wrong. `section`'s delta triples on its target cheap tier (Haiku
iteration-3, **+0.38**, vs Sonnet iteration-2 **+0.14**), which is why its
historical note cites the Haiku round. Read each page for the scenario-by-scenario
story and the cost (the skills trade time and tokens for correctness).

### `spec-viewer`: new suite

Two mechanical cases (`cases/spec-viewer.json`): (1) render a single OpenSpec
change to `review.html` (file exists, size floor, no external HTTP resource,
real content), and (2) generate a zh-TW gloss (`gloss.zh-TW.json` structure and
entry count, re-embedded page). **iteration-1** (Sonnet, n=1): with_skill
**1.00** vs without_skill **0.13** (Δ+0.88), the widest gap in the table, since
driving the generator and authoring a gloss is work a bare model does not do
unprompted; both new check types (`file_size`, `json_check.min_keys`) decided on
live runs. Results are regenerated by rerunning the suite; see
[`history.md`](./history.md#spec-viewer) for this round's narrative.

### <a id="two-regimes"></a>Why the two regimes are reported separately

A fresh **new-pipeline** round scores only the **machine subset**: `check.py`
defers every `llm_judged` row (`passed: null`) and excludes it from the rate, so
on its own it is not a full-assertion score. A later `backfill.py` pass (see
[How `llm_judged` is resolved](#how-llm_judged-is-resolved)) resolves those
deferred rows and records a **full-assertion total** alongside the machine
subset, never mixed into one number: `summary.pass_rate` stays the machine
subset, `summary.total_pass_rate` is the total. Both are committed to
`results/<suite>/iteration-N/` (Claude Sonnet), each with a fingerprint carrying
`checker_sha256`, the per-arm `skill_commit`, the `execution` record (rc + stderr
auth/limit scan), and, once backfilled, the separate `grader` block. The
**historical per-suite-page** numbers were full-assertion LLM-graded rounds
predating the checker, and stay as history.

## How the evals work

### The eight suites

| Suite | Skill under test | Scenarios | Page |
|-------|------------------|-----------|------|
| [`begin`](./history.md#begin) | `begin` | 3 | dirty-tree guard, occupied-lane new work, clean maintainer-named |
| [`ship`](./history.md#ship) | `ship` | 3 | on the default branch, ready-to-ship, Step 0c reconciliation |
| [`section`](./history.md#section) | `section` | 3 | happy one-section, two active changes, dispatch annotation |
| [`factory`](./history.md#factory) | `factory` | 4 | full three-section loop, no-active-change refusal, plan-gate rewrite, parallel-group lane hand-off |
| [`vibe-diff`](./history.md#vibe-diff) | `vibe-diff` | 2 | no-spec-source refusal (hardened contract), mini-spec happy path |
| [`cross-check`](./history.md#cross-check) | `cross-check` | 1 | two-axis (standards + spec) verdict artifact |
| [`spec-viewer`](./history.md#spec-viewer) | `spec-viewer` | 2 | render a change page, generate a zh-TW gloss |
| [`preflight`](./history.md#preflight) | `preflight` | 2 | triage three findings against Non-Goals and the decision ledger, honest not-run reporting with a ledger caveat line per absent layer |

One suite per skill: every suite's top-level `skill_name` is the single skill it
tests. The `vibe-diff` and `cross-check` suites were carved out of the former
cross-skill `review-artifacts` suite (its `ship` Step 0c case moved into `ship`);
their historical round is recorded in [`history.md`](./history.md) under each
suite's own heading. `vibe-diff`'s eval-2 and `factory`'s eval-4 are the newest
additions, covering the mini-spec happy path and the parallel-group lane
hand-off respectively.

### What every eval measures

Each scenario runs in its **own isolated, offline git sandbox** built to a
specific precondition (a dirty tree, an occupied feature lane, a repo whose
default branch is `trunk`, a branch ready to ship, …). For that sandbox we run
the skill's task prompt under two **arms** on the same cheap model:

- **with_skill**: told to read and follow the skill's `SKILL.md`.
- **without_skill** (baseline): the same task prompt, no skill.

A grader then scores each run against the eval's `expectations`. Machine checks
judge the **resulting git state and the run's own outputs** rather than
trusting the executor's narration; genuine judgment calls are handed to
`skill-creator`'s grader. Scores are aggregated into `mean ± stddev` per arm
with a `Δ` column.

**Safe mode is load-bearing.** Every executor run is launched with `claude
--safe-mode`, which loads **no ambient context** (no user or project
`CLAUDE.md`, no auto-memory, no settings-driven instructions). This keeps the
two arms differing by exactly one variable: this repo's global `CLAUDE.md`
carries commit-discipline and delegation rules that overlap with what the
skills enforce, so auto-injecting it would silently hand the baseline the same
guidance and make the skill look weaker than it is. The skill's `SKILL.md`,
fed explicitly to the `with_skill` arm, becomes the **only** difference.
Corollary: when a `SKILL.md` itself says to *read* an `AGENTS.md`/`CLAUDE.md`
in the repo (e.g. `ship` derives commit discipline that way), that file is
still present in the sandbox and readable on demand; safe mode removes the
ambient auto-load, not the skill's own explicit lookups.

#### How the skill reaches the `with_skill` arm

There is **no skill install and no auto-load**. The `with_skill` arm is handed
the absolute path to `skills/<skill_under_test>/SKILL.md` in its prompt and told
to read and follow it (resolving any `<skill-base>` script references against
that skill's directory in the repo checkout); `without_skill` gets the bare
task. The skill files live in the repo checkout *outside* the sandbox, and the
executor reads them explicitly. This is why a probe showing `--safe-mode` does
not load a project's `.claude/skills/` is **not** in tension with past
`with_skill` runs "having" the skill: those runs never relied on the
`.claude/skills/` registry or on auto-load at all. Safe mode disables ambient
auto-load; it never blocks an explicit `Read` of a file sitting in the
checkout. `run_eval.sh` implements exactly this: the arm is launched as `claude
--safe-mode --dangerously-skip-permissions --model <cheap> -p <prompt>`, and the
`with_skill` prompt names the `SKILL.md` path. Nothing is copied into any skills
registry.

Network isolation is **instruction plus fixture, not enforcement**: the executor
runs under `--dangerously-skip-permissions`, so no permission layer blocks a
network command. `git push` is inert because `origin` is a local bare repo, but
`gh` / `curl` are only *forbidden by the executor ground rules*, not sandboxed;
keep these runs on disposable checkouts. Do not read this as a hard guarantee
that nothing can leave the machine.

### Schema v1: `skills-eval/1`

Case files (`cases/<suite>.json`) are the **canonical, version-controlled**
statement of each eval. This is the schema; the checker (`harness/check.py`)
is its only interpreter.

```json
{
  "schema": "skills-eval/1",
  "skill_name": "<suite name>",
  "evals": [
    {
      "eval_id": "<stable kebab id>",
      "skill_under_test": "<skill>",        // optional; defaults to skill_name
      "prompt": "<the user turn, verbatim>",
      "fixture": "<suite>/<n>",             // key into harness/build_sandbox.sh
      "arms": ["with_skill", "without_skill"],
      "expected_output": "<one-paragraph human summary>",
      "expectations": [
        {"text": "<human-readable assertion>", "check": { "type": "...", ... }}
      ]
    }
  ]
}
```

Every expectation pairs the **human-readable `text`** (what a reviewer reads)
with a **typed `check`** (what the checker evaluates). The principle:
**anything a machine can decide gets a machine check; only genuine judgment is
left to `llm_judged`**, and each `llm_judged` records *why* in its rubric.

#### Check-type vocabulary

The checker resolves paths as follows: `file_*`, `json_check`, and
`changes_confined_to` operate on the **sandbox git tree**; `text_contains`
operates on the **run's own output artifacts** (`result.md`, `transcript.md`,
`PR_BODY.md`) selected by `source`. `git_log_count`'s default `base` is the
fixture's initial commit (the state before the run).

**Git / filesystem state (sandbox after the run):**

| Type | Fields | Passes when |
|------|--------|-------------|
| `git_log_count` | `base?`, `range:[min,max]` | commits added on HEAD beyond `base` fall in range |
| `commit_subject` | `which:"head"\|"added"`, `regex` | the tip subject (`head`) or every added subject (`added`) matches `regex` |
| `head_branch` | `equals?` \| `regex?` | the current checked-out branch name matches |
| `branch_exists` | `name`, `expect?:true` | the named local branch is present (absent if `expect:false`) |
| `branch_count` | `range:[min,max]` | the number of local branches falls in range |
| `is_ancestor` | `ancestor`, `descendant` | `ancestor` is reachable from `descendant` |
| `ref_equals` | `left`, `right` | both refs resolve to the same commit (fast-forward check) |
| `git_clean` | `expect?:true` | the working tree is clean (`expect:false` = must remain dirty) |
| `git_no_stash` | none | the stash list is empty |
| `file_exists` | `path?` \| `paths?`, `expect?:true` | the file(s) exist (absent if `expect:false`) |
| `file_size` | `path`, `min_bytes?`, `max_bytes?` | the file exists and its byte size is within the given bound(s) |
| `file_contains` | `path`, `needle?`\|`needles?`\|`regex?`\|`regexes?`, `present?:true` | the file matches (all `needles`/`regexes` required; `present:false` negates) |
| `json_check` | `path`, `min_keys?`, `has_keys?`, `absent_keys?`, `equals?:{dotted:val}`, `array?:{path,has_keys?,enum?}` | the JSON parses and satisfies the given structural asserts (`min_keys`: top-level object has at least N keys) |
| `changes_confined_to` | `prefix` | every path reported by `git status` lives under `prefix` |

**Run output (the arm's own reply/transcript):**

| Type | Fields | Passes when |
|------|--------|-------------|
| `text_contains` | `source:"result"\|"transcript"\|"pr_body"\|"any"`, `needle?`\|`needles?`\|`regex?`\|`regexes?`, `present?:true` | the selected artifact matches (all `needles`/`regexes` required; `present:false` negates) |

**Judgment fallback:**

| Type | Fields | Behavior |
|------|--------|----------|
| `llm_judged` | `rubric` | `check.py` defers it (`passed: null`); an optional later `skill-creator` grader pass folds a verdict into the same `grading.json` (see "How `llm_judged` is resolved") |

The vocabulary is **open**: new machine types may be added in later batches
(the checker is the one place that learns them), and an `llm_judged`
expectation is promoted to a machine check the moment one becomes decidable.

#### How `llm_judged` is resolved

`check.py` is deterministic and calls no model, so it **defers** every
`llm_judged` expectation rather than judging it: the row is written with
`passed: null`, an evidence string flagging the deferral, and the expectation's
`rubric` carried alongside. The normalize pass excludes `null` rows from the
summary counts, so a deferred expectation is never scored as a failure (a run
with only machine checks decided reports e.g. `2/2`, not `2/4`). Because the
grading is deterministic, `fingerprint.checker_sha256` fully identifies the
machine verdicts.

The judgment itself is a **separate, optional supplemental pass**, run by
`harness/backfill.py <suite> <iteration>` in the **main loop** (never a
subagent), not by `check.py`. This is why the run **workspace is retained** (the
gitignored `skills/<suite>/<suite>-workspace/…`, holding each run's
`transcript.md` + `outputs/`): a deferred row can be filled later without a
re-run. `backfill.py` touches **only** the `passed: null` `llm_judged` rows,
leaving machine rows, `checker_sha256`, and every existing fingerprint field
untouched. It judges each deferred row with **one `claude -p` call** (the
subscription, cheap tier, offline, strictly serial, stopping on any limit), fed
the row's `text` plus `rubric` and the run's own `result.md`, `transcript.md`,
and `git-state.txt`, then merges the returned `{passed, evidence}` back into the
**same** `grading.json` with `verdict_source: "grader"`. (skill-creator's
`agents/grader.md` is **not** used for this: it overwrites the whole file and
carries no fingerprint, which would erase the machine verdicts and provenance
this design keeps separate.)

Because the grader is an LLM, the pass **records its identity in a separate
`fingerprint.grader` block**, distinct from `checker_sha256`, so a mechanical
verdict and a model-judged one are never conflated. That block is a **fixed
schema**, not an illustration:

```json
"grader": {"model": "<model>", "rubric_sha256": "<sha256 of this run's llm_judged (text, rubric) rows>", "harness_commit": "<short HEAD>"}
```

The summary then carries both regimes **side by side**: `summary.pass_rate` (with
its `passed` / `failed` / `total`) still means the **machine subset**, name and
semantics unchanged, while backfill adds `summary.total_pass_rate` (with
`total_passed` / `total_decided`) over machine plus grader rows and folds a
`run_summary_total` block into `benchmark.json`. Until a suite's deferred rows are
backfilled, its `llm_judged` rows stay `null` and are reported as deferred; once
backfill covers them, that suite's total-table row switches to the `total` number,
with the machine subset shown in parentheses.

### The fingerprint block

Every `grading.json` **must** carry a `fingerprint` so a result can be traced
to exactly what produced it. It is stamped automatically by `run_eval.sh`
(`harness/run_eval.sh`), whose normalize pass runs after every grader:

```json
"fingerprint": {
  "checker_sha256": "...", "harness_commit": "...",
  "skill_name": "...", "skill_commit": "...", "iteration": 2,
  "model": "claude-sonnet-...", "runs": 1,
  "timestamp": "...", "environment": "local",
  "grader": {"model": "...", "rubric_sha256": "...", "harness_commit": "..."}
}
```

The `grader` sub-block is present **only after** a `backfill.py` pass has folded
`llm_judged` verdicts into that run; a machine-only round omits it, and its
`rubric_sha256` (identity of the rubrics judged) is kept separate from
`checker_sha256` (identity of the deterministic checker) on purpose.

### The driver and the skill-creator contract

`harness/run_eval.sh <skill> <eval_id> [runs] [iteration]` runs the whole
pipeline for one eval (or `all`): build the sandbox, run each arm, snapshot git
state, grade, normalize, aggregate, and harvest. It is a **thin shell over the
reproducible triad plus skill-creator's benchmark tools**: it adds no grading
intelligence of its own.

Grading routes through `harness/check.py`, the universal checker and **sole
grader** for every suite: it interprets each expectation's typed `check`
against the sandbox git tree and the run's own outputs, deciding every machine
check and deferring `llm_judged` rows (`passed: null`) to a `skill-creator`
grader pass that folds its verdict into the same `grading.json`. A **normalize
pass** then guarantees the contract skill-creator's tools require: every
`grading.json` carries `summary.{pass_rate,passed,failed,total}` and
`expectations[{text,passed,evidence}]`, plus the fingerprint above. Undecided
expectations (`passed: null`) are excluded from the summary counts rather than
scored as failures.

skill-creator contributes only the **aggregate** (`aggregate_benchmark.py`) and
the **viewer** (`eval-viewer/generate_review.py`). Both are directory-contract
consumers: they read `iteration-N/eval-*/<arm>/run-*/grading.json` plus
`eval-*/eval_metadata.json` (and, for the viewer, `outputs/`). They never touch
the sandbox git tree, so there is no scaffold to reconcile: our own sandbox
shape is invisible to them, and a `grading.json` written at the run level
satisfies both. `run_eval.sh` locates skill-creator automatically (override with
`SKILL_CREATOR_DIR`). `harness/snapshot.sh` stays as the driver's git-state
recorder: its `git-state.txt` lands in each run's `outputs/` as human- and
viewer-visible evidence.

### Iteration policy

Iterations are numbered **per skill** (`results/<skill>/iteration-N/`). Every
round records the **git hash of the skill under test at that time**
(`fingerprint.skill_commit`); cross-skill comparability comes from that hash,
not from a shared iteration counter. A skill at iteration-3 and another at
iteration-1 are compared by what their recorded commits were, never by number.

### Baseline (arm) policy

The **standard form** is `with_skill` vs `without_skill` with a `Δ` column;
that is what `arms` declares in every case file. An `old_skill` arm (the
skill's prior `SKILL.md`, frozen with `git archive <ref> skills/<name>`) is
**optional**: it exists only for the one round that validates a skill upgrade
against a regression, is built ad hoc for that round, and is **called out
explicitly in the report**. It is never a standing fixture and is not encoded
as a default arm. (The `review-artifacts` suite's iteration-1 numbers were
measured against an `old_skill` main snapshot for the two modified skills; that
was such a regression round, recorded as history on its page.)

### Reproducibility: the iron rules

1. **The reproducible triad is version-controlled.** A run is defined by three
   things and all three live in git: the **case** (`cases/<suite>.json`), the
   **fixture** (`harness/build_sandbox.sh`), and the **driver**
   (`harness/run_eval.sh`). If a scenario cannot be rebuilt from these, it is
   not an eval.
2. **Execution environments are disposable.** Codespaces, the scratchpad, and
   worktrees are throwaway. Anything that lives *only* inside an execution
   environment is treated as if it does not exist.
3. **Only small JSON comes home.** The one thing a completed round brings back
   into the repo is its `grading.json` plus the fingerprint block
   (`results/<skill>/iteration-N/`). Per-run sandboxes, transcripts, and
   benchmark blobs are regenerable and **gitignored** (`skills/*/*-workspace/`).
4. **No round, no citation.** If a round's `grading.json` + fingerprint cannot
   be brought back, the round is treated as never having run, and no report may
   cite its numbers.

> Why rule 1 exists: `review-artifacts`'s original sandbox was hand-built
> inside Codespaces and never version-controlled. When that environment went
> away the whole suite became unreproducible. The fixtures now live in
> `build_sandbox.sh` precisely so that cannot recur.

### Executor ground rules

These are the standing instructions handed to every executor subagent
(previously `harness/EXEC_RULES.md`, now folded here):

> You are running ONE task inside an ISOLATED, OFFLINE git sandbox as part of a
> skill benchmark. You are launched with `claude --safe-mode`: no ambient
> context is loaded (no user/project `CLAUDE.md`, no auto-memory, no
> settings-driven instructions), so both arms start from the same blank slate
> and the skill under test is the only variable. Follow these rules:
>
> - Your working directory is the sandbox path given in your prompt. `cd` into
>   it first and operate ONLY inside it. The only files you may read outside it
>   are the skill files your prompt explicitly points you at.
> - OFFLINE: the `origin` remote (when present) is a local bare repo, so `git
>   fetch` is fine, but NEVER run `git push`, `gh`, or any real-network
>   command. When the workflow reaches a push / `gh pr create` step, STOP and
>   report the exact command you WOULD run; do not attempt it.
> - Treat the task prompt as if a user typed it to you in this repo. You are on
>   the cheap execution model.
> - If your prompt names a skill to follow, read that SKILL.md and follow it
>   exactly, resolving any `<skill-base>` script references against the base dir
>   given. If no skill is named, use your own best judgment (baseline).
> - You have the Agent/Task tool if the workflow calls for dispatching a
>   subagent; if you dispatch one, note which model you used.
> - The project quality gate, when relevant, is `make check` (see AGENTS.md).
>
> When finished (or when you stop to ask/block), write into the outputs dir
> given:
> 1. `transcript.md`, honest narration: the key git/test commands you ran with
>    essential output, decision points, and, if you stopped to ask/block, the
>    exact question or block message you'd give the user, quoted. Note what you
>    deliberately did NOT do and why.
> 2. `result.md`: your final user-facing reply.
> 3. (ship only) `PR_BODY.md`: the PR body you composed, if any.
>
> Leave the git repo in its final state (do not clean up or revert). Reply with
> a 2-3 sentence summary.

### Execution discipline

- Runs go through the **subscription**, not the API: `ANTHROPIC_API_KEY` must
  be unset for the duration.
- **Strictly serial**, cheapest scenario first as a sentinel. On any `401` /
  `429` / rate-limit or usage-cap signal, **stop immediately** and report; do
  not retry or fan out.
- A nested `claude -p` invocation always runs in the **main execution loop**,
  never inside a subagent prompt: the safety classifier blocks
  `--dangerously-skip-permissions` when it appears inside a subagent (observed
  twice).
- If a load-bearing assumption breaks, **stop and report** rather than
  inventing a workaround on the spot.

### Target layout

```
evals/
  EVALUATION.md              this file: results + schema/rules single source
  cases/<suite>.json         schema v1: scenarios + typed expectations
  harness/build_sandbox.sh   sandbox construction (one case per fixture key)
  harness/run_eval.sh        thin one-shot driver (build -> arms -> grade -> aggregate)
  harness/snapshot.sh        post-run git-state recorder (evidence in outputs/)
  harness/check.py           the one general checker (sole grader; interprets schema v1)
  results/<skill>/iteration-N/   grading.json + benchmark.json (small JSON only)
  history.md                  condensed development trail per suite (supersedes the old per-suite <suite>-eval.md pages)
```

---

For the condensed development trail of each skill (measurements taken before the
2026-07-24 contract re-alignment, with their result files removed), see
[`history.md`](./history.md).
