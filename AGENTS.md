# AGENTS.md

Discipline for any agent or contributor working inside this repo. Keep it short and follow it exactly.

## Setup runbook

When the user asks to set up this machine or a project, execute this section top to bottom and report what was installed and what was skipped. Everything else in this file is discipline; this part is work. Run from this repo's root.

Machine setup (once per machine):

1. **Skills**: `npx skills add xavierforge/skills` if npx is available; otherwise the symlink loop:
   `for s in skills/*/; do ln -sfn "$PWD/$s" ~/.claude/skills/"$(basename "$s")"; done`
2. **Role roster, Claude Code** (symlink, so it follows this repo):
   `for f in agents/claude/*.md; do ln -sfn "$PWD/$f" ~/.claude/agents/"$(basename "$f")"; done`
3. **Role roster, Codex** (copy, not symlink: Codex rejects linked agent files, reads only the user-wide folder; re-copy after any roster edit):
   `mkdir -p ~/.codex/agents && cp agents/codex/*.toml ~/.codex/agents/`
4. **Verify**: `ls -l ~/.claude/skills ~/.claude/agents` shows links resolving into this repo; `ls ~/.codex/agents` lists the three role toml files.

Project setup (per project that wants the full pipeline):

5. **OpenSpec**: initialize it in the target project per OpenSpec's own docs if `openspec/` does not exist there.
6. **Rule template**: `cp openspec-rules/config.template.yaml <project>/openspec/config.yaml`. This turns on the tasks/design rules the skills expect (plan lint, verification evidence, the `decisions.md` ledger); see [`openspec-rules/README.md`](openspec-rules/README.md).

Never edit installed copies; this repo is the source of truth.

## Commit and branch style

- Conventional Commits: `type(scope): imperative subject`. Lowercase scope named after the subsystem (`skills`, `agents`, `evals`, `docs`). The subject must not contain "and"; if it needs one, split the commit.
- One commit per coherent, reviewable decision.
- Branch names: `<type>/<kebab-case-description>`.
- No em-dash or en-dash anywhere in the repo: commit messages, PR and issue text, and prose. Restructure with commas, parentheses, or colons instead.

## Portability

- No model names in skill bodies or in any `agents/openai.yaml`. Model names live only in `agents/claude/*.md` frontmatter and in spec-viewer's existing `model:` pin. Everywhere else, route by role.
- No personal absolute paths and no private repo names in skill bodies, descriptors, or docs. Reference a skill's own files through its base directory, not a hardcoded install path.
- Dispatch by role name. On a role's first mention in a given file, note the role in parentheses so a reader who does not know the roster can still follow.

## Sync rules

- `agents/claude/*.md` are the role source of truth. Any installed copy must be byte-for-byte identical to the file here.
- Each skill's `agents/openai.yaml` Codex descriptor tracks that skill's SKILL.md `description`; update the descriptor whenever the description changes.
- Every `<doc>.md` with a `<doc>.zh-TW.md` sibling is a mirror pair (today: the root README, `agents/README.md`, `evals/EVALUATION.md`): change both together, keep structure aligned. The zh-TW rendering is a natural translation that keeps English jargon, never a literal one.

## Evals

- `evals/` is a Claude Code-only measurement layer that calls the `claude` CLI directly. It does not move with the dual-harness wording, and its `--dangerously-skip-permissions` usage is a deliberate, sandboxed choice; leave it as is.
