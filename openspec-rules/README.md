# openspec-rules

Shared source of truth for the OpenSpec `rules` that every repo running the opsx
workflow should carry. `config.template.yaml` holds the canonical rule set;
each repo gets an instance copied into its own `openspec/config.yaml`.

## What the template gives you

`config.template.yaml` is a full `openspec/config.yaml` (schema `spec-driven`)
whose `rules` block encodes the workflow conventions we want enforced at
artifact-generation time:

- **`tasks`**: the tasks.md contract (vertical slices, one-commit sections,
  dispatch annotations), the mandatory plan lint, a per-task verification
  evidence rule (a task's "done" must cite real execution evidence, not a bare
  checkbox), and the decision ledger below.
- **`design`**: a decision reconciliation list closing every design.md, so the
  user can audit decisions against a checklist instead of re-reading the whole
  document.

Rules are keyed by artifact ID. OpenSpec only accepts the schema's artifact IDs
(`proposal`, `specs`, `design`, `tasks`) as keys and warns on and ignores any
other key, so a rule that fires during a phase lives on the artifact that phase
produces (verification evidence and the decision ledger on `tasks`, decision
reconciliation on `design`), never on a phase name like `verify` or `propose`.

### The decision ledger (`decisions.md`)

Each change directory carries a `decisions.md` beside `tasks.md`, holding the
rulings made **after execution started**, one per line, tagged `[caveat]`,
`[reversal→pending]` / `[reversal→denied]` / `[reversal→accepted]`,
`[included]`, or `[tracked]`, each line carrying its date and its source. It
is a repo artifact, so it is written in English like the proposal, the
design, and the commit messages.

The split with `design.md` is the point: `design.md`'s Non-Goals and its
reconciliation list are the **pre-start** record and stay authoritative, so the
ledger never copies them and a later ruling never gets retro-edited into the
design. What the ledger closes is the gap after that: a caveat found
mid-implementation, a review finding refused because the design already ruled
it out, a scope call made under pressure: facts that used to live only in a
session log and were gone by the next review. `/preflight` reads Non-Goals and
this ledger together as its reconciliation baseline, and writes every triage
ruling back into it.

The ledger is hosted on `tasks` rather than `design` because execution is the
phase that produces it, the same reason the verification-evidence rule sits
there. It is archived with its change like every other file in the directory,
and in a repo whose `openspec/` is untracked via `.git/info/exclude` it
inherits that and stays local, with no special case anywhere.

## Instantiating in a repo

1. Copy the template into the target repo:

   ```
   cp openspec-rules/config.template.yaml <repo>/openspec/config.yaml
   ```

2. Add a provenance note as the very first lines of the copied
   `<repo>/openspec/config.yaml` (above `schema:`), recording where the instance
   came from and which template revision it matches.

3. Merge in any repo-local rules the instance needs on top of the shared set.

### Provenance note format

Put this comment block at the head of the instantiated `config.yaml`:

```yaml
# Instantiated from: skills/openspec-rules/config.template.yaml
# Template sha256: <sha256 of config.template.yaml>
# Instantiated: <YYYY-MM-DD>
```

Compute the hash against the template file itself:

```
shasum -a 256 openspec-rules/config.template.yaml
```

### Why sha256, not a commit hash

The provenance note pins the template by content hash, not by the commit that
introduced it. The skills repo is maintained with a rebase-and-merge history:
rebasing or squashing a branch rewrites commit hashes, so a recorded commit hash
can point at a commit that no longer exists on `main`. A sha256 of the template
file is stable across any history rewrite: it identifies the exact bytes the
instance was aligned to, and re-running `shasum` on the current template tells
you at a glance whether an instance is still in sync or has drifted.
