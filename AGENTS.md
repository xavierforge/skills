# AGENTS.md

Discipline for any agent or contributor working inside this repo. Keep it short and follow it exactly.

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
- `README.md` and `README.zh-TW.md` are mirrors: change both together, and keep the version badges and structure aligned.

## Evals

- `evals/` is a Claude Code-only measurement layer that calls the `claude` CLI directly. It does not move with the dual-harness wording, and its `--dangerously-skip-permissions` usage is a deliberate, sandboxed choice; leave it as is.
