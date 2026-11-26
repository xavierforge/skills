---
name: factory
description: Drive the active openspec change end to end, gating the plan, running every section through its own fresh subagent, verifying, and reporting each round. Replaces handing the built-in /goal its loop contract by hand. Requires an OpenSpec project.
disable-model-invocation: true
---

# /factory: run the whole active change, one section per round

This is the Execute phase driven end to end. `/section N` executes one planned
section and stops; `/factory` is the foreman that runs the sections to
completion: it gates the plan, spawns one fresh subagent per section, times
and reports each round, and verifies the change at the end. The foreman
schedules, checks, and reports; the per-round subagents do the work.

**Relationship to the built-in `/goal`:** Claude Code ships a built-in `/goal`
that loops an agent on a free-form goal until done; its behavior is whatever
contract you paste into it, retyped (and re-mistyped) every time. This skill
is that loop with the contract built in: invoking `/factory` replaces handing
`/goal` the full text by hand. The skill is deliberately **not named `goal`**:
a skill named `goal` would shadow the built-in command, the same collision
lesson `code-review` already taught.

## Unattended mode and the reversibility test

**The reversibility test.** A stop-and-ask is warranted only when the next
action is irreversible or outward-facing (push, PR, merge, deleting user work,
any force operation), or the plan is undecidable in a way that changes scope.
Anything else is a reversible fork: decide it, do it, and record it.

**Unattended mode** needs an explicit signal, never silence: the request
waives the questions in words ("unattended", "don't ask, I'm away", "run until
done without me"), or the harness states that the run is non-interactive or
has no way to ask a person. Describing the job ("run the change to
completion") is not that signal. Without one, every question below is asked
as written, the plan gate's wait included.

Unattended, a question that passes the test (a dirty tree, a scope-changing
plan gap, a stuck section) ends the run, written up; one that fails it is
decided and recorded as an `[assumed]` line in `decisions.md` (form:
`/section` Step 4): of several active changes, run the one the branch name or
the only unfinished `tasks.md` marks; a parallel group takes `continue`; a
plan rewrite follows Step 1. The run ends with a **decided without you** list
(the `[assumed]` lines it added), so the user reviews every choice at once.

## Step 0. Precondition: exactly one active change

Two repo guards come before anything else, because the loop will commit
autonomously once it starts: the working tree must be clean (a dirty tree
means round commits would sweep in unrelated work; stop and ask the user to
commit or stash, never auto-stash), and HEAD must sit on a non-default
feature branch (on the default branch, stop and hand branch-opening to
`/begin` Phase B; the factory never lands its commits on the default
branch).

This skill serves OpenSpec projects only; the loop's unit of work is a
`tasks.md` section, and only OpenSpec provides one. List `openspec/changes/`,
excluding `archive/`:

- **Exactly one** active change: proceed, and announce which change the
  factory is running.
- **More than one**: list them and ask the user which change to run. Guessing
  runs the whole loop against the wrong plan.
- **Zero** (or no `openspec/` directory at all): refuse to run, and say why in
  one breath: this skill only serves OpenSpec projects, there is no active
  change under `openspec/changes/`, and the way in is to propose a change
  first (or work in ordinary sessions without the factory).

Done when: one change directory is named as the target, or the run has ended
at a refusal or a question.

## Step 1. Plan gate: tasks.md must be loop-ready

Read the change's `tasks.md` and judge every section against three
loop-readiness properties. The loop hands each section to a fresh subagent
with no memory, so the plan must carry everything:

1. **Session-sized**: one section completes comfortably in one fresh session.
   A section that reads like a mini-project (double-digit tasks, several
   subsystems at once) gets split.
2. **Independent**: a section depends only on earlier sections being fully
   committed, never on a sibling's half-done state. Two sections editing the
   same code against each other get merged or reordered.
3. **Verifiable**: every task line names its check (the test to write first,
   the command to run, the observable outcome). "Implement X" with no check
   gets its check written in.

If every section passes, say so and enter the loop. Otherwise rewrite
`tasks.md` in place (split, merge, reorder, add checks) and commit it on its
own (`docs(openspec): make <change> tasks loop-ready`) so round commits stay
one-section-one-commit. Interactive: first show the user the diff (`git diff`
of `tasks.md`) and wait for their approval; the loop runs only over a plan the
user has seen. Unattended: a rewrite is a reviewable commit the user can
revert, so waiting buys nothing; add an `[assumed]` line naming that commit's
subject and what changed, commit both together, and enter the loop. A plan
that cannot be made loop-ready without a scope decision is not a reversible
fork: stop, write up what is undecided, and end the run.

Done when: every section passes all three properties, and any rewrite has
been committed (approved first, when interactive).

## Step 2. Rounds: one section in, one commit out

Count the incomplete sections; the round budget is **that count + 3** (the +3
absorbs retries). Then loop, strictly one round at a time:

1. **Pick**: re-read `tasks.md` and take the lowest-numbered section with any
   unchecked box. If none remain, leave the loop for the verify step. If that
   section opens a group of two or more adjacent `[parallel: yes]` sections, do
   not spawn a round: hand the group back as lanes (see *Parallel groups* below)
   and wait for the user.
2. **Spawn**: record the start time (`date +%s`) and the start commit
   (`git rev-parse HEAD`), then dispatch one fresh
   subagent for that section in the role the section's `[dispatch: ...]`
   annotation selects (see below; roles are defined in `agents/`, and on
   Claude Code this maps to the Agent tool's `subagent_type`), passing no
   `model` and no `effort` parameter. Hand it a complete brief: the change
   name, the section number, the section contract to read and follow
   (`<skill-base>/../section/SKILL.md`), the role and marker for its round
   record, any foreman ruling it must write to `decisions.md` (an escalation,
   an unattended pick), and the two factory overrides:
   - **Inline only**: execute every task inside this subagent, treating any
     dispatch annotation as `main`. It is a leaf agent; the factory already
     read the annotation to pick this subagent's role, and already provided
     the fresh delegated session the annotation asked for.
   - **Report back**: return the commit subject, the gate result, any
     failures recorded as pre-existing, and the `Assumptions` heading.
   (`/section`'s fresh-session precondition is satisfied by construction: the
   subagent is exactly that.)

   Two absence cases stop the factory rather than degrade it: a harness with
   no subagent tool cannot run the loop's delegation layer (say so and point
   the user at running `/section N` by hand in fresh sessions), and a missing
   section contract file means this skill is installed without its sibling
   (report it, do not improvise a section contract inline). A third absence,
   the dispatch role type itself not being installed, does not stop the loop:
   it degrades to a general subagent (see *Rosterless fallback* below).
3. **Check the work, not the narration**: you recorded the round's start
   commit (`git rev-parse HEAD`) before spawning; after the subagent returns,
   confirm from the repo that section N's boxes are ticked, exactly one new
   commit landed, and the tree is clean. A round that fails any of these is a
   failed round: reset to the recorded start commit (`git reset --hard
   <start>`, which discards the round's partial commits and debris, and is
   safe because Step 0 guaranteed a clean tree and every earlier round ended
   at a clean commit), tell the next attempt what the last one got wrong, and
   let step 1 pick the section up again. A landed commit missing its round
   record, or a `decisions.md` line for an item under `Assumptions`, is not a
   failed round: stage the line and fold it in with `git commit --amend
   --no-edit` (bookkeeping on a local commit, not the section's work).
4. **Refresh the review page**: if `<change>/review.html` exists, run
   `uv run <skill-base>/../spec-viewer/scripts/generate.py <change>` (add
   `--quiz <change>/review-quiz.json` when that file also exists).
   `<skill-base>` is this skill's base directory, the path announced when the
   skill is invoked; `spec-viewer` installs as its sibling, so build the
   command from that announced path, never from an assumed install location.
   Zero-token, no dispatch; a failure here does not block the round, just note it.
5. **Report the round** (Step 3's one-liner), then return to step 1.

If the budget runs out with sections still incomplete, stop the factory and
report which section is stuck and how its rounds failed; the user decides
what happens to a section the loop could not land.

**After the last section**: run `/opsx:verify` on the change. Fix every
CRITICAL finding (each fix is its own conventional commit) and re-run, up to
three verify-fix cycles; a CRITICAL that survives the third cycle gets the
stuck-section treatment, stop and report it rather than looping. If
`/opsx:verify` does not exist in this environment, the result is
`unavailable`: say so plainly; an unavailable gate is reported, never
simulated. Either way, write the result as Step 3's verify record.

Done when: every section's boxes are ticked and verify has run (or its
absence is recorded), or the round budget is exhausted and the stuck section
is reported.

### Parallel groups: hand them back as user-dispatched lanes

A section marked `[parallel: yes]` invites its group to run at the same time,
but the factory never fans out concurrent dispatch on its own; opening lanes is
the user's call. So when the Pick step lands on a group of **two or more
adjacent** `[parallel: yes]` sections that are still unchecked, the foreman does
not spawn a round. It stops and hands the group back as a **lane plan** for the
user to run as dispatcher. (A solitary `[parallel: yes]` section with no
parallel neighbor has nothing to parallelize; run it as an ordinary round.)

The group is safe to split because the `[parallel: yes]` contract requires its
members to be mutually independent, needing none of each other's output at all
(the openspec-rules tasks contract states this above ordinary section
independence, precisely so lanes branching off a shared base stay correct: a
lane never sees another lane's uncommitted work). Do not take the annotation
purely on faith: before emitting the plan, read the group's section bodies as a
check on that contract, and if the sections reference one another (one section's
tasks name another's output, types, or files), treat it as a misannotation, stop
and point it out, and recommend `continue` so the group runs sequentially rather
than opening lanes on a dependency the shared base cannot carry.

Record the base first: the current commit of the feature branch
(`git rev-parse HEAD`), which already carries every earlier section. Every lane
branches off that one base, so each lane starts from the same committed history.

Emit one lane per section in the group. Each lane is a dispatch prompt the user
can paste straight into a fresh session, self-contained the way this repo's
briefs always are, carrying:

- the worktree name and the branch name (`<type>/<kebab-case-description>`),
- the section numbers and titles the lane covers,
- the exact commands to create the worktree off the recorded base and enter it,
- the section run itself (`/section N` for each covered section): run this way
  the section contract lands its own commit, and, outside a factory round,
  `/section` reads each section's `[dispatch: ...]` annotation and delegates on
  it as usual, so the factory's inline-only override does not reach a
  user-dispatched lane,
- the lane's acceptance command (the test the covered sections must pass before
  the lane is done),
- the teardown: leave the branch for the foreman to bring in, remove the
  worktree, and report the branch name with each section's commit subject.

Then state both exits plainly and wait for the user (unattended, take
`continue` and record it; a misannotated group does the same):

- **Open the lanes**: the user runs the prompts in their own sessions and
  reports each lane done. The foreman proceeds only once every lane has
  reported.
- **`continue`**: the user declines the lanes. The foreman drops the parallel
  split and runs the group as ordinary sequential rounds, lowest section first,
  exactly as if the markers were absent.

**Resuming after the lanes finish.** When every lane reports green, the foreman
brings their commits onto the feature branch in ascending section order,
preserving the loop's one-section-one-commit history: the first lane
fast-forwards, each later lane is replayed on top (cherry-pick its section
commit, or rebase the lane branch onto the branch tip), so the feature branch
ends linear with one commit per section. Then it confirms from the repo that
every covered section's boxes are ticked and the tree is clean, the same check
that ends a sequential round. A lane that reports failure is re-handed as a
fresh lane prompt, never brought in half-done. With the group landed, the loop
resumes at the Pick step on the next lowest unchecked section.

**Ledger.** A parallel group is one round line carrying a `parallel` marker: the
section field spans the covered range, the result field lists each lane's commit
subject, and the duration is the wall time from handing out the plan to the last
lane landed. The existing columns keep their meaning, and `parallel` sits where
a sequential round's role note would. Counting the whole group as one round
leaves the section-count budget with extra slack, which is fine; the round still
advances the loop past every one of its sections at once.

### Role for the round's subagent, and escalation

`[dispatch: ...]` selects the round's **starting tier**: which role the
foreman hands the section to on its first attempt. What the factory overrides
is only the *layer* question, not the *tier* question. The outer loop is the
delegation layer, so the round's subagent always executes inline rather than
spawning a sub-subagent (that would pay a second handoff for isolation it
already has, and hide the section's work one level further from the foreman's
check). Which role that subagent is, though, is read straight off the
annotation:

- **No annotation, `[dispatch: too-te]`, or `[dispatch: main]`**: dispatch
  the `too-te` role. (`main` means "no delegate role needed"; inside the
  factory the round's own subagent is that session, so it lands on `too-te`.)
- **`[dispatch: sai-hu]`**: dispatch the `sai-hu` role on the **first**
  round, not as an escalation, and note `per annotation` in the round's report
  line. The plan author already recorded that the section is judgment-heavy;
  starting it a tier low spends two failed rounds rediscovering that, and a
  section that outgrows the mechanical role's limits fails the same way every
  time it is retried there.
- **In every case**, pass no `model` and no `effort` parameter. The role's own
  agent frontmatter and the session decide those; hard-coding a model here is
  exactly the coupling role-based dispatch exists to remove.

**Rosterless fallback: keep the loop running when no roster is installed.** The
tiers above are role types (`too-te`, `sai-hu`) that exist only once the
`agents/` roster is installed; without it the dispatch fails outright, the
harness answering that the role type is not found. That degrades a round, it
does not stop the factory: re-dispatch the same section to a fresh general
subagent with the brief unchanged (still no `model`, no `effort`), prepending
the one-line contract the intended role would have carried:

- for a **`too-te`** round: run the section exactly as specced, take on no scope
  the plan did not hand you, and if the round runs long, wind down at a clean
  breakpoint and report it rather than pushing past the budget;
- for a **`sai-hu`** round: own the local design decisions the section's goal and
  constraints leave open.

Note the tier in the round's report and the ledger in fallback form,
`too-te (fallback: general)` or `sai-hu (fallback: general)`, and keep every
other marker (`per annotation`, `escalated`, `turn budget`) stacked on it as
usual.

**Escalation applies only to sections that started on `too-te`**: when such a
section's round fails twice in a row for a judgment reason (the subagent could
not decide, not that it lacked context you could have supplied), the next
attempt dispatches `sai-hu` for that section instead, and that round's report
line records the escalation and its reason.

**A turn-budget stop is not a judgment failure, and the escalation rule above
does not cover it.** `too-te` runs under a hard cap of about 100 turns, not
tool calls; one turn can batch several tool calls, so the tool-call count
where a round actually stops will vary (measured across ten truncated rounds
on 2026-07-24: nine were cut mid ordinary work, and the one runaway round, 69
calls with zero edits and zero commits, is exactly why the breaker still has
to exist; 100 turns doesn't cut off ordinary work and a runaway still hits a
ceiling). Its signature in the round's return is unmistakable: the subagent's
last message announces the next action and then stops, with no result for it
and no closing report. That is a hard stop mid-step, not a round that went
wrong, and it calls for a different move:

- **Never re-dispatch the same section to `too-te` unchanged.** A retry spends
  the same budget on the same section and stops in the same place. Two failures
  are not required before acting, and the two-judgment-failure rule is not what
  this is.
- Either **narrow the section** (split it in `tasks.md` so each part fits the
  budget, gated and committed as a Step 1 rewrite) or **dispatch `sai-hu`**
  for it, which carries no turn cap.
- Record `turn budget` in the round's report line, so the ledger keeps this
  apart from `escalated after two judgment failures`.

**A section that started on `sai-hu` per its annotation does not escalate**:
there is no tier above it. If it fails two rounds in a row, stop the factory
and report to the user: the section, both failure reasons, and the fact that
its starting tier was already the top one. Do not keep spending the round
budget on it, and do not fall back to running it inline in the foreman
session; what happens to it is the user's call.

**A section that started on `too-te`, hit a turn-budget stop, and moved to
`sai-hu` follows the same rule from there on.** Once it is running on
`sai-hu`, it is on the top tier regardless of how it got there: if it then
fails, treat it exactly like a section that started on `sai-hu` per its
annotation and stop the factory, reporting to the user rather than searching
for a further escalation that does not exist.

Report each round's tier and why it was chosen (`per annotation`, `escalated
after two judgment failures`, or `turn budget`) so the ledger makes the tier
choices auditable after the fact.

## Step 3. Reporting: the foreman's ledger

At the end of every round, output exactly one line:

    round <R>/<budget>: section <N> (<role>[, per annotation | , escalated | , turn budget]) | <commit subject, or FAILED - reason> | <Xm Ys> | next: <section M | verify | stop>

The role note is `per annotation` when the section's `[dispatch: ...]` picked
a non-default starting tier, `escalated` when two judgment failures moved a
`too-te` section up, `turn budget` when a truncated `too-te` round moved the
section to `sai-hu` or to a narrower shape, and omitted for a plain default
`too-te` round. When a round ran on the rosterless fallback, the role field
itself takes the fallback form (`too-te (fallback: general)`), and these
markers stack on top of it unchanged.

When the factory stops (all sections done and verified, or budget exhausted),
output the ledger: one table row per round with section, role, commit subject,
duration, and result; a row for verify with its outcome (clean, CRITICALs
fixed and committed, or unavailable); and a closing `total` row summing the
wall time, so the ledger's last line is always the total. The
ledger is written from the repo (commits, `tasks.md`), so it stays true even
when a round's narration was optimistic. An unattended run then adds its
decided without you list.

**The durable record is `tasks.md` and `decisions.md`, not chat.** Each landed
section carries its round record (`/section` Step 5 writes it into the
section's commit). After verify, append `> verify: <clean | CRITICALs fixed:
<hashes> | unavailable> | <MM-DD>` as the last line of `tasks.md` and fold it
into the run's last commit (`git commit --amend --no-edit`), or commit it on
its own (`docs(openspec): record <change> verify result`) if that commit is
already on a remote. A foreman ruling rides the commit carrying its effect
(the plan-gate commit, or the round's brief). A new session resumes from these
alone: a ticked section with a round record is finished, never re-run.

## Red flags: STOP, you are running the factory wrong

- "Section 3 could start while section 2's round finishes." One round at a
  time; the budget makes retries affordable, not rounds concurrent.
- "These sections are marked `[parallel: yes]`, so I'll dispatch both rounds at
  once." The factory never fans out concurrent dispatch; a parallel group stops
  and becomes a lane plan for the user to run as dispatcher, or runs sequentially
  on `continue`.
- "The subagent forgot to commit, I'll commit its work from here." The
  foreman schedules and checks; a round without its commit is a failed round,
  retried fresh.
- "This stuck section is small, I'll just do it inline in the main session."
  The budget ran out; report the stuck section and stop.
- "This section is marked `sai-hu`, but its task list looks mechanical, so
  `too-te` will do." The annotation is the starting tier, not a suggestion;
  the plan author judged the section, and the round is not the place to
  re-litigate it.
- "The `sai-hu` section failed twice, escalate it." There is nothing to
  escalate to; stop the factory and report it to the user.
- "The `too-te` round went quiet right after announcing its next step, retry
  it." That is the turn-budget signature; the same section on the same role
  stops in the same place. Narrow it or hand it to `sai-hu`.
- "There's no active change, but the goal is obvious from the repo." Step 0
  refuses; propose a change first.
- "My tasks.md rewrite is clearly fine, no need to wait for approval." In an
  interactive session the diff waits for the user; only an explicit unattended
  signal turns the wait into a committed, ledgered rewrite.
- "The user has gone quiet, so this run is unattended now." Silence is never
  the signal; ask as written.
