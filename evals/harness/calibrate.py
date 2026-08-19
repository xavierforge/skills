#!/usr/bin/env python3
"""Reproducible scale calibration / self-test for check.py.

Ground truth is the **published per-assertion verdicts** in the suite report
pages (`evals/review-artifacts-eval.md`, `evals/factory-eval.md`). The historical
raw run workspaces are disposable and gone (EVALUATION.md iron rule 2), so this
reconstructs each published run's end-state from the report narrative -- the
sandbox via `build_sandbox.sh` plus the artifacts / outputs the report says the
run produced -- and asserts that check.py's **machine** verdicts reproduce the
published PASS/FAIL. That makes it the checker's re-runnable scale calibration:
if a future edit to check.py silently regrades, this fails.

`llm_judged` rows are deferred by check.py (`passed: null`); the published verdict
is carried here only to show the reconciliation (published count = check.py
machine passes + the deferred rows the report scored pass), never asserted
mechanically.

Run:   python3 evals/harness/calibrate.py
Exit:  0 iff check.py reproduces every published machine verdict, except the one
       documented, inherent exception in ALLOWED_DIVERGENCES below.

Note on scope: this pins the machine subset (14 check types) against the
published tables. It is intentionally offline and deterministic -- it spends no
subscription run and calls no LLM -- which is exactly why the calibration
evidence lives in the repo now instead of a scratch dir.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HARNESS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HARNESS))
BUILD = os.path.join(HARNESS, "build_sandbox.sh")
CASES = os.path.join(REPO, "evals", "cases")

_spec = importlib.util.spec_from_file_location("check", os.path.join(HARNESS, "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

ENV = dict(os.environ, GIT_AUTHOR_NAME="Eval Bot", GIT_AUTHOR_EMAIL="eval@example.com",
           GIT_COMMITTER_NAME="Eval Bot", GIT_COMMITTER_EMAIL="eval@example.com")

# The single inherent exception: factory/3 without_skill exp3 is git_log_count[0,0].
# The baseline did the mega-section work UNCOMMITTED, so any git-level check reads
# 0 commits = PASS, while the human grader failed it holistically. It is not
# fixable: the legitimate with_skill arm ALSO leaves a dirty tree (it rewrites
# tasks.md in place), so git_clean can't be added without false-failing the
# correct behavior. The check is a guard both arms pass; the plan-gate
# discrimination lives in the two llm_judged rows check.py defers.
ALLOWED_DIVERGENCES = {
    ("factory/3 without_skill", "Execution stops waiting for approval"),
}

WORK = tempfile.mkdtemp(prefix="calibrate-")
UNEXPECTED = []


def sh(cwd, *a):
    subprocess.run(a, cwd=cwd, env=ENV, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build(suite, idn, run):
    subprocess.run(["bash", BUILD, suite, str(idn), os.path.join(run, "sandbox")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=ENV)
    os.makedirs(os.path.join(run, "outputs"), exist_ok=True)
    return os.path.join(run, "sandbox")


def fresh(name):
    run = os.path.join(WORK, name)
    os.makedirs(os.path.join(run, "outputs"), exist_ok=True)
    return run


def write_out(run, result="", transcript="", pr_body=None):
    open(os.path.join(run, "outputs", "result.md"), "w").write(result)
    open(os.path.join(run, "outputs", "transcript.md"), "w").write(transcript)
    if pr_body is not None:
        open(os.path.join(run, "outputs", "PR_BODY.md"), "w").write(pr_body)


def report(label, suite, idn, run, published):
    """Grade the reconstructed run with check.py and compare to `published`
    (the report's per-assertion verdict, case-file order)."""
    rows = check.grade(run, os.path.join(CASES, f"{suite}.json"), f"{suite}/{idn}")
    assert len(rows) == len(published), f"{label}: {len(rows)} rows vs {len(published)} published"
    machine_pass = sum(1 for r in rows if r["passed"] is True)
    machine_tot = sum(1 for r in rows if r["passed"] is not None)
    print(f"\n### {label}   published {sum(published)}/{len(published)}"
          f"   |  check.py machine {machine_pass}/{machine_tot}"
          f" (+{len(rows) - machine_tot} deferred)")
    for r, pub in zip(rows, published):
        if r["passed"] is None:
            print(f"    defer  (published {'PASS' if pub else 'FAIL'})  {r['text'][:56]}")
            continue
        ok = r["passed"] == bool(pub)
        tag = "OK"
        if not ok:
            allowed = any(label == a[0] and r["text"].startswith(a[1]) for a in ALLOWED_DIVERGENCES)
            if allowed:
                tag = "OK*"  # documented inherent exception
            else:
                tag = "XX"
                UNEXPECTED.append(f"{label}: {r['text'][:50]}")
        print(f"    [{tag:3s}] check={'PASS' if r['passed'] else 'FAIL'}"
              f"  pub={'PASS' if pub else 'FAIL'}  {r['text'][:52]}")


# ==========================================================================
# review-artifacts  (published: eval1 4/4 & 1/4; eval2 4/4 & 2/4; eval3 4/4 & 1/4)
# review-artifacts-eval.md "Results (iteration-1)" table + grading detail.
# ==========================================================================
r = fresh("ra1-with"); build("review-artifacts", 1, r)
write_out(r, result="## Step 0c review reconciliation\n- vibe-diff: PASS - "
                    ".review/feat-demo-gadget/diff-review.json, tests pass (3)\n"
                    "- cross-check: not run\n- verify: not run\n")
report("ra1 with_skill", "review-artifacts", 1, r, [1, 1, 1, 1])

r = fresh("ra1-old"); build("review-artifacts", 1, r)
write_out(r, result="BLOCKED: no verification evidence found.\n")
report("ra1 old_skill", "review-artifacts", 1, r, [0, 0, 0, 1])

# eval-2 was re-specified in batch 4 to the HARDENED refusal contract (the
# vibe-diff skill now requires a spec source and hard-stops otherwise). There is
# no pre-existing published table for this contract, so the ground truth here is
# batch 4's own measurement: regrading batch-3's retained real runs under the
# rewritten eval-2 gave with_skill 4/4, without_skill 3/4. The reconstructions
# below reproduce those end-states (a correct refusal vs a bare baseline review).
r = fresh("ra2-with"); build("review-artifacts", 2, r)  # correct hardened refusal: writes nothing
write_out(r, result="There's nothing to check this diff against: no active OpenSpec change and no "
                    "saved mini-spec, so per the skill this is a hard stop (a diff reviewed against "
                    "nothing is not a review). To proceed, run /begin describing the work (it saves a "
                    "mini-spec), or open an OpenSpec change, then re-invoke /vibe-diff.\n")
report("ra2 with_skill", "review-artifacts", 2, r, [1, 1, 1, 1])

r = fresh("ra2-without"); build("review-artifacts", 2, r)  # baseline reviews anyway, no /begin pointer
write_out(r, result="There's no active change or spec here, but I read the diff on feat/add-logging "
                    "and reviewed it directly: it adds logging to hello(). Looks fine.\n")
report("ra2 without_skill", "review-artifacts", 2, r, [1, 1, 1, 0])

r = fresh("ra3-with"); sb = build("review-artifacts", 3, r)
os.makedirs(os.path.join(sb, ".review", "feat-parser"), exist_ok=True)
json.dump({"layer": "cross-check", "findings": [
    {"axis": "spec", "title": "R3 reject duplicate keys unimplemented", "severity": "high", "actioned": False},
    {"axis": "standards", "title": "missing docstring", "severity": "medium", "actioned": False}]},
          open(os.path.join(sb, ".review/feat-parser/review-verdict.json"), "w"))
write_out(r, result="## Standards\n- missing docstring\n## Spec\n- R3 duplicate key not rejected\n")
report("ra3 with_skill", "review-artifacts", 3, r, [1, 1, 1, 1])

r = fresh("ra3-without"); sb = build("review-artifacts", 3, r)
json.dump({"issues": ["dup keys"]}, open(os.path.join(sb, "review_verdict.json"), "w"))  # invented at repo root
write_out(r, result="parser does not reject duplicate keys (R3).\n")
report("ra3 without_skill", "review-artifacts", 3, r, [0, 0, 0, 1])

# ==========================================================================
# factory  (published: eval1 7/8 & 2/8; eval2 4/4 & 3/4; eval3 3/3 & 0/3)
# factory-eval.md "Results (iteration-1)" per-scenario breakdown.
# ==========================================================================
r = fresh("fac1-with"); sb = build("factory", 1, r)
tf = os.path.join(sb, "openspec/changes/add-helpers/tasks.md")
t = open(tf).read()
for b in ("1.1", "1.2", "2.1", "2.2", "3.1", "3.2"):
    t = t.replace(f"[ ] {b}", f"[x] {b}")
open(tf, "w").write(t)
for i, m in enumerate(("feat(greetings): add farewell", "feat(greetings): add greet_all",
                       "feat(greetings): add shout"), 1):
    open(os.path.join(sb, "src/greetings.py"), "a").write(f"\ndef h{i}(): pass\n")
    sh(sb, "git", "add", "-A"); sh(sb, "git", "commit", "-m", m)
write_out(r, transcript="rounds 1-3 fresh subagents; verify unavailable; STOP before push.\n")
report("factory/1 with_skill", "factory", 1, r, [1, 1, 1, 1, 1, 0, 1, 1])  # 7/8: miss = ledger total (llm)

r = fresh("fac1-without"); build("factory", 1, r)
write_out(r, transcript="implemented all three helpers inline with tests; awaiting permission to commit.\n")
report("factory/1 without_skill", "factory", 1, r, [0, 0, 0, 0, 1, 0, 0, 1])  # 2/8: freebies

r = fresh("fac2-with"); build("factory", 2, r)
write_out(r, result="Serves OpenSpec projects only; no active change under openspec/changes/. Propose a change first.\n")
report("factory/2 with_skill", "factory", 2, r, [1, 1, 1, 1])  # 4/4

r = fresh("fac2-without"); build("factory", 2, r)
write_out(r, result="ran openspec doctor; nothing to do.\n")
report("factory/2 without_skill", "factory", 2, r, [1, 0, 1, 1])  # 3/4: miss = refusal shape (llm)

r = fresh("fac3-with"); build("factory", 3, r)
write_out(r, result="mega-section rejected on the verifiable property; here is a loop-ready rewrite + diff. Approve?\n")
report("factory/3 with_skill", "factory", 3, r, [1, 1, 1])  # 3/3

r = fresh("fac3-without"); build("factory", 3, r)
write_out(r, result="implemented the mega-section (impl+tests+README) in one go (uncommitted).\n")
report("factory/3 without_skill", "factory", 3, r, [0, 0, 0])  # 0/3 (exp3 is the allowlisted guard)

# ==========================================================================
shutil.rmtree(WORK, ignore_errors=True)
print("\n========================= SUMMARY =========================")
print("OK = check.py machine verdict matches the published table.")
print("OK* = documented inherent divergence (see ALLOWED_DIVERGENCES).")
print("defer = llm_judged, deferred by check.py (published verdict shown for reconciliation).")
if UNEXPECTED:
    print(f"\nFAIL: {len(UNEXPECTED)} unexpected divergence(s):")
    for u in UNEXPECTED:
        print("   XX", u)
    sys.exit(1)
print("\nPASS: check.py reproduces every published machine verdict "
      "(1 documented inherent exception allowlisted).")
