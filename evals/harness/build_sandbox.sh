#!/usr/bin/env bash
# Build an isolated git sandbox with the precondition for one behavioral eval.
# Usage: build_sandbox.sh <skill> <eval_id> <target_worktree_dir>
set -euo pipefail

SKILL="${1:?skill}"; ID="${2:?eval id}"; TARGET="${3:?target dir}"
PARENT="$(dirname "$TARGET")"
ORIGIN="${PARENT}/origin.git"
mkdir -p "$PARENT"
rm -rf "$TARGET" "$ORIGIN"
mkdir -p "$TARGET"

export GIT_AUTHOR_NAME="Eval Bot" GIT_AUTHOR_EMAIL="eval@example.com"
export GIT_COMMITTER_NAME="Eval Bot" GIT_COMMITTER_EMAIL="eval@example.com"

g() { git -C "$TARGET" "$@"; }

seed_project() {
  mkdir -p "$TARGET/src" "$TARGET/tests"
  : > "$TARGET/conftest.py"
  : > "$TARGET/src/__init__.py"
  : > "$TARGET/tests/__init__.py"
  cat > "$TARGET/src/greetings.py" <<'PY'
def hello(name):
    return f"Hello, {name}!"
PY
  cat > "$TARGET/tests/test_greetings.py" <<'PY'
from src.greetings import hello


def test_hello():
    assert hello("Ada") == "Hello, Ada!"
PY
  # A second, unrelated module + test so the full gate (`make check`) is broader
  # than any one section's tests. This makes "run the full gate only at the end,
  # not per task" observable: the section-relevant Red check is a narrow
  # `pytest tests/test_greetings.py`, distinct from the whole-suite gate.
  cat > "$TARGET/src/mathutil.py" <<'PY'
def add(a, b):
    return a + b
PY
  cat > "$TARGET/tests/test_mathutil.py" <<'PY'
from src.mathutil import add


def test_add():
    assert add(2, 3) == 5
PY
  cat > "$TARGET/Makefile" <<'MK'
.PHONY: check
check:
	pytest -q
MK
  cat > "$TARGET/AGENTS.md" <<'MD'
# Agent instructions

Quality gate for this project: `make check` (runs the full pytest suite).
Do not substitute a bare compile or a single-file run for the gate.
MD
  cat > "$TARGET/.gitignore" <<'GI'
__pycache__/
*.pyc
.pytest_cache/
GI
  cat > "$TARGET/README.md" <<'MD'
# greetings

A tiny greetings library.
MD
}

seed_tasks() {
  local role="$1"
  mkdir -p "$TARGET/openspec/changes/add-farewell"
  cat > "$TARGET/openspec/changes/add-farewell/proposal.md" <<'MD'
# Add a farewell helper

## Why
The library can greet but cannot say goodbye.

## What changes
- Add `farewell(name)` returning "Goodbye, {name}!".
- Add `greet_all(names)` returning a list of greetings.
MD
  cat > "$TARGET/openspec/changes/add-farewell/tasks.md" <<MD
# Tasks

## Dispatch
- Section 1: ${role}
- Section 2: main

## 1. Add farewell helper  [dispatch: ${role}, parallel: no]
- [ ] 1.1 Write a failing test for \`farewell(name)\` returning "Goodbye, {name}!"
- [ ] 1.2 Implement \`farewell\` in src/greetings.py so the test passes

## 2. Add greet_all helper  [dispatch: main, parallel: no]
- [ ] 2.1 Write a failing test for \`greet_all(names)\`
- [ ] 2.2 Implement \`greet_all\` in src/greetings.py so the test passes
MD
}

init_origin() {
  local def="$1"
  git init --bare -b "$def" "$ORIGIN" >/dev/null
  g remote add origin "$ORIGIN"
  g push -u origin "$def" >/dev/null 2>&1
  g remote set-head origin "$def" >/dev/null 2>&1
}

advance_origin() {
  local def="$1" tmp
  tmp="$(mktemp -d)"
  git clone -q "$ORIGIN" "$tmp"
  git -C "$tmp" config user.name "Upstream Bot"
  git -C "$tmp" config user.email "up@example.com"
  echo "upstream change" >> "$tmp/README.md"
  git -C "$tmp" commit -qam "docs(readme): note upstream change"
  git -C "$tmp" push -q origin "$def"
  rm -rf "$tmp"
  # Advance the sandbox's own remote-tracking ref so it reflects the now-ahead
  # origin while local "$def" stays stale. Without this fetch the tracking ref
  # would still equal local "$def", and a `ref_equals <def> origin/<def>` check
  # would pass on a run that never synced (a no-op passes the "default branch
  # fast-forwarded" assertion). The precondition these fixtures set up is
  # "origin is ahead, local is stale", so the tracking ref must show it.
  g fetch -q origin "$def"
}

# The factory fixtures gate with stdlib unittest instead of pytest so they run
# on hosts without any Python packages installed.
seed_unittest_gate() {
  local T="$1"
  cat > "$T/tests/test_greetings.py" <<'PY'
import unittest

from src.greetings import hello


class TestHello(unittest.TestCase):
    def test_hello(self):
        self.assertEqual(hello("Ada"), "Hello, Ada!")
PY
  rm -f "$T/src/mathutil.py" "$T/tests/test_mathutil.py" "$T/conftest.py"
  cat > "$T/Makefile" <<'MK'
.PHONY: check
check:
	python3 -m unittest discover -s tests -t . -q
MK
  cat > "$T/AGENTS.md" <<'MD'
# Agent instructions

Quality gate for this project: `make check` (runs the full unittest suite).
Do not substitute a bare compile or a single-file run for the gate.
MD
}

seed_helpers_change() {
  mkdir -p "$TARGET/openspec/changes/add-helpers"
  cat > "$TARGET/openspec/changes/add-helpers/proposal.md" <<'MD'
# Add three helpers

## Why
The library can greet but cannot say goodbye, greet groups, or shout.

## What changes
- Add `farewell(name)` returning "Goodbye, {name}!".
- Add `greet_all(names)` returning a list of greetings.
- Add `shout(text)` returning the text uppercased with a "!".
MD
}

# One OpenSpec change (add-farewell) for the spec-viewer suite: a proposal with
# stable ## Why / ## What changes headings (so generate.py assigns the section
# ids proposal--why / proposal--what-changes a gloss can key on), one specs file,
# and a tasks checklist. Exactly one change so a bare /spec-viewer auto-selects it.
seed_spec_change() {
  mkdir -p "$TARGET/openspec/changes/add-farewell/specs/greetings"
  cat > "$TARGET/openspec/changes/add-farewell/proposal.md" <<'MD'
# Add a farewell helper

## Why
The library can greet but cannot say goodbye.

## What changes
- Add `farewell(name)` returning "Goodbye, {name}!".
- Add `greet_all(names)` returning a list of greetings.
MD
  cat > "$TARGET/openspec/changes/add-farewell/specs/greetings/spec.md" <<'MD'
# Greetings capability

## ADDED Requirements

### Requirement: Farewell helper
The system SHALL provide a `farewell(name)` returning "Goodbye, {name}!".

#### Scenario: basic farewell
- WHEN farewell("Ada") is called
- THEN it returns "Goodbye, Ada!"
MD
  cat > "$TARGET/openspec/changes/add-farewell/tasks.md" <<'MD'
# Tasks

## 1. Add farewell helper
- [ ] 1.1 Write a failing test for `farewell`
- [ ] 1.2 Implement `farewell`
MD
}

# The retro suite's tracked lessons ledger, seeded with the given entry line.
seed_lessons_ledger() {
  mkdir -p "$TARGET/docs"
  printf '# Lessons ledger\n\n%s\n' "$1" > "$TARGET/docs/lessons.md"
}

# A landed retro branch: a feature commit that leaves a debug print() in
# src/<module>.py, the review-driven fix that removes it, and the committed
# cross-check verdict recording that finding as actioned (committed so the
# baseline tree is clean, as in land/3).
seed_debug_print_branch() {
  local branch="$1" module="$2" slug
  slug="${branch//\//-}"
  g switch -qc "$branch"
  cat > "$TARGET/src/${module}.py" <<PY
import json


def render(record):
    print("DEBUG render", record)
    return json.dumps(record, sort_keys=True)
PY
  g add -A; g commit -qm "feat(${module}): add json rendering"
  cat > "$TARGET/src/${module}.py" <<'PY'
import json


def render(record):
    return json.dumps(record, sort_keys=True)
PY
  g commit -qam "fix(${module}): remove leftover debug print"
  mkdir -p "$TARGET/.review/${slug}"
  cat > "$TARGET/.review/${slug}/review-verdict.json" <<JSON
{
  "layer": "cross-check",
  "fixed_point": "main",
  "findings": [
    {"axis": "standards", "title": "leftover debug print() in src/${module}.py render()", "severity": "hard", "actioned": true}
  ]
}
JSON
  g add -A; g commit -qm "chore(review): record cross-check verdict for ${branch}"
}

case "${SKILL}/${ID}" in
  factory/1)  # one active change, three loop-ready sections, mixed dispatch roles
    g init -qb main
    seed_project; seed_unittest_gate "$TARGET"; seed_helpers_change
    cat > "$TARGET/openspec/changes/add-helpers/tasks.md" <<'MD'
# Tasks

## 1. Add farewell helper  [dispatch: too-te, parallel: no]
- [ ] 1.1 Write a failing unittest for `farewell(name)` returning "Goodbye, {name}!"
- [ ] 1.2 Implement `farewell` in src/greetings.py so the test passes

## 2. Add greet_all helper  [dispatch: main, parallel: no]
- [ ] 2.1 Write a failing unittest for `greet_all(names)` returning a list of hello greetings
- [ ] 2.2 Implement `greet_all` in src/greetings.py so the test passes

## 3. Add shout helper  [dispatch: sai-hu, parallel: no]
- [ ] 3.1 Write a failing unittest for `shout(text)` returning "TEXT!"
- [ ] 3.2 Implement `shout` in src/greetings.py so the test passes
MD
    g add -A; g commit -qm "chore: scaffold greetings project and add-helpers change"
    g switch -qc feat/add-helpers
    ;;
  factory/2)  # no openspec at all: the factory must refuse
    g init -qb main
    seed_project; seed_unittest_gate "$TARGET"
    g add -A; g commit -qm "chore: scaffold greetings project"
    g switch -qc feat/misc
    ;;
  factory/3)  # one active change whose tasks.md is not loop-ready (plan gate must act)
    g init -qb main
    seed_project; seed_unittest_gate "$TARGET"; seed_helpers_change
    cat > "$TARGET/openspec/changes/add-helpers/tasks.md" <<'MD'
# Tasks

## 1. Build all the helpers and docs  [dispatch: main, parallel: no]
- [ ] 1.1 Implement farewell, greet_all, and shout in src/greetings.py
- [ ] 1.2 Refresh the README with usage notes for every helper
MD
    g add -A; g commit -qm "chore: scaffold greetings project and add-helpers change"
    g switch -qc feat/add-helpers
    ;;
  section/1)
    g init -b main >/dev/null; g symbolic-ref HEAD refs/heads/main
    seed_project; seed_tasks "main"
    g add -A; g commit -qm "chore: scaffold greetings project and farewell change"
    g switch -qc feat/add-farewell
    ;;
  section/2)
    g init -b main >/dev/null
    seed_project; seed_tasks "main"
    mkdir -p "$TARGET/openspec/changes/refactor-hello"
    cat > "$TARGET/openspec/changes/refactor-hello/tasks.md" <<'MD'
# Tasks

## 1. Refactor hello  [dispatch: main, parallel: no]
- [ ] 1.1 Extract a greeting template
MD
    # archived, already-shipped change (must be excluded). It carries a
    # fully-formed Section 1 so excluding it demands reasoning about the archive/
    # convention, not merely finding nothing there to match.
    mkdir -p "$TARGET/openspec/changes/archive/2026-01-add-punctuation"
    cat > "$TARGET/openspec/changes/archive/2026-01-add-punctuation/tasks.md" <<'MD'
# Tasks

## 1. Add punctuation helper  [dispatch: main, parallel: no]
- [x] 1.1 Write a failing test for `shout(text)` returning "text!"
- [x] 1.2 Implement `shout` in src/greetings.py so the test passes
MD
    g add -A; g commit -qm "chore: scaffold project with two active changes"
    g switch -qc feat/execute
    ;;
  section/3)
    g init -b main >/dev/null
    seed_project; seed_tasks "sai-hu"
    g add -A; g commit -qm "chore: scaffold greetings project and farewell change"
    g switch -qc feat/add-farewell
    ;;
  begin/1)
    g init -b main >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    echo "scratch note" >> "$TARGET/README.md"
    ;;
  begin/2)  # origin default is AHEAD so a genuine sync must happen for a fresh lane
    g init -b main >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    advance_origin main   # origin/main now ahead; local main is stale
    g switch -qc feat/existing-work
    echo "work in progress" >> "$TARGET/src/greetings.py"
    g commit -qam "feat(greetings): start existing work (unpushed)"
    ;;
  begin/3)
    g init -b trunk >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin trunk
    advance_origin trunk
    ;;
  land/1)
    g init -b main >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    cat >> "$TARGET/src/greetings.py" <<'PY'


def farewell(name):
    return f"Goodbye, {name}!"
PY
    g commit -qam "feat(greetings): add farewell helper"
    ;;
  land/2)
    g init -b main >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    g switch -qc feat/json-export
    cat > "$TARGET/src/exporter.py" <<'PY'
import json


def to_json(record):
    return json.dumps(record, sort_keys=True)
PY
    cat > "$TARGET/tests/test_exporter.py" <<'PY'
from src.exporter import to_json


def test_to_json_sorts_keys():
    assert to_json({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
PY
    g add -A; g commit -qm "feat(exporter): add JSON export helper"
    mkdir -p "$TARGET/openspec/changes/add-json-export"
    cat > "$TARGET/openspec/changes/add-json-export/proposal.md" <<'MD'
# Add JSON export

## Why
Users need to export records as canonical JSON for downstream tools.

## What changes
- Add `to_json(record)` producing key-sorted JSON.
MD
    cat > "$TARGET/openspec/changes/add-json-export/tasks.md" <<'MD'
# Tasks

## 1. JSON export  [dispatch: main, parallel: no]
- [x] 1.1 Write a failing test for `to_json`
- [x] 1.2 Implement `to_json` with sorted keys
MD
    g add -A; g commit -qm "docs(openspec): record the json-export change"
    ;;
  land/3)  # land Step 0c: branch with a diff and only a vibe-diff
           # artifact on disk, no openspec, no cross-check/verify layers
    g init -b main >/dev/null
    seed_project
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    g switch -qc feat/demo-gadget
    cat >> "$TARGET/src/greetings.py" <<'PY'


def gadget(name):
    return f"[gadget] {name}"
PY
    g commit -qam "feat(greetings): add demo gadget helper"
    # Only the vibe-diff layer's artifact exists; cross-check and verify never
    # ran. Committed so the baseline tree is clean and "modifies nothing"
    # (git_clean) discriminates on what the run itself does.
    mkdir -p "$TARGET/.review/feat-demo-gadget"
    cat > "$TARGET/.review/feat-demo-gadget/diff-review.json" <<'JSON'
{
  "branch": "feat/demo-gadget",
  "layer": "vibe-diff",
  "test_status": {"command": "bash test.sh", "result": "pass", "count": 3},
  "overview": "Adds a demo gadget helper to the greetings module.",
  "findings": []
}
JSON
    g add -A; g commit -qm "chore(review): record vibe-diff artifact for the gadget diff"
    ;;
  vibe-diff/1)  # vibe-diff refusal: no openspec anywhere and no saved mini-spec,
                # a diff to review; the hardened skill must refuse (no spec source)
                # rather than write any artifact under .review/<slug>/
    g init -b main >/dev/null
    seed_project
    cat > "$TARGET/test.sh" <<'SH'
#!/usr/bin/env bash
exec make check
SH
    chmod +x "$TARGET/test.sh"
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    g switch -qc feat/add-logging
    cat > "$TARGET/src/greetings.py" <<'PY'
import logging

logger = logging.getLogger(__name__)


def hello(name):
    logger.info("greeting %s", name)
    return f"Hello, {name}!"
PY
    g commit -qam "feat(greetings): log each greeting"
    ;;
  cross-check/1)  # cross-check two-axis verdict: spec gap + standards breach
                  # in the diff, no openspec, verdict is written to .review/<slug>/
    g init -b main >/dev/null
    seed_project
    mkdir -p "$TARGET/docs"
    cat > "$TARGET/docs/spec.md" <<'MD'
# Parser specification

## Requirements
- R1: `parse(text)` splits `key=value` lines into a dict.
- R2: Blank lines and lines starting with `#` are ignored.
- R3: A duplicate key MUST be rejected with a ValueError ("reject duplicate keys").
MD
    cat > "$TARGET/CODING_STANDARDS.md" <<'MD'
# Coding standards
- Every public function carries a docstring.
- No copy-pasted parsing loops: factor shared logic into one helper.
MD
    g add -A; g commit -qm "docs: add parser spec and coding standards"
    init_origin main
    g switch -qc feat/parser
    # The diff under review: duplicated parsing loops, no docstring, and R3
    # (reject duplicate keys) left unimplemented.
    cat > "$TARGET/src/parser.py" <<'PY'
def parse(text):
    result = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        result[key] = value
    return result


def parse_strict(text):
    result = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        result[key] = value
    return result
PY
    g add -A; g commit -qm "feat(parser): add parse and parse_strict helpers"
    ;;
  spec-viewer/1)  # render: exactly one openspec change present, English only;
                  # /spec-viewer auto-selects it and writes review.html beside it
    g init -b main >/dev/null
    seed_project; seed_spec_change
    g add -A; g commit -qm "docs(openspec): add the add-farewell change to review"
    ;;
  spec-viewer/2)  # gloss: same single change; /spec-viewer <dir> with a zh-TW gloss
                  # runs generate, reads the section ids, writes gloss.zh-TW.json,
                  # then re-runs so the page embeds the gloss
    g init -b main >/dev/null
    seed_project; seed_spec_change
    g add -A; g commit -qm "docs(openspec): add the add-farewell change to review"
    ;;
  preflight/1)  # finished change with Non-Goals + a pre-placed cross-check verdict
                # carrying three findings (in-spec defect, Non-Goal collision,
                # out-of-scope). preflight must reconcile against the Non-Goals and
                # triage into three exits, writing decisions.md and landing no
                # commits. The review layers are absent in this harness, so they
                # must be reported not-run, not faked.
    g init -qb main
    seed_project; seed_unittest_gate "$TARGET"
    # A roadmap file so the out-of-scope finding has a place to be tracked.
    mkdir -p "$TARGET/docs"
    cat > "$TARGET/docs/ROADMAP.md" <<'MD'
# Roadmap

Future work not yet scheduled.
MD
    mkdir -p "$TARGET/openspec/changes/add-export"
    cat > "$TARGET/openspec/changes/add-export/proposal.md" <<'MD'
# Add a CSV export helper

## Why
Callers need to emit greeting records as CSV for spreadsheets.

## What changes
- Add `to_csv(rows)` in src/exporter.py returning comma-separated rows.
MD
    cat > "$TARGET/openspec/changes/add-export/design.md" <<'MD'
# Design: add-export

## Context
The greetings library can build greetings but cannot emit tabular output.

## Decision
Add `to_csv(rows)` to a new `src/exporter.py`, one comma-separated line per row.

## Non-Goals
- **JSON export is out of scope.** This change adds CSV only. A `to_json` helper
  is deliberately not part of it and belongs to a separate change.
- **No streaming or chunked output.** `to_csv` builds the whole string in memory;
  large-input streaming is not addressed here.
MD
    cat > "$TARGET/openspec/changes/add-export/tasks.md" <<'MD'
# Tasks

## 1. Add CSV export helper  [dispatch: too-te, parallel: no]
- [x] 1.1 Write a failing unittest for `to_csv(rows)`
- [x] 1.2 Implement `to_csv` in src/exporter.py so the test passes
MD
    # Pre-placed cross-check verdict: three findings, one per triage exit.
    cat > "$TARGET/openspec/changes/add-export/review-verdict.json" <<'JSON'
{
  "layer": "cross-check",
  "fixed_point": "main",
  "findings": [
    {"axis": "spec", "title": "to_csv does not escape values containing a comma or a newline, so a field like \"Ada, Jr\" breaks the row; the change was supposed to emit valid CSV", "severity": "hard", "actioned": false},
    {"axis": "spec", "title": "the exporter offers no to_json helper; add JSON export alongside to_csv for output-format parity", "severity": "judgement", "actioned": false},
    {"axis": "standards", "title": "public functions in src/greetings.py and src/exporter.py carry no type hints", "severity": "judgement", "actioned": false}
  ]
}
JSON
    cat > "$TARGET/src/exporter.py" <<'PY'
def to_csv(rows):
    return "\n".join(",".join(str(cell) for cell in row) for row in rows)
PY
    cat > "$TARGET/tests/test_exporter.py" <<'PY'
import unittest

from src.exporter import to_csv


class TestToCsv(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(to_csv([["a", "b"], ["c", "d"]]), "a,b\nc,d")
PY
    g add -A; g commit -qm "feat(exporter): add csv export change with review verdict"
    g switch -qc feat/add-export   # cut at the finished tip: the run adds nothing
    ;;
  preflight/2)  # finished change but the repo has no test suite, no gate, and no
                # verify skill; preflight must record the mechanical and runtime
                # layers honestly (absent / not run) and never fake a green pass.
    g init -qb main
    mkdir -p "$TARGET/src"
    cat > "$TARGET/src/slug.py" <<'PY'
def slugify(text):
    return "-".join(text.lower().split())
PY
    cat > "$TARGET/README.md" <<'MD'
# tinyslug

A tiny slug helper. No test suite, no build gate.
MD
    mkdir -p "$TARGET/openspec/changes/add-slugify"
    cat > "$TARGET/openspec/changes/add-slugify/proposal.md" <<'MD'
# Add a slugify helper

## Why
Callers need a URL-safe slug from a title.

## What changes
- Add `slugify(text)` in src/slug.py lowercasing and joining words with hyphens.
MD
    cat > "$TARGET/openspec/changes/add-slugify/tasks.md" <<'MD'
# Tasks

## 1. Add slugify helper  [dispatch: too-te, parallel: no]
- [x] 1.1 Implement `slugify` in src/slug.py
MD
    g add -A; g commit -qm "feat(slug): add slugify change"
    g switch -qc feat/add-slugify   # cut at the finished tip: the run adds nothing
    ;;
  vibe-diff/2)  # vibe-diff happy path via the mini-spec fallback: no openspec, a
                # saved .review/<slug>/mini-spec.md as the spec source, and a small
                # diff on the branch; the skill captures the diff and renders the page.
    g init -b main >/dev/null
    seed_project
    printf '.review/\n' >> "$TARGET/.gitignore"
    cat > "$TARGET/test.sh" <<'SH'
#!/usr/bin/env bash
exec make check
SH
    chmod +x "$TARGET/test.sh"
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    g switch -qc feat/add-metrics
    cat > "$TARGET/src/metrics.py" <<'PY'
def count_greetings(names):
    return len(list(names))
PY
    cat > "$TARGET/tests/test_metrics.py" <<'PY'
from src.metrics import count_greetings


def test_count_greetings():
    assert count_greetings(["Ada", "Bea"]) == 2
PY
    g add -A; g commit -qm "feat(metrics): add greeting counter"
    # The saved mini-spec (what /begin persists from its invocation args) is the
    # spec source for the fallback path. .review/ is gitignored local scratch.
    mkdir -p "$TARGET/.review/feat-add-metrics"
    cat > "$TARGET/.review/feat-add-metrics/mini-spec.md" <<'MD'
# Mini-spec: greeting metrics

Add a `count_greetings(names)` helper to `src/metrics.py` that returns how many
names were greeted, so callers get a simple tally of processed names.

Out of scope: persistence, per-name breakdowns.
MD
    ;;
  factory/4)  # one active change whose first pickable group is two adjacent
              # [parallel: yes] sections, mutually independent (distinct files, no
              # cross-reference); the foreman must hand back a lane plan, not run them.
    g init -qb main
    seed_project; seed_unittest_gate "$TARGET"
    mkdir -p "$TARGET/openspec/changes/add-helpers"
    cat > "$TARGET/openspec/changes/add-helpers/proposal.md" <<'MD'
# Add two independent helpers

## Why
The library can greet but cannot say goodbye or shout, and the two are unrelated.

## What changes
- Add `farewell(name)` in src/farewell.py returning "Goodbye, {name}!".
- Add `shout(text)` in src/shout.py returning the text uppercased with a "!".
MD
    cat > "$TARGET/openspec/changes/add-helpers/tasks.md" <<'MD'
# Tasks

## 1. Add farewell helper  [dispatch: too-te, parallel: yes]
- [ ] 1.1 Write a failing unittest in tests/test_farewell.py for `farewell(name)` returning "Goodbye, {name}!"
- [ ] 1.2 Implement `farewell` in src/farewell.py so the test passes

## 2. Add shout helper  [dispatch: too-te, parallel: yes]
- [ ] 2.1 Write a failing unittest in tests/test_shout.py for `shout(text)` returning the text uppercased with a "!"
- [ ] 2.2 Implement `shout` in src/shout.py so the test passes
MD
    g add -A; g commit -qm "chore: scaffold greetings project and add-helpers change"
    g switch -qc feat/add-helpers
    ;;
  retro/1)  # retro first occurrence: a landed branch whose cross-check verdict
            # shows a leftover debug print fixed after review, no openspec, and a
            # lessons ledger holding one unrelated class. retro must append exactly
            # one [seen] line and touch nothing else; the tag pins "no commit".
    g init -qb main
    seed_project
    seed_lessons_ledger "- 2026-09-14 [seen] stale-readme-table: README skill table missed a new skill (evidence: https://example.invalid/pr/3)"
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    seed_debug_print_branch feat/cli-json cli
    g tag retro-fixture-tip
    ;;
  retro/2)  # retro second occurrence: the ledger already holds one evidenced
            # leftover-debug-output line (pointing at a real fix commit on main),
            # and the landed branch repeats the mistake. retro must reuse the slug,
            # append the second [seen] line, propose an enforcer, and stop for
            # approval without touching AGENTS.md or scripts/.
    g init -qb main
    seed_project
    mkdir -p "$TARGET/scripts"
    cat > "$TARGET/scripts/diff-scan.sh" <<'SH'
#!/usr/bin/env bash
# Pre-PR scan: every commit subject since the base must be a Conventional Commit.
set -euo pipefail
base="${1:?base ref}"
bad=$(git log --format=%s "$base"..HEAD | grep -Ev '^(feat|fix|docs|test|refactor|chore|perf|build|ci)(\([a-z0-9-]+\))?: ' || true)
if [ -n "$bad" ]; then echo "non-conventional subjects:"; echo "$bad"; exit 1; fi
echo "diff-scan: clean"
SH
    chmod +x "$TARGET/scripts/diff-scan.sh"
    g add -A; g commit -qm "chore: initial project"
    # The earlier occurrence: a console.log that review caught on a past change.
    mkdir -p "$TARGET/web"
    printf 'export function boot() {\n  console.log("boot debug");\n  return true;\n}\n' > "$TARGET/web/app.js"
    g add -A; g commit -qm "feat(web): add app bootstrap"
    printf 'export function boot() {\n  return true;\n}\n' > "$TARGET/web/app.js"
    g commit -qam "fix(web): drop leftover console.log"
    seed_lessons_ledger "- 2026-10-02 [seen] leftover-debug-output: console.log left in web/app.js, removed after review (evidence: commit $(g rev-parse --short=7 HEAD))"
    g add -A; g commit -qm "docs(lessons): record the leftover console.log"
    init_origin main
    seed_debug_print_branch feat/report-export report
    g tag retro-fixture-tip
    ;;
  retro/3)  # retro unevidenced claim: the user says the formatter was skipped
            # again, but there is no .review/, no formatter config, and no fixup
            # or review-driven commit. retro must record nothing (clean tree).
    g init -qb main
    seed_project
    seed_lessons_ledger "- 2026-09-14 [seen] stale-readme-table: README skill table missed a new skill (evidence: https://example.invalid/pr/3)"
    g add -A; g commit -qm "chore: initial project"
    init_origin main
    g switch -qc feat/add-greeting
    cat >> "$TARGET/src/greetings.py" <<'PY'


def greet_formal(name):
    return f"Good day, {name}."
PY
    g commit -qam "feat(greetings): add formal greeting"
    g tag retro-fixture-tip
    ;;
  *)
    echo "unknown skill/eval: ${SKILL}/${ID}" >&2; exit 2 ;;
esac

echo "built ${SKILL}/${ID} at ${TARGET}"
