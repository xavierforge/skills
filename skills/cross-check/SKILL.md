---
name: cross-check
description: Two-axis review of the diff since a fixed point, one axis for Standards (repo conventions, structure, style) and one for Spec (does the change do what the issue or PRD asked). Use when /preflight or /land needs its review layer, or the user asks to cross-check a change; a bare 'review this' request stays with /code-review.
---

Review the diff between a fixed point and `HEAD` along two axes that stay separate on purpose:

- **Standards**: does the code respect this repo's conventions, structure, and style?
- **Spec**: does the change faithfully do what the originating issue, PRD, or spec asked?

Each axis runs in its own clean-context subagent, so neither colours the other's reading, and this skill then aggregates their findings.

## Evidence ladder

Every finding names the strongest rung it reached, weakest to strongest:

- `said`: asserted, nothing cited.
- `pointed`: cites file:line on both ends, the rule or spec line and the offending hunk.
- `ran`: a command plus its observed output that shows the problem.
- `reproduced`: the orchestrating session reran that command and saw the same failure.

A Standards finding is normally complete at `pointed`. A finding that claims wrong behaviour (a Spec "implemented wrongly" finding, a `/land` adversarial portability or security finding) is `hard` only with a rerunnable command. Rungs measure proof, not importance: zero findings stays a valid report, and no reviewer is asked for a command on a finding that claims no behaviour.

**Rerun, then demote; never delete.** The orchestrating session reruns every supplied command. The same failure moves the finding to `reproduced`. A command that does not show the failure, or a behavioural claim with no command, keeps its entry but drops to severity `judgement`, marked unproven with a one-clause reason, and is counted, because a silently dropped finding hides the reviewer's miss. A command that cannot run here (offline sandbox, missing toolchain) is reported as `not run (<reason>)`, and the finding stays at the rung it reached with its severity as reported.

## Process

### 1. Pin the fixed point

The fixed point is whatever reference the user names: a commit SHA, a branch, a tag, `main`, `HEAD~5`. If they name none, ask for one.

Confirm it resolves (`git rev-parse <fixed-point>`) and that the diff is non-empty before spawning anything; catch a bad ref or an empty diff at this point, before either subagent starts. The comparison reads against the merge-base, so use the three-dot form: `git diff <fixed-point>...HEAD`, with the commit list from `git log <fixed-point>..HEAD --oneline`. Capture both once and hand them to each subagent.

### 2. Find the spec source

Locate the originating spec in this order:

1. An issue that the commits reference (`#123`, `Closes #45`, GitLab `!67`). Fetch its contents when the repo exposes a way to reach the tracker; otherwise treat the reference as a pointer and read whatever it links to.
2. A file path the user supplied when calling the skill.
3. A PRD or spec file under `docs/`, `specs/`, or `.scratch/` whose name matches the branch or the feature.
4. Nothing turned up: ask the user to point at the spec. If there truly is none, the Spec axis skips and reports "no spec available".

### 3. Find the standards sources

The Standards axis draws on two things:

1. Whatever the repo writes down about its own coding style, in files like `CODING_STANDARDS.md` or `CONTRIBUTING.md`. Collect those paths.
2. The **smell baseline**: the classic code smells from Fowler's _Refactoring_ catalog (mysterious names, duplicated logic, feature envy, data clumps, primitive obsession, message chains, and the rest of that vocabulary). Draw them from that shared knowledge rather than a copied checklist; it applies even when the repo documents nothing.

Two rules bind the baseline:

- **A documented repo standard wins.** Where the repo endorses something the baseline would flag, follow the repo and drop the smell.
- **Baseline smells stay judgement calls,** labelled as possibilities ("possible feature envy"), not hard violations. Skip anything tooling already enforces.

### 4. Spawn both subagents in parallel

Dispatch two fresh general subagents, one per axis, in a single message so they run in parallel (on Claude Code that is two `Agent` tool calls with `subagent_type: general-purpose` in one message). The clean context per axis is the point: neither subagent sees the other's reasoning.

**Briefs stay claim-free.** Each subagent gets the diff, its sources, the evidence ladder above pasted in full, and its brief, nothing else: no author summary, no commit-message bodies or justifications (the commit list is `--oneline` subjects), no conclusions from this session, because a reviewer handed the author's conclusion inherits it.

**Standards subagent** gets:

- The diff command and commit list.
- The standards-source paths from step 3, and the smell baseline pasted in full, since the subagent has no other access to it.
- This brief: "Report, per file or hunk where it helps, (a) every place the diff breaks a documented standard, citing the standard's file and rule; and (b) every smell baseline hit, named with the hunk quoted. Mark a clear documented-standard breach as hard and every baseline smell as a judgement call; where the written repo standard and the baseline disagree, the written standard governs. Leave out whatever a linter or formatter already catches. Give each finding its evidence rung, and the exact command and its output for any claim of wrong behaviour. No findings is a valid report. Keep the report under 400 words."

**Spec subagent** gets:

- The diff command and commit list.
- The spec path, or its fetched contents.
- This brief: "Report (a) anything the spec called for that the diff leaves unbuilt or only half-built, (b) behaviour in the diff nobody requested (scope creep), and (c) requirements that appear done but were implemented wrongly. Cite the spec line each finding rests on and give its evidence rung; for (c), give the exact command that shows the wrong behaviour and the output you saw. No findings is a valid report. Hold the report under 400 words."

When no spec exists, skip the Spec subagent and say so in the aggregate.

### 5. Aggregate

First rerun every supplied command per the evidence ladder. Then lay out each subagent's report under its own `## Standards` and `## Spec` heading, quoted as-is or with only light cleanup plus each finding's final rung. Keep them apart: do not merge, rerank, or crown one finding across axes, because that cross-axis reranking is exactly what the separation exists to prevent (see _Why two axes_).

Finish with a single line giving each axis its finding count, how many were demoted and why in a clause (`spec: 3 findings, 1 demoted (rerun passed)`), and its most serious item. Do not crown one overall winner across the two.

### 6. Write the verdict artifact

Persist the outcome so later tooling (notably `/land`'s reconciliation step) reads the verdict from disk instead of trusting a verbal claim. Resolve where it is written with the **artifact directory rule** the neighbor skills share (vibe-diff writes its artifacts by the same resolution): the active openspec change directory (`openspec/changes/<name>/`, excluding `archive/`) when exactly one exists, otherwise `.review/<slug>/` at the repo root, where `<slug>` is the branch name with `/` turned into `-` (`feat/hook-system` becomes `.review/feat-hook-system/`). Create the directory when it is missing. Write `review-verdict.json` there:

```json
{
  "layer": "cross-check",
  "fixed_point": "<the ref pinned in step 1, verbatim>",
  "patch_id": "a3770d655e49b15b7f250ccd27970add1bed258b",
  "findings": [
    {"axis": "standards", "title": "possible feature envy in loader.rs", "severity": "judgement", "actioned": false, "evidence": {"rung": "pointed"}},
    {"axis": "spec", "title": "retry on 429 never fires (spec line 12)", "severity": "hard", "actioned": false, "evidence": {"rung": "reproduced", "command": "pytest tests/test_client.py -k retry_429"}},
    {"axis": "spec", "title": "timeout ignores the config value (spec line 20)", "severity": "judgement", "actioned": false, "evidence": {"rung": "ran", "command": "pytest tests/test_client.py -k timeout", "unproven": "rerun passed"}}
  ]
}
```

- `layer` is this skill's name as invoked (`cross-check`).
- `fixed_point` is the ref pinned in step 1, verbatim.
- `patch_id` is the **patch id** of the reviewed diff, the one command every layer uses to tell whether a record still covers the current change:

  ```
  git diff <fixed_point>...HEAD -- ':!*review-verdict.json' ':!*diff-review.*' ':!*diff.patch' ':!*preflight-status.md' ':!*decisions.md' | git patch-id --stable | cut -d' ' -f1
  ```

  The excludes drop the files the review layers write, so committing an artifact does not stale its own verdict. A rebase or a message-only amend leaves the id unchanged; any content change alters it. Empty output means an empty diff, which step 1 already refuses.
- `evidence` is the finding's ladder record: `rung` always, `command` when one was supplied, `unproven` (a one-clause reason) only on a demoted finding, and `rerun: "not run (<reason>)"` when the command could not be rerun here.
- `patch_id` and `evidence` are additive: a reader meeting an artifact or finding without them treats it as written before this contract (unknown age, rung unknown) and reads the other fields as before.
- `axis` is `standards` or `spec`, matching the two report headings.
- `severity` is `hard` (a documented-standard breach, or a spec requirement missing or built wrong) or `judgement` (a smell baseline hit, other judgement call, or a demoted finding), the same distinction the reports already draw.
- `actioned` records whether the finding was fixed by the time the file is written: `false` at review time. A later session that fixes a finding flips the flag in place rather than deleting the entry, since the artifact is the record `/land` reconciles against, and never rewrites `patch_id`, because the fix itself was not reviewed.
- An empty `findings` array is a valid verdict: it says the review ran and found nothing, which is exactly the fact worth having on disk.

The step is done when `review-verdict.json` sits at the resolved artifact directory with the `patch_id` of the diff just reviewed, and its `findings` match the two reports one to one: every reported finding has an entry, demoted ones included, and no entry lacks a reported finding.

## Why two axes

One axis can come back clean while the other fails:

- Code that honours every documented standard but ships the wrong behaviour: Standards pass, Spec fail.
- Code that delivers precisely the behaviour the issue requested yet tramples the repo's conventions: Spec pass, Standards fail.

Reporting the axes separately keeps either one from masking the other.

## Why the trigger is this narrow

`cross-check` stays model-invocable on purpose: `/preflight` and `/land` call it by name as their review layer, which a `disable-model-invocation` flag would block. The narrow description is the guard instead. The model once fired this skill on its own inside a goal loop and ran an invisible review pass nobody asked for, so the description names its callers and leaves a bare "review this" request to `/code-review`.

The two-axis split was inspired by Matt Pocock's `code-review` skill; this repo's version is its own and maintained here.
