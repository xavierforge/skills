---
name: section
description: Executes one already-planned section of the active openspec change's tasks.md. Triggers on the user typing /section N, or a /factory dispatch loop's subagent invocation naming a section number. Not for open-ended feature-building, bug-fixing, or generic TDD requests that do not name a specific tasks.md section number.
---

# /section N: execute one planned section of the active change

This runs during the Execute phase, once a change has been proposed and its
`tasks.md` broken into numbered sections. It replaces the Execute-phase template
that used to be hand-pasted into each fresh session, so the behavior below is
fixed rather than retyped (and re-mistyped) every time. Its unit of work is one
section: one section in, one commit out, then stop.

`N` is the section number, taken from the invocation (`/section 3`). If the
invocation omits `N`, ask which section rather than picking one; running the
wrong section is the failure this whole skill exists to avoid.

## Precondition: you must set this up; the skill cannot

Before invoking, you must already be in a **fresh session sized for execution
work**, not a planning-tier one. This skill cannot switch models or open a
session; it only runs the work once you are on the right one. If you are not
sure, stop and fix that first rather than burning a planning-tier session on
mechanical section work.

Where Step 3 dispatches a delegate role, that role's own agent frontmatter
decides its model: this skill never passes a `model` or an `effort` parameter,
and never names a model.

## Step 1. Locate the active change

List `openspec/changes/`, excluding `archive/`. Exactly one active change
directory: that is the one, proceed. Zero, or more than one: do not guess. List
what you found and ask the user which change (or that none is active). Guessing
here runs a section against the wrong `tasks.md`.

## Step 2. Read the section and its dispatch annotation

Read that change's `tasks.md`. Find the `## N.` section and extract its dispatch
annotation, of the form `[dispatch: too-te|sai-hu|main, parallel:
yes|no]`. If the section carries no such annotation (older changes predate this
convention), read the `## Dispatch` preamble for the role it names for section
`N`, and resolve an under-specified role rather than stalling on it:

- If the preamble offers `main` as one of the acceptable roles (e.g. "main
  session or sai-hu"), take `main` and do the work inline. Running the section
  on this execution session is always a valid default, so a menu that includes
  `main` is not a question worth stopping for.
- Only ask the user when the role is genuinely undecidable: it is absent or
  unreadable, or the choice is between delegate roles alone (too-te vs
  sai-hu, with no `main` option) where picking wrong means dispatching to the
  wrong agent.

## Step 3. Dispatch decision

The annotation names the section's **starting tier**, and it is honored on the
first attempt: a section marked `sai-hu` goes to `sai-hu` straight away, never
to `too-te` first. Under-tiering a judgment-heavy section does not save a tier,
it spends two failed attempts rediscovering what the plan author already
recorded.

- `too-te` or `sai-hu`: **dispatch the leaf-role agent the annotation names**
  (roles are defined in `agents/`; on Claude Code this is the Agent tool's
  `subagent_type`) with the section handed over as a complete, self-contained spec (goal,
  exact task list, done-criteria, the execution and close-out rules below).
  Pass no `model` and no `effort` parameter. Do not do the
  work inline. On this path the leaf agent owns Steps 4 and 5, including the full
  gate, the single commit, and ticking the checkboxes; this session only relays
  its report and does **not** re-run the gate or make a second commit. The
  `parallel` flag is the plan author's signal about whether this section may
  overlap others; it does not change that one `/section` run is one section.
- `main`: do the work in **this** session, inline, following the rules below.

**If the named role type is not installed** (a bare environment with no
`agents/` roster: a safe-mode sandbox, a fresh install, an unconfigured Codex),
the dispatch fails with the role not found; do not stop. Re-dispatch the same
section to a fresh general subagent, brief unchanged, prepending the intended
role's one-line contract (for `too-te`: run the section exactly as specced,
expand no scope, wind down at a breakpoint if you run long; for `sai-hu`: own
the local design decisions the section's goal and constraints leave open), and
note the role in your report in fallback form, `sai-hu (fallback: general)`.
Installing the roster is what turns that fallback into real model tiering and a
per-role tool boundary.

**When a dispatched agent fails for a judgment reason** (it could not decide,
as opposed to lacking context you could have supplied), the starting tier
decides what happens next:

- **Started on `too-te`**: retry it, telling the next attempt what the last one
  got wrong. If a second attempt fails the same way, escalate the section to
  `sai-hu` and say so in your report.
- **Started on `sai-hu`**: there is no tier above it, so there is nothing to
  escalate to. After two failed attempts, **stop and report to the user**: the
  section, both failure reasons, and the fact that its starting tier was
  already the top one. Do not retry it further, and do not quietly finish the
  section inline in this session.

## Step 4. Execution rules (while working the section's tasks)

- **TDD per task**: write the failing test first, then the implementation that
  turns it green. Never implementation-first. Green means the simplest
  implementation that passes, nothing extra.
- **A failing test during the Red phase is the EXPECTED SUCCESS signal.** If you
  did not watch the test fail, you do not know it tests the right thing. The
  only check Red needs is that it fails for the expected reason (the assertion,
  not a typo, import error, or build break); once confirmed, do not debug it and
  do not treat it as a problem: proceed straight to the implementation that
  makes it pass.
- Run **only the tests relevant to this section** while working. No full quality
  gate mid-section, no per-task commits, no per-task check-ins with the user.
  Work the whole section through, then gate and commit once at the end.

### Red flags: STOP, you are misreading the plan

- "The test is failing, let me debug it" during Red. No: if it fails on the
  expected assertion, that failure is success.
- "Let me commit this task before the next one." No: one commit per section.
- "Let me run the full gate / check in with the user after this task." No: only
  at the section boundary.
- "It says `sai-hu`, but the tasks look mechanical, `too-te` can take a first
  pass." No: the annotation is the starting tier, and Step 3 dispatches it as
  written.

## Step 5. Close the section (gate, commit, stop)

Once every task in section `N` is done:

1. **Run the full gate**: the project's own gate command, whatever it is (its
   agent instructions file (`AGENTS.md`, `CLAUDE.md`) names it if present;
   otherwise its own build surface: a `justfile`, `Makefile`, `package.json`
   script, or CI config). `just check` is only the common example, not an
   assumption; do not invent a gate the project does not use.
2. If it fails on **something this section touched**, that is your bug: fix it to
   green before committing.
3. If it fails **only on pre-existing issues unrelated to this section**, do not
   chase them. But "pre-existing" is a claim you must evidence, not assume,
   because you are on the cheap model with no memory of what was red before: a
   failure counts as pre-existing only if it does not touch this section's diff
   AND you have confirmed it reproduces on the section's base (it was already red
   with your changes stashed, or on the merge-base in a throwaway worktree). Only
   then record each in your reply, **commit anyway**, and note they should get
   their own scoped branch later.
4. Make **exactly one commit** for the whole section, in Conventional Commits
   format (`type(scope): imperative subject`). **Tick this section's checkboxes
   in `tasks.md` as part of that same commit.** Never touch another section's
   tasks or checkboxes.
5. **Refresh the review page**: if `<change>/review.html` exists, run
   `python3 ~/.claude/skills/spec-viewer/scripts/generate.py <change>` (add
   `--quiz <change>/review-quiz.json` when that file also exists). Zero-token,
   no dispatch; a failure here does not block the section, just note it.
6. **Stop.** Do not roll into section `N+1`. One `/section` invocation is one
   section; the user starts the next one in its own fresh session.
