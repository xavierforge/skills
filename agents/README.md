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

**Codex**: copy `agents/codex/*.toml` into `~/.codex/agents/` for a user-wide
roster, or into a project's own `.codex/agents/` for a project-scoped one. Codex
reads one agent per `.toml` file; there is no announced base-directory convention
to symlink against, so a plain copy is the supported install path.

## Known differences (degraded mode, stated honestly)

Codex's agent format is not a full equivalent of Claude Code's, and this repo does
not try to paper over the gap:

- **No hard turn ceiling**: `too-te`'s Claude Code definition sets `maxTurns: 100`
  as an enforced circuit breaker. Codex has no equivalent field, so the Codex
  rendering carries the same 100-turn figure as a stated self-budget inside the
  contract text instead of an enforced stop; the wind-down and breakpoint-report
  behavior still applies, it is just not backstopped by the harness.
- **No fine-grained tool blocklist**: the Claude Code agents set
  `disallowedTools: Agent, Workflow` to keep these roles as leaves that never
  delegate further. Codex has no per-tool allow/deny list at the agent level, so
  the Codex rendering relies on the contract text itself ("role agents are leaf
  agents: they never delegate further") to hold the line.
- **Coarse-grained sandboxing**: Codex's `sandbox_mode` is a three-way switch
  (read-only, workspace-write, danger-full-access), mapped here as read-only for
  `explore` and workspace-write for `too-te` and `sai-hu`. It is not a substitute
  for Claude Code's per-tool allowlist (Read/Glob/Grep for `explore`); it only
  constrains filesystem/exec access, not which tools a role reaches for.

This repo provides basic support for both harnesses, not full parity. Getting a
harness-specific guarantee beyond what is listed above (a real turn ceiling, a
real tool blocklist) means adjusting the rendering yourself against that
platform's current capabilities.
