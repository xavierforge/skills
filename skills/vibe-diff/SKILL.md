---
name: vibe-diff
description: Render a branch's diff against its merge-base into one self-contained diff-review.html, read against the OpenSpec change it implements, the right-side twin of /spec-viewer. Run manually in a fresh session after a change's sections are executed, before /land's adversarial review.
disable-model-invocation: true
---

# /vibe-diff: one-page diff review, judgment layered over a template

After a change's sections are all executed, the human review surface collapses
to a raw diff plus a PR body: a wall of `+`/`-` lines the reviewer decodes line
by line before they can think about architecture or risk. `/spec-viewer` turns
the left side of a review (the spec) into one navigable page; this is the right
side, the diff, explained so attention goes to what changed and why it matters.

The work splits into two layers with a hard boundary. The **mechanical layer**
is `scripts/generate.py` in this skill: it parses the captured diff, computes
the diffstat, escapes and embeds every hunk under a stable id, cross-links the
spec-viewer twin, and lays out the page. The **judgment layer** is yours: a
`diff-review.json` holding the explanation (what the diff does, which hunks
implement which requirement, where behavior shifts, which lines deserve a
margin note). You never write HTML, CSS, or escaping, and you never write the
file itself; a dispatched subagent does that carpentry, the script never
writes a sentence of judgment.

**vibe-diff explains, it never judges.** The page is a map, not a verdict: no
approve/block signal, no "this is fine" or "you must fix this." Surface what a
reviewer would want to look at twice; let them decide. Judging the diff is
`/land`'s adversarial review, a separate, later, blocking gate.

## Precondition: run in a fresh session

Author this in a session that did not write the code under review. A session
that watched the feature get built inherits its blind spots and will summarize
the diff the way the author already thinks about it, which is exactly the
reading a reviewer does not need. Fresh eyes reading the raw diff cold is the
whole value. If you wrote this code, say so and let the user start a clean
session instead.

Check this mechanically before doing anything else: if this session has
already run an Edit or Write against any tracked source file in this repo,
the reviewer is the author. Refuse to run, say so plainly (naming that this
session edited or wrote tracked files earlier), and tell the user to run
`/vibe-diff` from a new session instead. This is a hard gate, not a judgment
call: a 2026-07-16 run authored a review in the same session as the
implementation, took three minutes, and produced no real anchoring, exactly
the failure mode this precondition exists to catch before it happens again.

## Step 1. Gather the inputs

- **Which change, and where artifacts are written.** If the user named an
  `openspec/changes/<name>/` directory, use it. Otherwise list
  `openspec/changes/` (excluding `archive/`): one active change, use it;
  several, list them and ask. The chosen change directory is the
  **artifact dir**, written `<artifact_dir>` below: `diff.patch`,
  `diff-review.json`, and `diff-review.html` are all written there, nowhere else.
  If there is no active change (or no `openspec/` at all), say so and fall
  back to `.review/<slug>/` at the repo root as the artifact dir, where
  `<slug>` is the branch name with `/` replaced by `-`
  (`feat/hook-system` → `.review/feat-hook-system/`); create it if missing.
  This two-tier **artifact directory rule** (active change dir, else `.review/<slug>/`)
  is the same resolution `/land`'s reconciliation step and cross-check's
  verdict artifact use, so never invent a third location. `.review/` is local review scratch, not part
  of the shipped work: leave it uncommitted (suggest adding `.review/` to
  `.gitignore` if the repo does not already ignore it).
- **The spec, resolved in this order.** (1) An active `openspec/changes/`
  entry: read `proposal.md`, `design.md` if present, and every
  `specs/**/*.md` in the change. (2) No active change: fall back to
  `.review/<slug>/mini-spec.md`, the text `/begin` saves from its invocation
  args, if that file exists, read it as the spec in full. (3) Neither
  exists: refuse to run. Say so plainly and point at the fix: run `/begin`
  with the work described in its command args (that, and only that, is what
  makes it save a mini-spec), or open an OpenSpec change,
  then invoke `/vibe-diff` again. A diff reviewed against nothing to check it
  against is not a review. When (2) supplied the spec, skip the spec-page
  bullet below (there is no `openspec/` for `/spec-viewer` to render), still
  build `intent_map` off the mini-spec's stated intent, and note in the
  overview that the spec source was a mini-spec, not an OpenSpec change.
- **The spec page.** Regenerate the twin so its section ids are current:
  `uv run <skill-base>/../spec-viewer/scripts/generate.py <artifact_dir>`, where
  `<skill-base>` is this skill's base directory (the path announced when the
  skill is invoked; the spec-viewer skill sits beside this one, never assume an
  install location). If the sibling is missing, spec-viewer is not installed;
  proceed without it and this script degrades gracefully (no cross-links).
- **Last test run.** Get the command, when it ran, and the pass/fail summary,
  in this order: what the user gave you at invocation; failing that, run the
  project's test command yourself and use that result. If you cannot locate
  the command or it will not run cleanly, the status is unobtainable, but try
  before you settle for that: an unobtainable status is honest, a skipped
  attempt is not.

## Step 2. Capture the diff and print the contract

Fetch first (`git fetch`) so the base ref is current. The base defaults to the
repo's default branch (`git symbolic-ref refs/remotes/origin/HEAD`, usually
`main`); if it differs and you cannot tell, ask. Capture the diff to a file
(never work from a diff pasted earlier in the conversation, which may be
stale), then run the renderer once:

```
git diff --no-color -M <base>...HEAD > <artifact_dir>/diff.patch
uv run <skill-base>/scripts/generate.py <artifact_dir> --base <base> --branch <branch>
```

`<artifact_dir>` is the directory Step 1 resolved (the active change dir, or
`.review/<slug>/` in the fallback); the script takes either without caring
which tier it is.

The script writes a skeleton page (diffstat plus all hunks) and prints the
**authoring contract**: every hunk id and, when `review.html` exists, every
spec requirement section id. Those ids are the only handles Step 3 may use;
never invent one.

Both generators are python3 stdlib only, so uv is a launcher, not a
dependency: if uv is missing, run the same paths with `python3` directly. If
neither exists, name what is missing and offer to install uv; never fail
silently.

## Step 3. Decide the judgment layer

Now read the diff and the spec for real, and work out everything that will
go into `<artifact_dir>/diff-review.json`: the overview, scope creep, intent
map, risks, hotspots with their hunk anchors, and the unverified list. This
analysis is the whole reason the skill exists, and it stays in this session.
Do not write the file yourself; Step 4 packages what you decided here into a
dispatch brief and hands the writing to a subagent. Every string value is
plain prose with an inline `code` / `**bold**` subset; no HTML ever. The
target shape:

```json
{
  "test_status": {"command": "cargo test", "when": "2026-07-13, this session", "result": "pass, 14 tests"},
  "overview": ["One or more paragraphs mapping the diff to the spec's intent."],
  "scope_creep": ["Anything the diff does that the spec never asked for."],
  "intent_map": [
    {"id": "spec-foo--requirement-bar", "title": "Requirement: Bar",
     "items": [{"text": "what implements it", "hunks": ["hunk-src-foo-rs"]}],
     "gap": "optional, a requirement facet with no implementing hunk"}
  ],
  "risks": ["Where behavior shifts, what could go wrong, and for whom."],
  "hotspots": [
    {"title": "loader.rs, the sort and the skip are one loop",
     "lede": "why this hunk is subtle, one or two sentences",
     "hunk": "hunk-src-memory-loader-rs",
     "annotations": [
       {"match": "sort_by_key(|e| (Reverse(e.tier)", "note": "the margin note for exactly this line"}
     ]}
  ],
  "unverified": ["Beliefs with no hunk to anchor to."]
}
```

Field-by-field intent (all optional except that an empty file is not a review):

- `test_status`: from Step 1. If unobtainable, write
  `{"unobtainable": "why"}`; the script renders it in UNVERIFIED, never
  dressed up as green.
- `overview`: plain-language account of what the diff does, mapped to the
  spec's intent. `scope_creep` items get a "not in spec" flag: unrequested
  renames, drive-by refactors. That gap is the single most useful thing a
  reviewer can be handed.
- **Language idiom and maintainability** (folded into `overview`, not a new
  key): one or two sentences total, either one per major hunk group or one
  for the diff as a whole, on whether the code reads as idiomatic for its
  language (rustacean Rust, pythonic Python, and so on) and any
  maintainability signal worth flagging (naming, duplication, complexity).
  Keep it short: a read, not a hunk-by-hunk audit. Descriptive only, like the
  rest of the page: say what a fluent reader of that language would notice,
  never a go/no-go verdict. An observation specific and confident enough
  that the reviewer needs the exact lines in front of them belongs in
  `hotspots`, anchored on that hunk's id, not as a stray sentence here;
  anything you are not sure of goes in `unverified` instead. Judging idiom
  violations stays cross-check's Standards axis; this page only describes.
- `intent_map`: each spec requirement paired with the hunks that implement it.
  `id` must be a requirement section id from the contract, verbatim; the
  script links it to `review.html#<id>` and `review.html` links back. A
  requirement with no implementing change is a `gap` worth showing, not
  hiding.
- `hotspots`: the few hunks that deserve real human eyes; this is where you
  spend a reviewer's scarce attention deliberately. Each `annotations[].match`
  is a substring that must match **exactly one line** in that hunk; the script
  highlights the line and sets the note beside it in the margin. Annotate only
  the lines that need it, not every line. A mismatched `match` is reported and
  rendered as an unplaced note, so check the script's output and fix rather
  than publish a dangling claim.
- `unverified`: anything you believe but cannot tie to a hunk. Quarantined,
  never mixed in with anchored claims as if it were confirmed. An honest gap
  helps a reviewer; a confident-looking guess misleads one.

## Step 4. Dispatch the write, render, and open

This skill's HTML is always written by a dispatched subagent; writing it by
hand in this session is a violation, not a shortcut. A 2026-07-21 run did
exactly that and produced 660KB in one turn; a 2026-07-27 wrap-up session
repeated it and produced 702k tokens, most of it hand-written page content.
Writing the file, however large, is carpentry, not judgment, and carpentry
has no business in the session doing the judging.

Package Step 3's decided content, verbatim, into a self-contained dispatch
brief: the full JSON shape, every field's content, the hunk ids and
requirement ids from Step 2's authoring contract, and the two commands below.
Dispatch it to a subagent, `subagent_type: too-te` (the executor role for fully-specified work, defined in `agents/`); if the harness has no
`too-te` role, fall back to `general-purpose` and say so explicitly in the
prompt, naming a cheap, fast model rather than leaving the choice open. The
worker does no analysis, invents no finding, and makes no judgment call: it
writes `<artifact_dir>/diff-review.json` exactly per the brief, runs the
commands, and fixes only what the script's report names (unknown ids,
unplaced annotations) by correcting the JSON to match the brief it was given,
iterating until the report is clean.

```
uv run <skill-base>/scripts/generate.py <artifact_dir> --base <base> --branch <branch>
uv run <skill-base>/../spec-viewer/scripts/generate.py <artifact_dir>
```

(Skip the second command in the no-change fallback: there is no spec page to
regenerate.)

The first command renders the full page and reports problems (unknown ids,
unplaced annotations): that is what the worker fixes and re-runs against. The
second regenerates `review.html`, which only emits its per-requirement
`diff ↗` links once `diff-review.html` exists on disk; that run closes the
loop from the spec page back into yours.

When the subagent reports back, read the rendered page yourself and accept or
reject it: spot-check that hotspot hunk anchors line up with the actual diff
hunks and that the unverified section matches what the brief specified. Do
not fix a problem by rewriting the HTML yourself; reject and redispatch with
the correction folded into the brief. Once you accept it, tell the user the
output path and open it (`open` on macOS, `xdg-open` on Linux, `start` on
Windows).

## Step 5. Stay for follow-ups

When the user asks a follow-up and the answer materially changes the review (a
risk turns out to be a non-issue, a hotspot needs a sharper walkthrough),
decide the change in this session, then dispatch Step 4 again with the
updated brief. The page always re-renders as one coherent review, never a
transcript with a Q&A log appended. Small clarifications that do not change
the review can just be answered in chat.

## Scope

The page format is frozen in the script: no bespoke layouts, no per-change
CSS, no inline SVG diagrams, no live-reload, no theme switcher, no PR-body
generation. If the format itself needs to evolve, change `scripts/generate.py`
once; never hand-patch an emitted HTML file.
