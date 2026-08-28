# Role agents

## What this is

This repo's skills dispatch work to three named roles, not to model names: `explore`
(read-only reconnaissance: locate files, trace symbols, sweep for "where or how is
X", cite conclusions with file:line, change nothing), `too-te` (fully-specified
mechanical execution: a tasks.md section, a pattern edit, a checklist audit, a data
extraction job, given a complete spec of goal, scope, and done-criteria), and
`sai-hu` (judgment-heavy implementation: features, bug fixes, and refactors with
real design decisions, or a task where a `too-te` run stalled twice). One rule ties
the whole roster together: skill text names roles, never model names, so the
roster can be re-pinned or re-hosted without touching a single skill body.

`agents/claude/` and `agents/codex/` are two renderings of the same three role
contracts, one per harness. The contract (what each role is for, what it may
decide, when it must stop and report instead of guessing) is authored once and
kept in sync by hand across both renderings; only the frontmatter/config shape
differs per platform.

## Installation

**Claude Code**: copy or symlink `agents/claude/*.md` into `~/.claude/agents/`.
Symlinking keeps the roster following this repo as it evolves:

```
for f in agents/claude/*.md; do ln -sfn "$PWD/$f" ~/.claude/agents/"$(basename "$f")"; done
```

**Codex**: copy `agents/codex/*.toml` into `~/.codex/agents/`:

```
mkdir -p ~/.codex/agents && cp agents/codex/*.toml ~/.codex/agents/
```

Codex reads one agent per `.toml` file, and on current releases (codex-cli
0.150) two restrictions make plain copies the only working install:

- Symlinked role files are rejected at spawn time: the link still appears in
  the spawn tool's role listing, but dispatching it fails with "agent type is
  currently not available". After editing a role here, re-copy it instead of
  relying on a link.
- Only the user-wide directory is read. The project-scoped `.codex/agents/`
  that upstream documentation describes is not loaded.

The spawn tool's schema is generated from the installed roster: an empty
`~/.codex/agents/` exposes no role parameter at all, and the roles appear in
the tool's listing once the files are in place.

## Dispatch

Neither harness needs routing configuration beyond the install. A skill line
such as "dispatch the `too-te` role" resolves natively: Claude Code routes it
through the Agent tool's subagent types; Codex routes it through the spawn
tool's `agent_type` argument, loads the role's `developer_instructions`, and
applies the TOML's pinned model and reasoning effort to the child. Only
`agent_type` selects a role; naming a task or a subagent after a role does
not load anything.

## Known differences (degraded mode, stated honestly)

Codex's agent format is not a full equivalent of Claude Code's, and this repo does
not try to paper over the gap:

- **No hard turn ceiling**: `too-te`'s Claude Code definition sets `maxTurns: 100`
  as an enforced circuit breaker. Codex has no equivalent field, so the Codex
  rendering carries the same 100-turn figure as a stated self-budget inside the
  contract text instead of an enforced stop; the wind-down and breakpoint-report
  behavior still applies, it is just not backstopped by the harness.
- **No per-tool blocklist**: Claude Code keeps these roles leaf agents through
  enforced frontmatter (`disallowedTools: Agent, Workflow` on `too-te` and
  `sai-hu`, a Read/Glob/Grep-only allowlist on `explore`). Codex has no
  per-tool allow/deny list; current releases give spawned subagents no
  multi-agent tools at all, so the roles run as leaves there too. Each Codex
  role additionally carries `[agents] enabled = false` and an explicit leaf
  clause in its `developer_instructions` as insurance against a future release
  granting nested spawning. Finer tool granularity (which read tools `explore`
  may reach for) has no Codex equivalent.
- **Coarse-grained sandboxing**: Codex's `sandbox_mode` is a three-way switch
  (read-only, workspace-write, danger-full-access), mapped here as read-only for
  `explore` and workspace-write for `too-te` and `sai-hu`. It is not a substitute
  for Claude Code's per-tool allowlist (Read/Glob/Grep for `explore`); it only
  constrains filesystem/exec access, not which tools a role reaches for.

This repo provides basic support for both harnesses, not full parity. Getting a
harness-specific guarantee beyond what is listed above (a real turn ceiling, a
real tool blocklist) means adjusting the rendering yourself against that
platform's current capabilities.
