# xavier skills

[繁體中文](README.zh-TW.md)

This repo holds nine skills that walk one change from a framed spec all the
way to a merged PR, then feed what went wrong back into the rules, in this
order:

1. **Prepare** (`begin`): sync the default branch to a clean base, then open
   a feature branch.
2. **Implement**: `factory` drives the whole change forward, one section per
   round; `section` focuses on a single block, TDD per task, stopping after
   one commit.
3. **Layered review**: `cross-check`, `vibe-diff`, `spec-viewer`, and
   `preflight` stack the review gates and maintain a decision ledger.
4. **Contribute** (`land`): reconcile, run the adversarial review, organize
   the commits, then write the PR body and open the PR.
5. **Learn** (`retro`): log each mistake in a lessons ledger, and once a
   class of mistake recurs, propose the strongest enforcer that can hold it
   (a script, a check, a test, prose last) for the user to approve.

The flow grew around the [OpenSpec](https://github.com/Fission-AI/OpenSpec)
workflow, so it works best doing SDD with it. In practice only three skills
hard-require the OpenSpec directory layout (see the table); the rest run on
any repo, automatically falling back to a mini-spec with a `.review/` artifact
directory when no spec directory is found, and the repo's
[`openspec-rules/`](openspec-rules/) directory ships the templates needed.

One more thing to remember: this repo is the single source of truth. Every
install track below works by symlink, so make changes here, never in the
installed copy.

> **About the mini-spec**
>
> A term specific to this workflow: the few sentences of raw intent handed to
> `/begin` when the work starts.
> The system saves it **verbatim** to `.review/<branch-slug>/mini-spec.md`
> (it never presumes to distill a summary out of the chat for you).
> When the project has no OpenSpec change to consult, the review skills treat
> this file as the sole baseline for reading the diff.
>
> **A worked example**
>
> Given the input:
>
> `/begin CLI gets a --json flag; schema matches the README table; default text output stays unchanged`
>
> the system opens a feature branch and saves that sentence, word for word,
> as `.review/feat-cli-json-flag/mini-spec.md`.
> A later `/vibe-diff` review then reads the branch's diff directly against
> this mini-spec to explain, and judge, whether it matches the original
> intent.

## The skills

| Skill                                | What it does                                                                          | OpenSpec | Invoke                         |
| ------------------------------------ | ------------------------------------------------------------------------------------- | -------- | ------------------------------ |
| [`begin`](skills/begin/)             | Sync the default branch first, then open a clean feature branch                       | none     | `/begin`                       |
| [`factory`](skills/factory/)         | Drive the active change, one section per round, a fresh subagent every round          | required | `/factory`                     |
| [`section`](skills/section/)         | Run one numbered `tasks.md` section: TDD per task, one commit at the end, then stop   | required | `/section N` (model-invocable) |
| [`cross-check`](skills/cross-check/) | Standards axis + spec axis review of the diff; persists a verdict for `/land`         | optional | `/cross-check`                 |
| [`vibe-diff`](skills/vibe-diff/)     | Self-contained diff-review page, read against the change's intent                     | optional | `/vibe-diff`                   |
| [`spec-viewer`](skills/spec-viewer/) | One OpenSpec change rendered as a single handbook-style HTML page                     | required | `/spec-viewer`                 |
| [`preflight`](skills/preflight/)     | Pre-contribution acceptance gate: reconcile, run the review layers, rule on findings  | optional | `/preflight`                   |
| [`land`](skills/land/)               | Sync the base to the remote default branch's latest, quality gate, adversarial review, organize commits, write the PR body | optional | `/land`                        |
| [`retro`](skills/retro/)             | Record mistakes in a lessons ledger; turn a recurring class into a script, check, or test after approval | optional | `/retro`                       |

_(Note: **required** = nothing to act on without `openspec/changes/`;
**optional** = uses it when present, takes the non-OpenSpec path when absent;
**none** = fully decoupled.)_

`land` was named `ship` until a Claude Code skill of the same name made the
rename necessary; if you installed by symlink, re-run the install loop and
delete the stale `ship` link from your skills directory.

## Installation

> **TL;DR**
>
> Open this repo in your agent (Claude Code or Codex) and say **"follow the
> setup runbook in [AGENTS.md](AGENTS.md)"**; it installs the skills, the
> role roster, and the project's OpenSpec rule template in one pass. Running
> this step in full is strongly recommended: it is the baseline that lets
> every skill here perform at its best.
>
> To do it by hand instead, follow the tracks below.

### 0. OpenSpec (optional)

Install [OpenSpec](https://github.com/Fission-AI/OpenSpec) first if you want
the full pipeline, or skip it if you only need `begin`, `land`, or the
standalone review skills. Beyond that the project has no external
dependencies: wherever a skill body mentions a neighbor command
(`/opsx:verify`, `/code-review`, ...), a fallback is written in, so nothing
hard-fails on a missing command.

### 1a. skills CLI (recommended)

```bash
npx skills add xavierforge/skills
```

The vercel-labs `skills` CLI supports every harness that follows the
Agent-Skills standard (Claude Code, Codex, and others), and installs by
symlink, so already-installed skills follow along as the repo updates.

### 1b. Claude Code plugin

```bash
claude plugin marketplace add xavierforge/skills
claude plugin install xavierforge-skills@xavierforge
```

### 1c. Manual symlink (fallback)

```bash
for s in skills/*/; do ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"; done
```

This is safe to re-run (idempotent); run it again after adding a skill. To
install a single skill:
`ln -sfn "$PWD/skills/<skill>" ~/.claude/skills/<skill>`.

Tools needed: `git` always; `gh` only for land's PR-creation step; the
viewer skills' scripts need `uv` or any `python3`.

### 2. Role agents (recommended)

The skills that dispatch work (`factory`, `section`, `land`, `retro`) hand
tasks to three named roles rather than pinning specific models.

Install the roster per [`agents/README.md`](agents/README.md) (both the
Claude Code and Codex renderings are there). Nothing breaks without it:
dispatch degrades to a plain subagent carrying the role's one-line contract
and keeps running, noting the degrade in its report; installing the roster is
what buys real model tiering and explicit tool boundaries.

## Conventions and principles

- **No hardcoded install paths**: skill bodies always reach their own files
  as `<skill-base>/scripts/...`, resolved dynamically from the base directory
  the harness provides at invocation.
- **Shared scripts exist once**: the canonical copy lives in one skill, and a
  neighbor reaches it by sibling path
  (`<skill-base>/../<other-skill>/scripts/...`); skills never symlink to each
  other. The only failure mode is "the sibling is not installed", and the
  prompt says so outright when it happens.
- **A clean script environment**: every skill script lives in `scripts/`,
  uses only the python3 standard library or plain bash, and never depends on
  a project-level config file; project facts are derived dynamically at run
  time, and when they truly cannot be guessed, the user is simply asked.

## Evals

Every skill carries a behavioral eval: the same cheap model runs the
`with_skill` and `without_skill` arms, and scoring looks directly at the
resulting git state and outputs. The method and the numbers live in
[`evals/EVALUATION.md`](evals/EVALUATION.md).

The harness's `claude --safe-mode --dangerously-skip-permissions` exists so a
whole eval batch can run without human intervention, scoped to a disposable
sandbox checkout; it is not an endorsement of the flag, so use your own
judgment in normal work.

## Cross-harness support (Claude Code + Codex)

This repo provides basic dual-harness support without chasing full parity;
wherever a harness cannot hold a guarantee, the degraded mode is stated
honestly:

- **Scripts depend only on the standard library**: no venv, pip, or version
  pinning problems; `uv run` is just a cross-platform launcher, and the
  project names `python3` as the fallback.
- **`<skill-base>` holds on any harness**: Claude Code announces the base
  directory at invocation; other platforms resolve against the location of
  the loaded `SKILL.md`.
- **Frontmatter is Claude Code-only**: other harnesses read only
  `name`/`description`; each skill ships an extra `agents/openai.yaml` for
  Codex to read, and `disable-model-invocation: true` is there so the
  manually invoked ritual skills stay off the always-loaded list (zero
  standing context).
- **Model routing by role description**: `land`, for example, asks for "the
  strongest review-grade model available" instead of pinning a model id; the
  one deliberate pin in the whole suite is spec-viewer's `model: haiku` (the
  cheapest model that can run a script).
- **An agent roster on both harnesses**: shipped as `agents/claude/*.md` and
  `agents/codex/*.toml`; the exact gaps on the Codex side (no hard turn
  ceiling, no tool blocklist) are all enumerated in
  [`agents/README.md`](agents/README.md).
- **No hard slash-command coupling**: skill bodies describe only the event
  that must happen; neighbor commands are one way to satisfy it, and a
  fallback exists for environments without them.
