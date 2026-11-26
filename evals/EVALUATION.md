# Skill evaluations: results & specification

[繁體中文](EVALUATION.zh-TW.md)

In short: this directory holds the **behavioral evaluations** for the repo's
workflow skills, and it is the **single source of truth** for how those evals
are designed, run, scored, and reported. Every eval asks one question: **at a
fixed model, what does having the skill installed add over not having it?**
The version-controlled inputs are the case files ([`cases/`](./cases/)) and
the harness ([`harness/`](./harness/)); the aggregation and review tooling is
taken directly from Anthropic's `skill-creator` skill.

Recommended reading order: numbers first, method second. The cross-harness
table below is the headline; the plumbing (schema, check types, discipline,
iron rules) all sits in ["How the evals work"](#how-the-evals-work) at the
bottom, for when you want to dig.

## Results: the cross-harness comparison (2026-08-28)

The suite now runs under **two executors**: Claude Code (`claude -p` with
`EVAL_MODEL=sonnet`) and Codex (`codex exec` with `EVAL_MODEL=gpt-5.6-terra`,
enabled via `EVAL_EXECUTOR=codex`). This round ran all eight suites once on
each executor (one run per arm), with identical case files, an identical
harness, and the same backfill judge (`sonnet` on both).

One thing to note: the four codex suites carrying dispatch assertions
(`land`, `section`, `factory`, `preflight`) were measured with the
[role roster](../agents/README.md) installed in `~/.codex/agents/`, so the
collab `spawn` tool had named roles to hand work to; the other four suites
carry no dispatch assertions and are unaffected by the roster.

Numbers are full-assertion totals (machine checks plus backfilled `llm_judged`
rows), shown as passed/total. Each suite's raw grading sits in
`results/<suite>/iteration-N/` at the iteration numbers in the table (Claude
Code / Codex).

| Skill | Iter (cc/cx) | Claude with | Claude w/o | Codex with | Codex w/o |
|-------|--------------|-------------|------------|------------|-----------|
| `begin` | 9 / 8 | **11/11** | 6/11 | **11/11** | 8/11 |
| `land` | 6 / 7 | 13/14 | 7/14 | 13/14 | 7/14 |
| `section` | 4 / 5 | **14/14** | 10/14 | **14/14** | 10/14 |
| `factory` | 4 / 5 | 18/22 | 6/22 | 11/22 | 8/22 |
| `vibe-diff` | 4 / 3 | **12/12** | 2/12 | **12/12** | 3/12 |
| `cross-check` | 4 / 3 | 3/4 | 1/4 | 3/4 | 1/4 |
| `spec-viewer` | 4 / 3 | **8/8** | 1/8 | **8/8** | 1/8 |
| `preflight` | 11 / 12 | **15/15** | 8/15 | 14/15 | 7/15 |
| **Total** | | **94/100** | 41/100 | **86/100** | 45/100 |

On the machine-judged subset alone the two executors sit close: `with_skill`
is 66/69 (Claude) vs 63/69 (Codex); the baselines (no skill) 29/69 vs 32/69.
Which shows the skills' value holds across platforms: **+0.53 on Claude
Code, +0.41 on Codex**, with the two baselines close as well (41/100 vs
45/100).

As for why points were lost, the reasons are these:

- **Codex `factory` stuck at the plan-approval gate (nearly all of its 11
  lost points)**: the eval-1 and eval-4 runs stopped at the gate to wait for
  user approval, but an eval is an automated script with no one to answer
  it, so not a single round ran and the downstream assertions (rounds,
  ledger, `/opsx:verify`, the lane plan) fell with it.
- **`factory` eval-2, both platforms, both arms**: the refusal neither says
  the skill serves OpenSpec projects only nor points at proposing a change
  first. A wording gap in the SKILL.md prompt.
- **Claude `factory`, two rows**: the transcript the judge read was cut
  short before the later dispatches and the final ledger appeared. Read
  those two rows as a lower bound, not as work left undone.
- **The rest is the baseline failing where it was expected to**: doing the
  work inline instead of dispatching, picking a change without asking the
  user, fanning out where lanes belong to the user. That spread is exactly
  Δ (the improvement the skill buys).

Note that dispatch itself loses no points on either side: Codex spawns the
roster roles through its collab tool (a section annotated `sai-hu` really
does go to a `sai-hu` child). Dispatch is judged from the records each spawn
leaves behind (details under "The Codex executor's particulars" below). With
the dispatch-related rows removed, `with_skill` is 88/92 (Claude) vs 82/92
(Codex).

### <a id="round-caveats"></a>Comparability with earlier rounds

Executor prompts issued between 2026-07-19 and 2026-08-27 carried **no ground
rules**: a documentation restructure demoted the heading the harness extracts
them from, and the extraction silently returned an empty string until the
anchor was made heading-agnostic (with an abort on empty extraction). Rounds
on either side of that boundary are therefore **not same-condition** and are
not compared numerically. `with_skill` results were barely affected, since
the skills carry most of those constraints in their own text, so earlier
conclusions stand; the superseded 2026-08-06 table remains in git history and
[`history.md`](./history.md).

A first codex measurement of the four dispatch-bearing suites (iterations
`land/5`, `section/3`, `factory/3`, `preflight/10`) ran before the role
roster existed in the execution environment, when the collab `spawn` tool
exposed zero agent types and dispatch was impossible by construction. Those
iterations were superseded by the post-roster re-measurement in the table
above and removed from `results/`; git history retains them.

### Reading Δ (the improvement)

Δ measures whether a skill gives the model a structured judgment it lacks;
in other words, added capability.
For skills that codify a repeated ritual (ritual-automation, e.g. `begin`,
`spec-viewer`), the real KPI is compliance and run-to-run stability with the
skill on, not Δ.

By that standard the eight suites fall into three classes:

1. **Ritual-automation** (`begin`, `spec-viewer`)
2. **Hybrid** (`land`, `vibe-diff`)
3. **Judgment-structure** (`cross-check`, `factory`, `section`,
   `preflight`) — only this class is read by Δ.

Some rows pass on both arms (zero Δ) on purpose: they are sentinels watching
whether the model still follows the ritual and whether it has quietly
drifted, not dead-weight rows. And when a smarter baseline compresses Δ,
that is no license to pile on rules until the baseline fails again; the
right move is to measure on the cheap model the skill actually dispatches
to.

### The Codex executor's particulars

Setting `EVAL_EXECUTOR=codex` routes every arm through `codex exec` instead
of `claude -p`, with all the discipline unchanged:

- **Vendor subscription only, never an API key**: the Claude executor
  requires `ANTHROPIC_API_KEY` and its siblings unset; Codex likewise
  requires `OPENAI_API_KEY` unset and goes through the ChatGPT login. Codex
  mode also demands an explicit `EVAL_MODEL`.
- **Hermetic launch**: `codex exec --ignore-user-config --skip-git-repo-check
  --dangerously-bypass-approvals-and-sandbox --json` (the counterpart of
  Claude's safe mode). One trap to know about: `--ignore-user-config` does
  **not** hide `~/.codex/agents/` — with a role roster installed, codex arms
  can see it. Both arms of one executor see the same environment, so
  within-executor Δ is unaffected; keep it in mind when comparing rounds
  across a roster install.
- **The same evidence contract**: `result.md` and `transcript.md` are rebuilt
  unconditionally from `codex.stream.json`, the run's authoritative record.
- **Limit signals and capacity overload are handled differently**: a
  `401`/`429`/quota signal stops the whole batch, no forced retry (same as
  the Claude side). The one exception is the provider reporting "model is at
  capacity": a mid-turn transient that dies without producing any output,
  retryable with spacing, because a failed turn leaves nothing behind to
  inflate a score with.
- **Dispatch evidence lives only in session rollouts, never in the stream**:
  the collab `spawn` tool can only summon agents present in
  `~/.codex/agents/`. But the `--json` report shows a spawn only as a
  receiverless `wait` tag; what the child agent actually did all sits in its
  rollout file under `$CODEX_HOME/sessions` (matched via
  `parent_thread_id`). `harness/codex_transcript.py` harvests those rollouts
  into the transcript's `[dispatch]` records, and that is what the judge
  scores from.

## History and the two scoring regimes

The earlier historical rounds (the 2026-08-06 table, the old rounds where an
LLM was the whole grader, and the rest) are condensed into
[`history.md`](./history.md). Two scoring regimes appear there, and they
must **never be mixed in a comparison**:

- A freshly finished round carries only the **machine subset (pure machine
  verdicts)**: `check.py` marks every row needing human-or-LLM judgment
  (`llm_judged`) as `passed: null`, deferred and excluded from the rate.
- A later `backfill.py` pass hands the deferred rows to an LLM and records a
  **full-assertion total**; the two sit side by side, never merged:
  `summary.pass_rate` is the machine score, `summary.total_pass_rate` the
  combined total.

The hard-won lessons from those rounds still apply: the pure machine subset
always understates judgment-class skills (the hardest calls are exactly the
deferred ones), and backfill can widen or narrow Δ, so read both numbers. A
capable model handles the happy path on its own; a skill's real value is
whether the guardrails hold when the model gets it wrong.

## How the evals work

### The nine suites

| Suite | Skill under test | Scenarios | Page |
|-------|------------------|-----------|------|
| [`begin`](./history.md#begin) | `begin` | 3 | dirty-tree guard, occupied-lane new work, clean maintainer-named |
| [`land`](./history.md#land) | `land` | 3 | on the default branch, ready-to-land, Step 0c reconciliation |
| [`section`](./history.md#section) | `section` | 3 | happy one-section, two active changes, dispatch annotation |
| [`factory`](./history.md#factory) | `factory` | 4 | full three-section loop, no-active-change refusal, plan-gate rewrite, parallel-group lane hand-off |
| [`vibe-diff`](./history.md#vibe-diff) | `vibe-diff` | 2 | no-spec-source refusal (hardened contract), mini-spec happy path |
| [`cross-check`](./history.md#cross-check) | `cross-check` | 1 | two-axis (standards + spec) verdict artifact |
| [`spec-viewer`](./history.md#spec-viewer) | `spec-viewer` | 2 | render a change page, generate a zh-TW gloss |
| [`preflight`](./history.md#preflight) | `preflight` | 2 | triage three findings against Non-Goals and the decision ledger, honest not-run reporting with a ledger caveat line per absent layer |
| `retro` | `retro` | 3 | not yet run: first occurrence recorded only, second occurrence proposes and stops for approval, unevidenced claim dropped |

Each suite's top-level `skill_name` names the one skill it concentrates on.

### What each eval actually measures

Every scenario runs in its **own isolated, offline git sandbox**, built to a
prescribed state (a dirty tree, an occupied lane, and so on). On the same
sandbox, the same model runs two **arms**:

- **with_skill**: told to read the skill's `SKILL.md` and follow it.
- **without_skill** (baseline): the task prompt only, no skill, left to its
  own devices.

Machine checks judge the **resulting git state and the run's own outputs**
rather than trusting the executor's narration; genuine judgment calls are
deferred to the backfill grader.

**The hermetic launch is load-bearing.** Every executor runs with ambient
context stripped (`claude --safe-mode`; `codex exec --ignore-user-config`):
no user or project instructions, no auto-memory. This keeps the two arms
differing by exactly one variable; this repo's global instructions carry
commit-discipline rules that overlap with what the skills enforce, and
auto-injecting them would silently hand the baseline the same guidance. When
a `SKILL.md` itself says to *read* an `AGENTS.md` in the repo, that file is
still present in the sandbox and readable on demand: hermetic launch removes
ambient auto-load, not the skill's own explicit lookups.

**How the skill reaches the `with_skill` arm**: there is no skill install and
no auto-load. The `with_skill` prompt names the absolute path to
`skills/<skill_under_test>/SKILL.md` and says to read and follow it,
resolving `<skill-base>` references against that skill's directory in the
repo checkout; `without_skill` gets the bare task. Nothing is copied into any
skills registry, and hermetic mode never blocks an explicit read of a file
sitting in the checkout.

**Network isolation is instruction plus fixture, not enforcement**: the
executor runs with permissions bypassed, so no layer blocks a network
command. `git push` is inert because `origin` is a local bare repo, but `gh`
and `curl` are only *forbidden by the executor ground rules*; keep these runs
on disposable checkouts.

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

Every expectation pairs the **human-readable `text`** with a **typed
`check`**. The principle: **anything a machine can decide gets a machine
check; only genuine judgment is left to `llm_judged`**, and each `llm_judged`
records *why* in its rubric.

#### Check-type vocabulary

The checker resolves paths as follows: `file_*`, `json_check`, and
`changes_confined_to` operate on the **sandbox git tree**; `text_contains`
operates on the **run's own output artifacts** (`result.md`, `transcript.md`,
`PR_BODY.md`) selected by `source`. `git_log_count`'s default `base` is the
fixture's initial commit.

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
| `json_check` | `path`, `min_keys?`, `has_keys?`, `absent_keys?`, `equals?:{dotted:val}`, `array?:{path,has_keys?,enum?}` | the JSON parses and satisfies the given structural asserts |
| `changes_confined_to` | `prefix` | every path reported by `git status` lives under `prefix` |

**Run output (the arm's own reply/transcript):**

| Type | Fields | Passes when |
|------|--------|-------------|
| `text_contains` | `source:"result"\|"transcript"\|"pr_body"\|"any"`, `needle?`\|`needles?`\|`regex?`\|`regexes?`, `present?:true` | the selected artifact matches (all `needles`/`regexes` required; `present:false` negates) |

**Judgment fallback:**

| Type | Fields | Behavior |
|------|--------|----------|
| `llm_judged` | `rubric` | `check.py` defers it (`passed: null`); a later `backfill.py` pass folds a verdict into the same `grading.json` |

The vocabulary is **open**: new machine types may be added (the checker is
the one place that learns them), and an `llm_judged` expectation is promoted
to a machine check the moment one becomes decidable.

#### How `llm_judged` is resolved

`check.py` is deterministic and calls no model, so it **defers** every
`llm_judged` expectation: the row is written with `passed: null` and its
rubric carried alongside, excluded from the summary counts rather than scored
as a failure. Because grading is deterministic,
`fingerprint.checker_sha256` fully identifies the machine verdicts.

The judgment is a **separate supplemental pass**:
`harness/backfill.py <suite> <iteration>`, run in the main loop, never a
subagent. This is why the gitignored run workspace is retained: a deferred
row can be filled later without a re-run. `backfill.py` touches **only** the
`passed: null` rows, judging each with one `claude -p` call (subscription,
cheap tier, strictly serial, stop on any limit) fed the row's `text` plus
`rubric` and the run's own `result.md`, `transcript.md`, and `git-state.txt`,
then merging `{passed, evidence}` back with `verdict_source: "grader"`. The
judge prompt budgets 60k transcript chars with head-and-tail elision, so
end-of-run evidence survives truncation. When running backfill after a codex
round, leave `EVAL_MODEL` unset: the variable names the judge model here, not
the SUT.

Because the grader is an LLM, its identity lands in a separate
`fingerprint.grader` block, distinct from `checker_sha256`:

```json
"grader": {"model": "<model>", "rubric_sha256": "<sha256 of this run's llm_judged (text, rubric) rows>", "harness_commit": "<short HEAD>"}
```

The summary carries both regimes side by side: `summary.pass_rate` stays the
machine subset; backfill adds `summary.total_pass_rate` over machine plus
grader rows and folds a `run_summary_total` block into `benchmark.json`.

### The fingerprint block

Every `grading.json` **must** carry a `fingerprint` so a result traces to
exactly what produced it; `run_eval.sh`'s normalize pass stamps it:

```json
"fingerprint": {
  "checker_sha256": "...", "harness_commit": "...",
  "skill_name": "...", "skill_commit": "...", "iteration": 2,
  "model": "...", "runs": 1,
  "timestamp": "...", "environment": "local",
  "execution": {"arm_rc": 0, "stderr_scan": "clean", "model": "...", "executor": "codex"},
  "grader": {"model": "...", "rubric_sha256": "...", "harness_commit": "..."}
}
```

`execution` records the per-arm run outcome (rc, the stderr auth/limit scan,
and, for codex arms, the executor); it makes the discipline claim auditable
from the harvested JSON alone. `grader` is present only after a backfill
pass; a machine-only round omits it.

### The driver and the skill-creator contract

`harness/run_eval.sh <skill> <eval_id> [runs] [iteration]` runs the whole
pipeline for one eval (or `all`): build the sandbox, run each arm
(`EVAL_EXECUTOR` selects the CLI), snapshot git state, grade with `check.py`,
normalize, aggregate, and harvest. It adds no grading intelligence of its
own. skill-creator contributes only the aggregate
(`aggregate_benchmark.py`) and the viewer (`eval-viewer/generate_review.py`);
both are directory-contract consumers reading
`iteration-N/eval-*/<arm>/run-*/grading.json` plus `eval_metadata.json`, and
never touch the sandbox git tree. `harness/snapshot.sh` records
`git-state.txt` into each run's `outputs/` as evidence.

### Iteration policy

Iterations are numbered **per skill** (`results/<skill>/iteration-N/`). Every
round records the git hash of the skill under test
(`fingerprint.skill_commit`); cross-skill comparability comes from that hash,
never from a shared iteration counter.

### Baseline (arm) policy

The standard form is `with_skill` vs `without_skill` with a Δ column. An
`old_skill` arm (the skill's prior `SKILL.md`, frozen with `git archive`) is
optional, built ad hoc for the one round that validates a skill upgrade
against regression, and called out explicitly in that report; it is never a
standing fixture.

### Reproducibility: the iron rules

1. **The reproducible triad is version-controlled.** A run is defined by the
   **case** (`cases/<suite>.json`), the **fixture**
   (`harness/build_sandbox.sh`), and the **driver** (`harness/run_eval.sh`),
   and all three live in git. If a scenario cannot be rebuilt from these, it
   is not an eval.
2. **Execution environments are disposable.** Anything that lives *only*
   inside an execution environment is treated as if it does not exist.
3. **Only small JSON comes home.** A completed round brings back its
   `grading.json` plus fingerprint (`results/<skill>/iteration-N/`); per-run
   sandboxes, transcripts, and benchmark blobs are regenerable and
   gitignored.
4. **No round, no citation.** If a round's `grading.json` + fingerprint
   cannot be brought back, the round is treated as never having run.

> Why rule 1 exists: an early suite's sandbox was hand-built inside a
> Codespace and never version-controlled; when that environment went away the
> whole suite became unreproducible. Fixtures live in `build_sandbox.sh`
> precisely so that cannot recur.

### Executor ground rules

These are the standing instructions handed to every executor run;
`run_eval.sh` extracts this blockquote verbatim into the prompt, so the
heading above and the quote format below are load-bearing:

> You are running ONE task inside an ISOLATED, OFFLINE git sandbox as part of a
> skill benchmark. You are launched hermetically (`claude --safe-mode`, or
> `codex exec --ignore-user-config`): no ambient context is loaded (no
> user/project instructions, no auto-memory), so both arms start from the same
> blank slate and the skill under test is the only variable. Follow these rules:
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
> - If your harness provides a subagent dispatch tool (Agent/Task), use it when
>   the workflow calls for dispatching a subagent and note which model you
>   used. If it provides none, do that step inline and say so explicitly.
> - The project quality gate, when relevant, is `make check` (see AGENTS.md).
>
> When finished (or when you stop to ask/block), write into the outputs dir
> given:
> 1. `transcript.md`, honest narration: the key git/test commands you ran with
>    essential output, decision points, and, if you stopped to ask/block, the
>    exact question or block message you'd give the user, quoted. Note what you
>    deliberately did NOT do and why.
> 2. `result.md`: your final user-facing reply.
> 3. (land only) `PR_BODY.md`: the PR body you composed, if any.
>
> Leave the git repo in its final state (do not clean up or revert). Reply with
> a 2-3 sentence summary.

### Execution discipline

- Runs go through the **subscription of the executor's own vendor**, never an
  API key: `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` /
  `ANTHROPIC_BASE_URL` must be unset for the Claude executor,
  `OPENAI_API_KEY` / `OPENAI_BASE_URL` for the Codex executor. The driver
  aborts if they are set.
- **Strictly serial**, cheapest scenario first as a sentinel. On any `401` /
  `429` / rate-limit or usage-cap signal, **stop immediately** and report; do
  not retry or fan out. A provider **capacity** error is the one exception:
  transient, produces no gradable output, retryable with generous spacing.
- A nested executor invocation (`claude -p` or `codex exec`) always runs in
  the **main execution loop**, never inside a subagent prompt: the safety
  classifier blocks `--dangerously-skip-permissions` when it appears inside a
  subagent (observed twice).
- If a load-bearing assumption breaks, **stop and report** rather than
  inventing a workaround on the spot.

### Target layout

```
evals/
  EVALUATION.md              this file: results + schema/rules single source
  cases/<suite>.json         schema v1: scenarios + typed expectations
  harness/build_sandbox.sh   sandbox construction (one case per fixture key)
  harness/run_eval.sh        thin one-shot driver (build -> arms -> grade -> aggregate; EVAL_EXECUTOR selects claude or codex)
  harness/check.py           the one general checker (sole machine grader; interprets schema v1)
  harness/backfill.py        supplemental llm_judged grader (fills deferred rows, adds total_pass_rate)
  harness/codex_transcript.py  codex outputs reconstructor (stream + child session rollouts -> transcript.md/result.md)
  harness/snapshot.sh        post-run git-state recorder (evidence in outputs/)
  results/<skill>/iteration-N/   grading.json + benchmark.json (small JSON only)
  history.md                  condensed development trail per suite
```

---

For the condensed development trail of each skill, including the superseded
single-executor rounds, see [`history.md`](./history.md).
