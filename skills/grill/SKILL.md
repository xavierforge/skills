---
name: grill
description: Front-door interview for the delivery pipeline that pins down a change before it is built and ends by producing its spec, a short confirmed brief with testable requirements that /begin saves as the mini-spec. Use when the user asks to be grilled, to stress-test a plan or idea, or to pin down what a change should do before building it; not for ordinary questions, and not for requests that are already unambiguous and self-contained.
---

# /grill: interview until the spec writes itself

The user never sits down to write a spec. They answer questions and confirm a brief, and that brief is the spec: `/begin` saves it as `.review/<slug>/mini-spec.md`, which `/vibe-diff`, `cross-check`, and `/preflight` already read as the baseline. No OpenSpec is needed. The brief is only as good as the questions, so the questions carry the rules below.

## Hard gates

These are the places an agent is tempted to cut a corner. Each one is absolute.

- **Never ask a fact.** Anything the repo, its history, or the environment can answer is looked up, because a user asked for a fact spends attention on what a lookup settles for free.
- **Never ask an opinion a run could settle.** When running something would decide the fork, propose that run instead of asking which way the user feels.
- **Never close on a requirement without a check.** It either gets its test, command, or observable outcome, or it moves to Open questions; a requirement nobody can verify grades nothing downstream.
- **Never act after confirmation.** The confirmed brief ends the turn: no code, no branch, no file, no tool call, because what happens next is the user's call.

## When it does not run

This skill needs a live user to answer. In an unattended or non-interactive run, judged by the same explicit signal defined in the factory skill's *Unattended mode and the reversibility test* section (`<skill-base>/../factory/SKILL.md`, where `<skill-base>` is this skill's base directory), do not interview and do not guess answers: report the ask as blocked, listing the decisions it leaves open, and stop.

## Step 1. State the frame

Before any question, write one sentence saying what you think is being decided or built, and the rung of the closing ladder (Step 4) you expect it to land on. For example: "I read this as choosing how `sync` reports conflicts to the caller, and I expect a rung 1 brief." The user corrects a wrong frame in one line; a wrong frame found in round three costs every answer before it.

Done when the frame sentence is sent and the user has accepted or corrected it.

## Step 2. Work the decision tree in rounds

Every decision branches into the decisions that depend on it. A question is **ready** when every decision it depends on is settled.

1. Each round asks every ready question, at most five, ordered so the ones that unblock the most later questions come first; a longer list gets skimmed. A question that depends on another still open in the same round waits for a later round.
2. Number each question within the round. Give each your recommended answer with a one-clause reason, and word it so a plain "yes" accepts the recommendation.
3. **Facts are yours.** Before putting a question to the user, check whether it is a fact. A single known file you read yourself; anything wider goes to the `Explore` role (the read-only lookup role), and you keep asking the rest of the round while it runs. Only questions downstream of the lookup wait for it.
4. **Runs beat opinions.** When a fork would be settled by running something (does the parser accept this input, how slow is the naive version), the question becomes: the smallest experiment or prototype, and the result that would decide each way. On a yes, run it outside the working tree if it touches nothing in the repo; otherwise it goes to Open questions with that experiment named as the decider.
5. **Probe borrowed answers.** When an answer is a convention or a quality word with no outcome behind it ("make it robust", "the standard way"), ask once what they would want if nobody else had to approve it. Once, because a second push turns probing into badgering.
6. Recompute the tree from the answers and send the next round.

A round looks like this:

```text
Round 2

1. Should a conflict abort the whole sync rather than skip that file? Recommended yes: a partial sync is harder to reason about than a failed one.
2. Should the conflict list go to stderr, one path per line? Recommended yes: it keeps stdout parseable for the scripts that call sync.
3. Should sync exit with code 3 when it finds conflicts? Recommended yes: src/exit.rs already uses 0 to 2, and 3 is free (looked up, not asked).
4. Should --force keep its meaning of "overwrite remote"? Recommended yes: changing a flag's meaning breaks muscle memory silently.
```

Done when the stop test below passes, or the floor below trips.

## Step 3. The stop test

Stop asking when both hold: no open question is ready, and you can predict the user's answer to each of the next three questions you would ask. If you cannot name those three questions and your predictions, the test has not passed.

**Floor.** If three rounds go by and answers keep reopening settled branches instead of narrowing the tree, stop grinding: say the interview is not converging and name the foundational piece that is missing (who it is for, what success looks like, which constraint binds).

Done when the test has passed, or the floor has been called and the user has chosen how to proceed.

## Step 4. Write the brief, sized by the ladder

The ladder: **rung 0**, a trivial change, gets no brief, only a one-line done check, and you stop. **Rung 1**, the default, gets the brief below. **Rung 2**, work needing several independently verifiable sections, gets the brief plus a note, outside it, that a sectioned plan (an OpenSpec change today) must exist before `/factory` or `/section` can run it, listing the candidate sections one line each with the requirement ids each covers.

The brief is 10 to 25 lines of plain Markdown, with these headings in this order:

- **Goal**: one sentence.
- **Requirements**: `R1` to `Rn`, each testable and each ending with its check (the test, command, or observable outcome that proves it). Ids are stable: a correction edits a line in place, a dropped requirement retires its id, and nothing is renumbered, since downstream review cites these ids.
- **Non-goals**: what this change deliberately does not do; never empty, because silent disagreement lives here.
- **Decisions**: each settled branch in one line with its reason; these seed the change's decisions ledger.
- **Assumptions**: everything you defaulted without the user ruling on it, so it stays visibly unconfirmed.
- **Open questions**: empty, or each one deferred with who decides it.

```markdown
## Goal
`sync` stops on the first conflict and reports every conflicting path.

## Requirements
- R1. A conflict aborts the sync before any file is written. Check: `test_sync_conflict_writes_nothing` passes.
- R2. Each conflicting path is printed to stderr, one per line. Check: `sync` on the two-conflict fixture prints exactly two stderr lines.
- R3. A run with conflicts exits with code 3. Check: `sync fixtures/conflict; echo $?` prints 3.

## Non-goals
- No automatic merge or conflict resolution.

## Decisions
- Abort over skip: a partial sync is harder to reason about than a failed one.
- `--force` keeps "overwrite remote": changing a flag's meaning breaks habits silently.

## Assumptions
- Symlinks count as files for conflict detection.

## Open questions
- None.
```

Done when every requirement carries a check and every heading is present in order.

## Step 5. Confirmation gate

Present the brief and ask the user to confirm or correct it line by line, naming lines by requirement id or heading. Only an explicit confirmation counts: a "yes" covering the whole brief, or one per line. "Sounds good" or "sure" gets one follow-up asking which line they would change. A deferral ("whatever you think") is not a ruling: re-ask that point as a choice between two concrete options. A correction is folded in and the whole brief is presented again.

Done when the user has explicitly confirmed the current text of the brief.

## Step 6. Hand off and end the turn

Reply with the exact next line to run, in one fenced block: `/begin` followed by the confirmed brief, verbatim and with nothing else after the command. `/begin` saves spec text passed in its command args verbatim to `.review/<slug>/mini-spec.md`, so any word you add to that line becomes part of the spec. Outside the block, say that `/begin` will propose a branch name from the Goal, and for rung 2 repeat the sectioned-plan note. Then end the turn, per the hard gate above.

Done when the hand-off block is sent and no tool has been called since the confirmation.

The round-by-round decision tree and the explicit confirmation gate were inspired by Matt Pocock's `grilling` skill and Addy Osmani's `interview-me` skill; this repo's version is its own and maintained here.
