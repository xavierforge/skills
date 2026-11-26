---
name: spec-viewer
description: Render one OpenSpec change into a single self-contained HTML review page with a built-in comprehension quiz, optionally with a zh-TW side gloss. Run manually to review a change fast instead of opening four Markdown files.
disable-model-invocation: true
model: haiku
effort: low
---

# /spec-viewer: one-page OpenSpec change review

Reviewing an OpenSpec change means reading four or more Markdown files
(`proposal.md`, `design.md`, `specs/*/spec.md`, `tasks.md`) in an editor and
holding the cross-references in your head. This skill collapses them into one
self-contained HTML page with a tab per file: click a tab to read that document
on its own, with a sidebar of its sections, requirements and scenarios visually
set apart, and the tasks checklist rendered with its checkbox state and a
completion bar. One file at a time keeps each document readable instead of one
long scroll. A trailing Quiz tab, after every document tab, tests whether the
reader actually understood the change; it is part of every run, not an
opt-in extra.

The skill is deliberately small. It dispatches one subagent to write a quiz
question bank, runs one generator script, and optionally emits one gloss
file. It does not diff changes, watch for edits, theme, or read a config
file. That is the whole scope; do not add to it.

## Invocation

The user triggers this with `/spec-viewer`, optionally followed by a change
directory and optionally a request for a zh-TW gloss. Resolve the invocation in
this order before doing anything else:

- **Which change?** If the user gave a path (an `openspec/changes/<name>/`
  directory), use it. If they gave none, look under `openspec/changes/` in the
  current project: if exactly one change directory is there, use it; if several
  are, list them and ask which one; if none, say so and stop. Never guess when
  more than one exists.
- **Gloss or not?** Only produce a zh-TW gloss when the user asks for one (any
  request to the effect of "with a Chinese gloss", "加中文", "zh-TW"). A bare
  `/spec-viewer <dir>` still runs the full default pipeline below, quiz
  included; the gloss is the only piece that stays opt-in. If a
  `gloss.zh-TW.json` already sits next to the change, Step 3 embeds it
  automatically with no extra work, so a repeat run keeps the existing gloss
  without regenerating it.

Once the change is resolved, run Step 1 and Step 2 every time, in order, and
Step 3 only if a gloss was asked for. Step 2's closing `open` is a hard step
too, not something to wait on the user for.

## What it produces

A single HTML file (inline CSS and JS, no external requests, no server, no watch
mode) written next to the change as `review.html`, or to a path you give.
Regenerating is one command, so re-run it after editing the change rather than
hand-patching the HTML.

The script (`generate.py`, python3 stdlib only) does the Markdown-to-HTML and the
layout deterministically. It reads the fixed OpenSpec file set but tolerates
absences: `design.md` may be missing, and `specs/` may hold several files (each
becomes its own section group). The English text in the change is the normative
source and is rendered verbatim; the page never rewrites it.

The page's last tab is Quiz: multiple-choice comprehension questions over the
whole change, revealed 8 at a time, each locking on the correct answer with a
one-line citation back to the source file. All of this tab's HTML, CSS, and
JS live in `generate.py`'s fixed template; no LLM, worker or main session,
ever writes markup for it. Only the question data is generated per change
(Step 1 below).

When `/vibe-diff`'s `diff-review.html` already sits next to the change, the page
links into it automatically: a `diff review ↗` link in the topbar, and a
per-requirement `diff ↗` anchor pointing at `diff-review.html#<section-id>`
(the twin gives its intent-map entries these same ids, so the jump lands on
that requirement's implementing hunks). Absent that file, no links are emitted.
This means the ordering matters: a `review.html` generated before the diff page
existed has no links, so re-run Step 2 after `/vibe-diff` writes its page.

## Step 1. Produce the quiz question bank

Dispatch a subagent to write the quiz question bank as
`<change>/review-quiz.json`, before touching `generate.py`. This dispatch
happens on every invocation, even when `review-quiz.json` already exists from
a previous run: overwrite it. (The one exception is the explicit *Asking for
more questions* flow below, which appends to an existing bank instead of
overwriting it.) The main session never writes quiz questions itself: all
comprehension content comes from the dispatched worker, and all HTML, CSS,
and JS for the Quiz tab come from `generate.py`, never from the worker.

Dispatch with `subagent_type: too-te` (the executor role for fully-specified work, defined in `agents/`). If the harness has no `too-te` role
installed, fall back to `subagent_type: general-purpose` with an explicit
cheap `model` override; never dispatch a rosterless general subagent without
naming a model.

The brief must be self-contained: restate, or point directly at, the rules
below. A partial brief that leaves the worker guessing at the contract is a
spec defect, not something to patch with subagent judgment.

**Source material.** Limit questions to whichever of `proposal.md`,
`design.md`, `tasks.md`, and `decisions.md` actually exist in the change
directory. Never invent content for a file that is not there. Question
language follows the source documents (English).

**Bank size.** 24 questions by default. If the change's material is thin, the
worker may drop to 12, but its report back must say why (for example, "only
proposal.md and tasks.md exist, and both are short").

**Distractors.** Every wrong option must be a plausible misreading, never a
straw man. Prefer wrong options built from a path the source material
explicitly rules out: a `decisions.md` ruling, a `design.md` Non-Goal, or a
named rejected alternative, restated as if it had been the chosen path.

**Citations.** Every option, right or wrong, needs a one-sentence "why", and
each question's citation must point at real, checkable text: a filename plus
either a verbatim quote or a line reference. A citation that cannot be
grepped back to the source file is a defect, not a style issue (see
*Spot-check before generating* below).

**Format.** Write a JSON array; see `load_quiz` in `scripts/generate.py` for
the exact schema `generate.py` validates against (`id`, `q`, `options`,
`correct`, `why`, `cite`). If `generate.py` rejects the file in Step 2 (schema
error, exit code 2), fix or redispatch before opening anything.
`generate.py` deterministically shuffles each question's option order at
render time, seeded from its id, so write `correct` at whatever index reads
naturally; the worker does not need to vary option position itself.

### Spot-check before generating

Once the worker reports back, read `review-quiz.json` yourself and check at
least 3 citations: `grep` the quoted text against the source file it names.
Do not trust a worker's citation at face value. If any citation is fabricated
(the quoted text does not actually appear in the file it claims to), reject
the whole file and redispatch; do not hand-patch individual questions. This
is not a theoretical risk: a worker has fabricated a citation before, which
is why this check is mandatory, not optional.

## Step 2. Generate the page

Run the generator with the change directory as its argument, via `uv run` so a
suitable Python is selected on any OS (uv is assumed present; this sidesteps the
`python3` vs `python` difference across platforms). `generate.py` lives in the
`scripts/` directory under this skill's base directory, the path announced when
the skill is invoked; build the command from that announced path, never from an
assumed install location such as `~/.claude/skills/`:

```
uv run <skill-base>/scripts/generate.py <path-to>/openspec/changes/<name>/ --quiz <path-to>/openspec/changes/<name>/review-quiz.json
```

The script is python3 stdlib only, so uv is a launcher, not a dependency: if
uv is missing, run the same path with `python3` directly. If neither exists,
name what is missing and offer to install uv; never fail silently.

By default the page is written to `<change>/review.html`, right inside the change
directory next to `proposal.md`. Leave it there: keeping the output in the change
folder is the intended layout, so do not redirect it elsewhere with `--out`
unless the user explicitly asks. The gloss file (Step 3) and the quiz file
(Step 1) live in the same folder for the same reason.

Options (rarely needed):

- `--out PATH` writes the HTML somewhere other than `<change>/review.html`.
- `--gloss PATH` points at a gloss JSON other than the default
  `<change>/gloss.zh-TW.json` (see Step 3).
- `--quiz PATH` points at a quiz JSON other than the default
  `<change>/review-quiz.json` written in Step 1.

The script prints the output path, a section count, the full list of
**section ids** it assigned, and whether it picked up a quiz file and how
many questions it holds. Those section ids are what a gloss file keys on, so
a first run with no gloss is also how you discover the ids to write one.

After a successful run, open the resulting `<path-to>/review.html` yourself
(`open` on macOS, `xdg-open` on Linux, `start` on Windows). This is a hard
step, not something to wait for the user to ask for; the point of the Quiz tab
is that a reviewer actually looks at it.

Stop after Step 2 unless a zh-TW reading aid is explicitly wanted.

## Step 3. Optional zh-TW gloss (additive reading aid only)

The page reserves a per-section side slot for a translation gloss. This is a
reading aid for the human reviewer, never a replacement: the normative English
is always rendered unchanged, and all prompting and review stay in English. The
gloss only helps a zh-TW reader parse the English faster; do not translate the
change, and do not let a gloss entry restate anything in a way that could be
mistaken for the spec.

To add one:

1. Run Step 2 once and read the printed section ids.
2. Write a JSON object keyed by section id. Include only the entries worth
   glossing: section headings and the one or two key sentences of a section, not
   a full translation of the body. A value is a short zh-TW string (use `\n` to
   split it into separate lines). Keys that match no section are reported and
   ignored, so a partial gloss is fine.
3. Save it as `<change>/gloss.zh-TW.json`, inside the change directory alongside
   `review.html`, and re-run Step 2 (still passing `--quiz`). That default path
   is picked up automatically on every later run, so the gloss persists with the
   change; only use `--gloss PATH` for a one-off location the user names. The
   script embeds each entry beside its section and switches the page to the
   two-column gloss layout.

Example `gloss.zh-TW.json`:

```json
{
  "proposal--why": "為什麼要改：最新的每日記憶會被大的 MEMORY.md 擠掉。",
  "spec-foo--requirement-section-priority-order": "區段優先順序需求"
}
```

## Asking for more questions

When the user comes back later and asks for more questions on a change
already reviewed, do not start a fresh bank. Dispatch the worker again,
passing it the existing `review-quiz.json` and its highest `id`, and tell it
to continue numbering from there and append to the same file, never renumber
or rewrite existing entries. Then re-run Step 2. Existing ids stay stable so
a reader's in-progress localStorage state for already-answered questions is
untouched; only the newly appended questions start unanswered.

The default `model` / `effort` pin in the frontmatter is sized for
this skill's actual work: dispatch the quiz worker, spot-check its output,
run the script, open the result, and, if asked, produce the gloss JSON. The
question-writing work itself runs on the dispatched worker's own model
(`too-te`'s default, or the named cheap fallback), off this frontmatter's
budget. Only bump the pin one tier up if the main session's own spot-check judgment,
or gloss quality, proves insufficient.
