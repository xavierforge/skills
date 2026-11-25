---
name: preflight
description: Pre-PR acceptance gate for a finished change, run after /factory and before /land. Reconciles every finding against the change's Non-Goals and decision ledger, runs the mechanical, runtime, and static review layers, and triages each finding into fix, reversal request, or tracked.
disable-model-invocation: true
---

# /preflight: acceptance before landing

This skill runs in the gap between "the sections are all executed" and "open
the PR". `/factory` finishes when every `tasks.md` section is committed and
`/opsx:verify` is green; `/land` starts from a branch it assumes was already
verified and already review-fixed. Nobody owned the space between them, and
three failures kept escaping through it:

- **A settled Non-Goal gets re-opened by a reviewer.** The change's design
  ruled something out on purpose; a later review flags its absence as a
  finding, and the finding gets implemented because nobody read the ruling
  back.
- **Rulings made during implementation evaporate.** A caveat discovered in
  section 9, a scope call made under time pressure: recorded nowhere, so the
  next session rediscovers or contradicts it.
- **Findings ship unfixed and unregistered.** A review writes a real finding
  into a report, the report is read once, and the branch ships with the
  finding neither fixed nor tracked anywhere.

Every step below exists to close one of those. The gate's output is not a
verdict but a triaged list where each finding has exactly one recorded exit.

## preflight is a discussion gate

Human intervention is expected behavior here, not a failure of the run. Two
of the three triage exits (a reversal request, a decision to track work
elsewhere) are the user's call by construction, and a run that ends by putting
those in front of them has succeeded, not stalled. Do not optimize this skill
toward "completed without asking anything". An autonomous run that quietly
resolved a reversal request in its own favor is precisely the failure the gate
was built to stop.

## Step 0. Reconciliation baseline: read what is already settled

Before running any review layer, load the record of what has already been
decided, so every later finding can be judged against it instead of on its own
merits alone. Resolve the change directory the way the neighbor skills do (the
one active directory under `openspec/changes/`, excluding `archive/`; ask when
there are several), then read:

1. **`design.md`'s Non-Goals** (and `proposal.md`'s, when the non-goals list
   lives there): the pre-start record of what this change deliberately does
   not do. Authoritative, and never edited by this run.
2. **`decisions.md`**: the change's decision ledger, the post-start rulings
   (`[caveat]`, `[reversal→denied]` / `[reversal→accepted]`, `[included]`,
   `[tracked]`), each with its date and source. If the file does not exist,
   say so plainly and create it at the first ruling Step 5 produces; do not
   reconstruct a ledger for rulings that were never recorded.
3. **`docs/adr/`**, if the repo has one: decisions that outgrew a single
   change and were promoted to the repo level. These bind across changes, so a
   finding that contradicts an ADR is a reversal request against the repo, not
   against this branch.

Output of this step: a short written list of what is out of bounds by prior
decision, carried into Step 5. Reading these after the reviews have already
been triaged defeats the purpose, so do it first.

**Without OpenSpec**: when the repo has no `openspec/changes/`, ask the user
where the spec and its non-goals live rather than guessing, and fall back to
`.review/<slug>/` at the repo root as the artifact directory (the landing rule
the neighbor skills share, where `<slug>` is the branch name with `/` replaced
by `-`); `decisions.md` lands there. Every step below still applies. If there
is no statement anywhere of what this work deliberately does not do, say so
plainly in the run summary: exit 2 of the triage cannot fire against a record
that does not exist, and the user should know that before they read the
findings.

## Step 1. Mechanical layer

Run the project's full test suite to green, no substitutions and no subset.

Then confirm `/opsx:verify` already ran at the close of `/factory` and passed.
That is normally the case, and re-running it here would just spend a review
pass to reprint a known result. Re-run it only when one of two things is true:
it never ran (the factory stopped early, the change was executed by hand), or
the spec artifacts changed after it ran. Check the second mechanically: if any
file under the change directory is newer than the verify pass, the pass was
against an older spec and does not count.

Record which case applied (`verify: green at factory close`, or
`verify: re-run here because <reason>`); a gate whose evidence is "it probably
ran" is the reason Step 0's ledger exists.

## Step 2. Runtime verification

**This step is not optional, and it is the one most likely to be skipped.**
The static layers below are cheap to add and have accumulated over time; live
behavior verification is the layer that keeps getting waved through because
the tests were green. Green tests are evidence about the tests. This step is
evidence about the program.

Run the project's own `verify` skill if it has one: build the real binary and
drive it at its real surface, using a mock provider, a mock backend, or a stub
executable so the run costs no API spend. A repo with such a skill already
encodes how to do this without a key; use it rather than inventing a path.

If the repo has no verify skill, exercise the change's main path once by hand
against a real build, and record what you ran and what came back. Either way
the deliverable is the same: the actual command and the actual observed
output, in the run's summary. "Should work" is not an observation.

## Step 3. Static review, two layers, fresh sessions

Two review layers run here, both from clean context. Open them as two fresh
sessions and run them in parallel; nothing in either depends on the other.

- **`/code-review`** (the Claude Code built-in): the defect axis, hunting for
  bugs in the diff. When this harness has no such built-in, dispatch a fresh
  general subagent in a clean context to run the defect-axis review instead.
- **`/cross-check`**: the two-axis review, Standards (does the diff meet this
  repo's documented standards plus the smell baseline) and Spec (does it
  faithfully implement what was asked). It persists `review-verdict.json` at
  the change directory, which is exactly what `/land`'s reconciliation step
  reads back. Skipping it does not go unnoticed downstream: on an openspec
  project, `/land` stops on the missing `review-verdict.json` and asks the
  user whether to proceed unreviewed.

**Fresh context is the whole point.** An in-loop review, run inside the
session that wrote the code or partway through `/factory`, inherits the
implementation's blind spots and reads the diff the way its author already
thinks about it. Reviews performed mid-factory do not satisfy this step; a
review that already happened counts only if it ran in a session that did not
write the code.

Matt Pocock's original `code-review` skill is deliberately not in this chain.
`/cross-check` is this repo's own two-axis review and holds that slot, so
running both would be the same review twice, one copy of it unmaintained.

**Harness fact**: `/vibe-diff` is a user-invoked skill
(`disable-model-invocation: true`). The model running this preflight cannot
see its description and cannot call it by name through the Skill tool;
invisible does not mean not installed. Decide whether a user-invoked skill
exists by checking disk (for example `ls ~/.claude/skills/vibe-diff`), never
by whether the model can see it. When it needs to run, the correct move is
to hand off, not to declare it absent: Step 4 gives the user the line to run
in a fresh session, since it carries its own fresh-eyes precondition that a
session which already touched this diff cannot satisfy. `/cross-check`
carries no such flag: call it directly by name through the Skill tool
whenever this step needs the two-axis layer.

## Step 4. Sign-off page: hand it to the user

`/vibe-diff` renders the branch's diff against its merge-base into the
one-page review surface, read against the change it implements. This is the
artifact the user actually signs off on: the reviews above produce findings,
this produces the readable account of what changed and why it matters. It
explains, it does not judge, so it neither blocks nor approves; it is what
makes the human's approval an informed one.

**This session does not run it.** `/vibe-diff` is user-invoked by design (Step
3's harness fact), and its own fresh-eyes gate rules out any session that has
already read this diff, which is exactly what this one has been doing. So hand
it over rather than reaching for it: give the user the line to paste into a
fresh session, verbatim and on its own,

```text
/vibe-diff
```

and treat the layer as open until `diff-review.json` exists in the artifact
directory Step 0 resolved. It usually will not by the time this run ends, and
that is the expected shape of the hand-off, not a failure: the layer's line in
Step 6's closing status reads `diff-review.json: pending` until the file is on
disk, which is also the file `/land` reconciles against later.

## Step 5. Finding triage: three exits, every ruling written back

Collect every finding from Steps 1 to 4 into one list. Each finding takes
exactly one of three exits, and each exit writes a line to `decisions.md` (the
format is the change's decision ledger contract: one line, dated, tagged, with
its source):

1. **In-spec defect** (the finding names something this change was supposed to
   get right and did not): dispatch a fix. Package it as a self-contained spec
   (the finding, the exact file and hunk, the done-criteria, an explicit "do
   not commit") and grade it the way a `tasks.md` section is graded (roles are
   defined in `agents/`; on Claude Code these are the Agent tool's
   `subagent_type`s): `too-te` when the fix is already fully decided, `sai-hu`
   when the finding names a problem without settling how to fix it. Ledger line when the fix
   lands and it changed scope in any way worth remembering: `[included]`; a
   plain "we fixed the bug we were supposed to fix" needs no ledger line, the
   commit is the record. The subagent never commits, which is exactly what the
   "do not commit" in its spec buys: this session does, once it has accepted
   the returned diff, with `git commit --fixup <the commit the fix corrects>`.
   That keeps the correction attached to what it corrects, and leaves the
   squash to `/land`'s Step 5, which already expects to find fixups on the
   branch and fold them in.
2. **Collides with a Non-Goal or an already-recorded decision**: this is a
   **reversal request**, and it goes to the user. Do not implement it, do not
   quietly widen the change to accommodate it, and do not argue it away
   yourself either. Present it as: what the finding asks for, which prior
   decision it contradicts, and where that decision is recorded. The user
   rules. Ledger line, written when you hand the request over and not after
   the answer comes back: `[reversal→pending]`, naming the finding as its
   source and the decision it contradicts. When the user rules, update that
   same line in place to `[reversal→denied]` or `[reversal→accepted]`, so one
   ruling stays one line. A preflight run normally ends before the ruling
   arrives, which makes `[reversal→pending]` the state this gate leaves
   behind; a run that waits for the answer before writing anything leaves no
   record at all. This is the exit that closes the first of the three holes,
   so treat "the reviewer was probably right" as the trap it is: the reviewer
   did not see the decision.
3. **Out of spec** (real, but not this change's job): register it where the
   project tracks future work (its roadmap file, an issue) and keep it out of
   this PR. Open an issue only after the user confirms; never open one
   autonomously. Ledger line: `[tracked]`, naming where it was registered.
   When the destination needs the user's confirmation and the run ends before
   it arrives, write the line anyway, naming the destination you proposed and
   marking it as awaiting their confirmation; fill the destination in when
   they answer. The tag itself does not change.

One case sits beside the three exits rather than inside them: a finding that
is real, is not a defect, asks for no future work, and contradicts nothing,
because it names a limitation this change knowingly accepts (a claim only a
live human gate can prove, an intended behavior a reader would not expect, a
cosmetic edge nobody will act on). Its ruling is "accepted, and here is how we
live with it", and its exit is the record itself: a `[caveat]` line in the
ledger, plus a line in the PR body's notes. Do not manufacture a fix or an
issue for it just to give it one of the three exits; an invented work item is
worse than a stated limitation.

**A layer that could not run is a ruling too.** Steps 1 to 4 each assume a
layer exists: a test suite, a verify skill, `/code-review`, `/cross-check`,
`/vibe-diff`. Before writing any of them off as absent or unavailable,
confirm it on disk (the same check as Step 3): a user-invoked skill like
`/vibe-diff`, one the model cannot see or call, is not the same thing as a
skill that is not installed. When the check finds it present, the exit is
Step 4's hand-off, `pending` in Step 6's status, not a caveat; do not write
`[caveat]` for a layer that exists but was never asked to run. When one is
genuinely absent from this repo or unavailable in this harness, reporting it
in the run summary is not enough. Write one `[caveat]` line per such layer
into `decisions.md`, naming the layer and why it did not run:

```text
- 07-25 [caveat] runtime verification not run: this repo has no test suite and no verify skill (source: preflight step 2)
```

Such a layer is also the one that reads `not run (caveat: <reason>)` in Step
6's closing status, so the ruling lands in both places in the same words. The
summary evaporates with the session; the ledger is what someone opening
this change directory three months from now reads. "This change shipped
without runtime verification, and here is why" is exactly the kind of ruling
`decisions.md` exists to hold.

A finding with no exit is not triaged. The step is done when every finding has
one, and when `decisions.md` carries a line for every ruling that was not
simply "fixed as specified".

## Step 6. Hand off to /land

**What this gate does not do is land the branch.** The fixes accepted in Step
5 are committed here, as fixups against what they correct, and that is where it
stops: preflight never pushes, never opens a PR, and never reorganizes the
branch's history. Leaving a fix uncommitted is not the safer choice it looks
like, because `/land`'s scan and adversarial review both read
`<base>...HEAD`: work still sitting in the tree is invisible to both and never
reaches the PR.

State the handoff explicitly and stop: the branch is ready for `/land`, which
reconciles against `review-verdict.json` (plus the vibe-diff and verify
artifacts) and runs its own adversarial review last. That review stays in
place as deliberate redundancy: it reads the finished diff cold, with a
maintainer's persona, after everything here has already been triaged. Do not
skip it on the grounds that preflight already reviewed the branch, and do not
duplicate it here.

Report, in the run summary: the verify case from Step 1, the runtime evidence
from Step 2, one line per review layer with its finding count, and the triage
table (finding, exit, ledger line). That summary is what the user reads before
approving the hand-off to `/land`.

Close it with the artifact status, three fixed lines in this order, one per
thing `/land`'s reconciliation goes looking for. Every line carries one of
three labels, and the parenthetical is part of the label, not decoration:

- `done (<evidence>)`: the artifact is on disk, named by the layer that wrote
  it and what it found.
- `pending (<who runs it and how>)`: the layer exists and has not run yet.
  This is what Step 4's hand-off leaves behind for `/vibe-diff`.
- `not run (caveat: <reason>)`: the layer is genuinely absent from this repo
  or unavailable in this harness. It is the same ruling as the `[caveat]`
  line Step 5 already writes into `decisions.md` for that layer, in the same
  words: one vocabulary, said once to the user reading now and once to
  whoever opens the change directory later.

```text
verify: done (green at factory close)
review-verdict.json: not run (caveat: cross-check unavailable in this harness)
diff-review.json: pending (user runs /vibe-diff in a fresh session)
```

**A layer whose invocation failed is not `done`, and neither is one you stood
in for.** An error back from the Skill tool (`Unknown skill: cross-check`)
means the layer did not run, and reviewing the diff inline instead does not
make it run: fresh context is the layer's whole definition (Step 3), and this
session has none left to offer. An errored or substituted layer takes
`not run (caveat: <reason>)` and its ledger line, never `done` with the
substitute named in the parenthetical.

Three lines every run, present or not. A `pending` or `not run` line is not
this gate failing; it is the user's remaining list, and the alternative is
that they discover the gap at the `/land` gate instead of here.

## Promoting a decision to an ADR

Some rulings in `decisions.md` outlive their change. Promote one to a
repo-level ADR (`docs/adr/NNNN-slug.md`, plain serial number, one paragraph is
already a valid ADR) when all three hold:

1. **Hard to reverse**: undoing it later means touching many call sites, a
   data format, or a published interface.
2. **Surprising without the context**: a competent reader meeting the code
   cold would ask "why on earth is it done this way".
3. **The outcome of a real trade-off**: something was genuinely given up. A
   decision with no cost is a convention, not an ADR.

Two guards on where this applies. **Only in repos the user owns.** In someone
else's project, a decision goes through that project's own channels (the PR
description, a code comment, an issue) or the user records it back in their own
repo; do not commit a personal discipline file into another maintainer's
version control. And ADRs are promotions, not duplicates: the ledger line stays
where it is, the ADR states the decision at repo scope, and the ledger line
points at it.

## Writing long output

Any long HTML page or long report produced during this run is written by a
dispatched `too-te` subagent, never typed by the main session. The main session
holds the judgment (which findings are real, which prior decision a finding
collides with, what the summary must say), so it writes the content spec: the
exact structure, the facts to include, the file to write. The subagent writes
the file, and the main session reads the result back and accepts or rejects it.
The main session's context is the expensive one in this run; spending it
emitting markup is the single most avoidable cost here.

## Red flags: STOP, you are running preflight wrong

- "The reviewer flagged it as CONFIRMED, so I fixed it." Check the Non-Goals
  and the ledger first. A confirmed finding against a settled decision is a
  reversal request, not a work item.
- "The tests are green, so runtime verification is redundant." Step 2 exists
  because that sentence keeps getting said. Green tests are evidence about the
  tests.
- "I reviewed this thoroughly while implementing it, so Step 3 is done." A
  review in the implementing session is the one kind that does not count.
- "Only one finding is left, I will just note it in the PR body." Every
  finding takes one of the three exits and the ruling lands in `decisions.md`;
  the PR body is not the ledger.
- "I will write up all the rulings at the end." The ledger is written when a
  ruling happens. A ledger reconstructed at close of change is a summary of
  what someone remembered, which is the failure it exists to prevent.
- "/land runs its own review, so I can skip cross-check." That review is the
  last redundancy, not the supply. Without `review-verdict.json`, `/land`'s
  reconciliation finds nothing to read and stops to ask the user whether to
  proceed unreviewed.
- "I said in my reply that there was no test suite, so it is recorded." The
  reply dies with the session. An absent or unrunnable layer takes a
  `[caveat]` line in `decisions.md` like any other ruling.
- "The fix is in, so I will push it and open the PR." Committing the accepted
  fix is this gate's last act; pushing and opening the PR are `/land`'s. A gate
  that pushes is no longer a gate.
- "The user has not ruled yet, so there is nothing to write down." The handover
  is itself the event the ledger records: write `[reversal→pending]` when you
  put the request to them, and update that line when the answer comes.
