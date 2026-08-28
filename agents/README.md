# Role agents

[繁體中文](README.zh-TW.md)

## Why this exists

In short: when most Skills in this repo hand out work, they get better results
by dispatching to three custom sub-agents:

- **`explore` (read-only recon)**: finds files, traces code, and works out
  "where is this and how does it work". Its conclusions come with file and
  line numbers (file:line citations), and it never touches the code.
- **`too-te` (mechanical execution)**: handles tasks that are already fully
  specified, such as bulk edits, checklist-driven review, or data extraction,
  provided it is given an explicit goal, scope, and done-criteria.
- **`sai-hu` (main implementer)**: work that needs judgment goes here! That
  covers new features, bug fixes, refactors, and any hard problem `too-te`
  has stalled on twice in a row.

The point of this setup: a `SKILL.md` only ever names roles, so later swaps of
model or platform never touch a written `SKILL.md`. `agents/claude/` and
`agents/codex/` are just this contract implemented on each platform; the core
rules are identical, only the config format differs.

## Installation

### Claude Code

Symlink the `.md` files under `agents/claude/` into `~/.claude/agents/`; that
way, when the repo updates, these custom sub-agents upgrade with it:

```bash
for f in agents/claude/*.md; do ln -sfn "$PWD/$f" ~/.claude/agents/"$(basename "$f")"; done
```

### Codex

Copy the `.toml` files under `agents/codex/` straight into `~/.codex/agents/`:

```bash
mkdir -p ~/.codex/agents && cp agents/codex/*.toml ~/.codex/agents/
```

Note that Codex is currently (codex-cli 0.150) less flexible; two limitations
make plain copying the only install method that works:

- **No symlink support**: a linked file shows up in the listing, but actually
  running it errors out (agent type is currently not available), so after
  changing a config file, remember to copy it over again.
- **Global path only**: it reads the user-wide folder exclusively; the
  project-level `.codex/agents/` in the official docs is never picked up.

_(Aside: Codex's tool listing is generated dynamically. Before any files are
installed you will not even see a role parameter; it appears once they are in
place.)_

## Dispatch

Once both platforms are installed, there is no need for elaborate model
routing in a global CLAUDE.md or AGENTS.md. Write one line in a script,
"dispatch the `too-te` role", and the system takes care of itself:

- **Claude Code**: goes through the Agent tool's subagent mechanism.
- **Codex**: goes through the spawn tool's `agent_type` argument, which loads
  the matching instructions and applies the model and reasoning effort set in
  the TOML. Note that in Codex only the proper argument (`agent_type`)
  actually summons a role; just naming a task or subagent after a role does
  nothing.

## Known platform differences (Codex degraded mode)

No sugarcoating here: Codex's config cannot yet reach full parity with Claude
Code:

- **No hard turn ceiling**: `too-te` has `maxTurns: 100` as a forced brake on
  the Claude Code side, but Codex has no such feature, so "100 turns" can
  only be written into the prompt as self-restraint; the system will not cut
  the line for us. The fallback is the contract's wind-down rule: as the
  budget runs low, it must stop itself at a clean breakpoint and report its
  progress as a breakpoint write-up.
- **No precise tool restriction (Tool Blocklist)**: Claude Code can pin roles
  down to leaf nodes in config (`disallowedTools: Agent, Workflow` on
  `too-te` and `sai-hu`) or restrict `explore` to reading. Codex currently
  has no such denylist mechanism. That said, testing shows subagents spawned
  on the current version cannot reach any multi-agent tools in the first
  place, so "no further delegation" is natively guaranteed for now; the
  `[agents] enabled = false` and written rules in the Codex rendering are
  insurance against a future release opening up nested spawning. What truly
  stays on the honor system is the finer tool restriction, such as requiring
  `explore` to use only read tools, which has no counterpart in Codex.
- **Coarser sandbox permissions**: Codex's sandbox is a three-way switch
  (read-only, workspace-write, danger-full-access); we set `explore` to
  read-only and the other two to write. Compared with Claude Code's ability
  to restrict specific tools directly, that is still a gap; moreover, the
  sandbox governs filesystem and execution permissions, not which tools a
  role actually reaches for.

To sum up, this repo provides basic dual-platform support. If you need
hardened safety guarantees (such as a strict forced stop or tool lockdown),
you will still have to tune things yourself against what the platform can do
at the time.
