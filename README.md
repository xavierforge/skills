# xavier skills

[繁體中文](README.zh-TW.md)

A disciplined agent delivery pipeline: from spec to merged PR, with role-tiered dispatch, layered review gates, and eval-measured skills. It works best on an OpenSpec-structured project; most of the skills also run standalone.

The eight skills cover the delivery path from a framed change to a merged PR: branch discipline at the start (`begin`), role-tiered dispatch through the execute phase (`factory`, `section`), layered review gates with a decision ledger before shipping (`cross-check`, `vibe-diff`, `preflight`), and reconciled PR creation at the end (`ship`), each carrying its own behavioral eval. OpenSpec is the recommended spec backbone rather than a hard prerequisite: `factory`, `section`, and `spec-viewer` read an `openspec/changes/` layout and need it; `begin` and `ship` run on any project; `cross-check`, `vibe-diff`, and `preflight` use the OpenSpec change directory when it is there and fall back to a mini-spec and a `.review/` landing when it is not. The companion [`openspec-rules/`](openspec-rules/) directory ships the templates that layout fits into.

This repo is the canonical source of truth for each skill. Edit here, not the installed copies (the CLI and manual tracks below install by symlink, so a copy is just a link back to this tree).

## Installation

Set up OpenSpec first if you want the full pipeline (step 0, optional), then install the skills through one of the three tracks below.

### 0. Optional: install OpenSpec

[OpenSpec](https://github.com/Fission-AI/OpenSpec) gives a project the `openspec/changes/` structure the spec-driven skills read. Install it to unlock the full pipeline: `factory`, `section`, and `spec-viewer` need that layout, and `cross-check`, `vibe-diff`, and `preflight` use it when it is present. The rest run without it, so this step is optional; skip it if you only want `begin`, `ship`, or the standalone review skills.

Aside from OpenSpec, the suite has no external skill dependencies. Where a skill body names a neighbor command it does not own (`/opsx:verify`, `/code-review`, `/verify`, `/opsx:archive`), it carries a fallback for the environment that lacks that command, so nothing hard-fails on a missing command.

### 1. skills CLI (recommended)

```
npx skills add xavierforge/skills
```

The vercel-labs `skills` CLI works on any harness that follows the Agent-Skills standard (Claude Code, Codex, and others). It installs by symlink, so the skills keep following this repo as it evolves.

### 2. Claude Code plugin

```
claude plugin marketplace add xavierforge/skills
claude plugin install xavierforge-skills@xavierforge
```

The `.claude-plugin/` marketplace in this repo promotes all eight skills as one installable plugin for Claude Code users.

### 3. Manual symlink (fallback)

Link everything in one go (idempotent; re-run after adding a skill):

```
for s in skills/*/; do ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"; done
```

Or link a single skill: `ln -sfn "$PWD/skills/<skill>" ~/.claude/skills/<skill>`.

Tool requirements: `git` everywhere; `gh` (GitHub CLI) only for ship's PR-creation step (begin is pure git); `uv` or any `python3` for the viewer skills' scripts.

## Role agents (recommended for the dispatching skills)

The skills that dispatch work (`factory`, `section`, `ship`) hand it to three named roles rather than to model names, so they run best with the role roster installed alongside the skills. Install it from [`agents/README.md`](agents/README.md), which covers both the Claude Code and Codex renderings and their degraded-mode differences. Without the roster installed the dispatch step degrades rather than hard-failing: `factory`, `section`, and `ship` fall back to a general subagent carrying the intended role's one-line contract and keep running, noting the degrade in their reports. Installing the roster is what turns that fallback into real model tiering and per-role tool boundaries; the non-dispatching skills are unaffected either way.

## Skills

| Skill                                | What it does                                                                                                                                                                                                                                                                    | OpenSpec | Invocation                    |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ----------------------------- |
| [`begin`](skills/begin/)             | Two-phase start-of-contribution ritual: sync the default branch to a clean base and guard the working tree, then open the feature branch once the work is nameable                                                                                                              | none     | manual, `/begin`              |
| [`cross-check`](skills/cross-check/) | Two-axis review of the diff since a fixed point, each axis run in its own parallel sub-agent and reported side by side (a standards axis against the repo's documented conventions plus a fixed smell baseline, and a spec axis against the originating issue or PRD); persists a `review-verdict.json` for `/ship` to reconcile against | optional | manual, `/cross-check`        |
| [`factory`](skills/factory/)         | Drive the whole active OpenSpec change, one section per round through fresh subagents, with a plan gate, round budget, and ledger; user-invoked only                                                                                                                             | required | manual, `/factory`            |
| [`preflight`](skills/preflight/)     | Pre-ship acceptance gate between `/factory` and `/ship`: reconcile against the change's Non-Goals and its `decisions.md` ledger, run the mechanical, runtime, and two static review layers, hand the sign-off page to the user (`/vibe-diff` in a fresh session), then triage every finding into fix, reversal request, or tracked, writing each ruling back to the ledger                                                | optional | manual, `/preflight`          |
| [`section`](skills/section/)         | Execute-phase workflow: run one numbered `tasks.md` section (locate the active change, honor its dispatch annotation, TDD per task, one Conventional Commits commit, tick checkboxes, stop)                                                                                     | required | model-invocable, `/section N` |
| [`ship`](skills/ship/)               | Pre-PR shipping workflow: base refresh, mechanical diff scan, quality gate, adversarial pre-PR review, commit organization, PR body; per-project facts derived at run time, no config file                                                                                      | optional | manual, `/ship`               |
| [`spec-viewer`](skills/spec-viewer/) | Render one OpenSpec change into a single self-contained HTML review page: proposal, design, specs, and tasks assembled into a navigable handbook-style page                                                                                                                     | required | manual, `/spec-viewer`        |
| [`vibe-diff`](skills/vibe-diff/)     | Render a self-contained diff-review page for a branch's diff against its merge-base, read against the OpenSpec change it implements; a deterministic script owns the page, the model authors only the judgment JSON; the right-side twin of `spec-viewer`, cross-linked with it | optional | manual, `/vibe-diff`          |

OpenSpec column: **required** means the skill reads an OpenSpec change directory and has nothing to act on without one (`factory`, `section`, `spec-viewer`); **optional** means it uses the OpenSpec layout when present and takes a non-OpenSpec path when absent (`ship` asks and derives its spec location and post-merge ritual from the layout; `cross-check`, `vibe-diff`, and `preflight` fall back to a mini-spec and a `.review/` landing); **none** means fully decoupled (`begin`).

## Conventions

- **No hardcoded install paths**: When Claude Code invokes a skill it announces "Base directory for this skill: <path>", and every SKILL.md references its own files through that announcement, written as `<skill-base>/scripts/...` in skill bodies.
- **Shared scripts exist once**: The canonical copy lives in one skill and the other skill reaches it as a sibling (`<skill-base>/../<other-skill>/scripts/...`). No symlinks between skills, so nothing degrades on a Windows checkout or a partial copy; the only failure mode is the sibling skill not being installed, which the referencing SKILL.md handles by saying so.
- **Skill scripts live in `scripts/`**, are python3 stdlib-only or plain bash, and never require a per-project config file: per-project facts are derived at run time, confirmed with the user when ambiguous, and at most offered (never required) for recording in the project's own agent instructions.

## Evals

Every skill carries a behavioral eval that measures what the skill adds at a fixed cheap model over the same model with no skill, run as a `with_skill` vs `without_skill` pair and scored on the resulting git state and outputs rather than on the runner's narration; the suites, the method, and the per-skill numbers live in [`evals/EVALUATION.md`](evals/EVALUATION.md). This is a Claude Code-only measurement layer: `evals/harness/run_eval.sh` invokes the `claude` CLI directly, and its `claude --safe-mode --dangerously-skip-permissions` call is deliberate and scoped to that harness, running each pair inside a disposable sandbox checkout where skipping the interactive permission prompt is what lets the batch run unattended; it is not a recommendation for normal skill use, and a public scanner flagging that flag is reading it out of its sandbox context.

## Portability and dual-harness support

This repo aims at basic support for both Claude Code and Codex, not full parity. The skill bodies and their Codex descriptors are kept harness-neutral; where a harness cannot enforce a guarantee, the degraded mode is stated honestly rather than papered over.

- **Python via uv, stdlib only**: Skill scripts are python3 stdlib-only, so the classic Python dependency problems (venv, pip, version pinning) are absent by construction; the only environment assumption is "any Python 3 exists". `uv run` is just the cross-platform launcher (it self-provisions an interpreter when none is installed); the SKILL.md bodies name the `python3` fallback for machines without uv. Keep new skill scripts stdlib-only to preserve this.
- **Base directory, any harness**: The `<skill-base>` convention leans on Claude Code injecting "Base directory for this skill: <path>" at invocation. Other harnesses may not announce it; on those, the fallback is resolving relative to the SKILL.md file the harness loaded. Skill bodies are phrased as "this skill's base directory" (a concept any harness can satisfy) rather than naming the Claude Code banner as the only source.
- **Frontmatter is Claude Code-only, descriptions are portable**: The keys `disable-model-invocation`, `model`, and `effort` in SKILL.md frontmatter are Claude Code extensions; other harnesses read only `name` and `description` and ignore the rest. For those harnesses each skill also ships an `agents/openai.yaml` Codex descriptor next to its SKILL.md, kept in sync with the description. In Claude Code, `disable-model-invocation: true` additionally drops the skill's description from the always-loaded skill list, so the user-invoked rituals (begin, ship, spec-viewer, vibe-diff) cost zero standing context.
- **Role-phrased model routing, with one deliberate pin left**: ship's adversarial review asks for "the strongest review-grade model available" and reports which model it dispatched, so it survives a model lineup change without edits. spec-viewer still pins `model: haiku` (cheapest model that can run a script); if that pin ever goes stale, rephrase it as the role instead of a newer model id.
- **Agent roster, supported on both harnesses with degraded mode stated**: the dispatching skills name three roles (explore, too-te, sai-hu), not model names, so the roster can be re-pinned or re-hosted without touching a skill body. Both renderings live in `agents/` (`agents/claude/*.md` and `agents/codex/*.toml`) and install per [`agents/README.md`](agents/README.md). Where a harness cannot back a guarantee (Codex has no hard turn ceiling and no per-tool blocklist), the role contract carries the constraint in prose and the skill reports rather than stalls when the environment differs; the exact differences are enumerated in that README's degraded-mode section.
- **Slash-command coupling**: Skill bodies state the required event and treat neighbor slash commands as one way to satisfy it, not as hard dependencies (begin's branch rule is phrased as "before the new work's first commit" rather than naming the propose command; ship names /opsx:archive only as an example of the archive event). Direction: keep auditing for hard command dependencies as new skills are added.
