#!/usr/bin/env python3
"""Fold `llm_judged` verdicts into an already-graded iteration.

Usage:
    backfill.py <suite> <iteration>          # e.g. backfill.py begin 4

The supplemental grading pass EVALUATION.md describes ("How `llm_judged` is
resolved"). `check.py` decides every machine check and defers each `llm_judged`
row with `passed: null`; this script fills only those deferred rows and leaves
everything else byte-for-byte alone:

- **Only the null rows move.** Machine rows, `fingerprint.checker_sha256`, and
  every other existing field are untouched. `summary.pass_rate` keeps its name
  AND its meaning: the machine subset. A new `summary.total_pass_rate` is added
  over machine + grader rows, so the two are reported side by side.
- **One judge per row.** Each deferred row is judged by a single `claude -p`
  call (the subscription, cheap tier, offline, strict-serial, stop on any
  401/429/limit) fed the row's `text` + `rubric` and the run's own
  `result.md` / `transcript.md` / `git-state.txt`; the judge returns
  `{passed, evidence}`.
- **Grader identity is recorded separately.** The verdict lands in the row with
  `verdict_source: "grader"`, and a sibling `fingerprint.grader` block records
  `{model, rubric_sha256, harness_commit}`, distinct from `checker_sha256`, so
  a mechanical verdict and a model-judged one are never conflated.
- **Re-aggregate + re-harvest.** `benchmark.json` is regenerated (skill-creator's
  aggregate, machine subset) and gains a `run_summary_total` block; the updated
  small JSON is copied home to `evals/results/<suite>/iteration-<n>/`.

Execution discipline mirrors `run_eval.sh`: `ANTHROPIC_API_KEY` /
`ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` must be unset (else abort), the
nested `claude -p` runs here in the main loop (never a subagent), and any limit
signal stops the whole pass with no retry and no score-padding.
"""

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
REPO = HARNESS_DIR.parent.parent
MODEL = os.environ.get("EVAL_MODEL", "sonnet")

# Bound the prompt so a long transcript cannot blow the judge's context.
# Wide caps: 60k chars is ~15k tokens, comfortable for the judge's window.
# 16k proved too tight in practice: factory-scale runs overflowed it and the
# judge failed assertions whose evidence (later dispatches, the final ledger)
# sat past the cap.
TRANSCRIPT_CAP = 60000
RESULT_CAP = 16000


def die(msg: str, code: int = 1) -> "None":
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(code)


def note(msg: str) -> None:
    print(f">> {msg}", flush=True)


def guard_subscription() -> None:
    """Same guard as run_eval.sh: no API key / token / endpoint override."""
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
        if os.environ.get(v):
            die(f"{v} is set; backfill judging must go through the subscription. "
                f"unset it (and any other ANTHROPIC_* override) and retry.", 3)


def clean_env() -> dict:
    env = os.environ.copy()
    for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDECODE"):
        env.pop(v, None)
    return env


def git_short_head() -> str:
    try:
        return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def stats(values: list) -> dict:
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
    n = len(values)
    mean = sum(values) / n
    stddev = math.sqrt(sum((x - mean) ** 2 for x in values) / (n - 1)) if n > 1 else 0.0
    return {"mean": round(mean, 4), "stddev": round(stddev, 4),
            "min": round(min(values), 4), "max": round(max(values), 4)}


def discover_aggregate() -> "Path|None":
    override = os.environ.get("SKILL_CREATOR_DIR")
    if override:
        p = Path(override) / "scripts" / "aggregate_benchmark.py"
        return p if p.exists() else None
    root = Path.home() / ".claude" / "plugins"
    for hit in root.rglob("skill-creator/scripts/aggregate_benchmark.py"):
        return hit
    return None


def read_capped(path: Path, cap: int) -> str:
    if not path.exists():
        return "(missing)"
    txt = path.read_text(encoding="utf-8", errors="replace")
    if len(txt) > cap:
        # Keep head AND tail: end-of-run evidence (final ledger, last
        # dispatches, the closing report) decides many assertions, so a
        # head-only cut starves the judge of exactly the part that matters.
        head, tail = (cap * 3) // 5, cap - (cap * 3) // 5
        return (txt[:head]
                + f"\n...(middle truncated, {len(txt) - cap} chars elided)...\n"
                + txt[-tail:])
    return txt


def build_prompt(text: str, rubric: str, run_dir: Path) -> str:
    out = run_dir / "outputs"
    result = read_capped(out / "result.md", RESULT_CAP)
    transcript = read_capped(out / "transcript.md", TRANSCRIPT_CAP)
    git_state = read_capped(out / "git-state.txt", 4000)
    return f"""You are grading ONE expectation from a skill behavioral eval. Decide PASS or
FAIL strictly from the evidence in the run's final reply, transcript, and final
git state below. Do not use any tools; answer directly from what is quoted here.

EXPECTATION:
{text}

RUBRIC (how to judge this expectation):
{rubric}

--- FINAL REPLY (result.md) ---
{result}

--- TRANSCRIPT (transcript.md; may be truncated) ---
{transcript}

--- FINAL GIT STATE (git-state.txt) ---
{git_state}

The burden of proof to pass is on the expectation: if the evidence is absent, or
only superficially satisfies the wording while the underlying outcome is wrong or
incomplete, return false. Respond with ONLY a JSON object on one line, no prose
and no code fence:
{{"passed": true or false, "evidence": "<one to three sentences quoting the specific text or git fact that decides it>"}}
"""


def limit_signal(stdout: str, stderr: str) -> "str|None":
    """Return a limit description if a hard 401/429/usage-limit is seen, else None.

    Mirrors run_eval.sh: scan stderr text, then parse stream events properly (never
    grep the JSON body, so a duration_ms like 102429 cannot false-positive).
    """
    low = stderr.lower()
    for needle in ("rate limit", "rate-limit", "usage limit", "401", "429", "quota", "unauthor"):
        if needle in low:
            return f"stderr flagged: {needle}"
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "rate_limit_event":
            info = o.get("rate_limit_info", {}) or {}
            st = info.get("status")
            if st and not str(st).startswith("allowed"):
                return f"stream rate_limit_event status={st}"
    return None


def final_result_text(stdout: str) -> "str|None":
    final = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "result" and isinstance(o.get("result"), str):
            final = o["result"]
    return final


_PASSED_RE = re.compile(r'"passed"\s*:\s*(true|false)', re.IGNORECASE)
_EVIDENCE_RE = re.compile(r'"evidence"\s*:\s*"(.*)', re.IGNORECASE | re.DOTALL)


def _scan_strict(reply: str) -> "dict|None":
    """First clean JSON object carrying a boolean `passed`, tolerant of surrounding prose.

    Scans every `{` and uses `raw_decode`, which stops at the end of the first
    valid JSON object, so trailing prose after the object (the model explaining
    itself) cannot break parsing the way a first-brace-to-last-brace slice would.
    """
    dec = json.JSONDecoder()
    idx = reply.find("{")
    while idx != -1:
        try:
            o, _ = dec.raw_decode(reply[idx:])
        except ValueError:
            idx = reply.find("{", idx + 1)
            continue
        if isinstance(o, dict) and isinstance(o.get("passed"), bool):
            return {"passed": o["passed"], "evidence": str(o.get("evidence", "")).strip()}
        idx = reply.find("{", idx + 1)
    return None


def _repair_tail(reply: str) -> "dict|None":
    """Recover a verdict whose JSON is well formed but missing trailing close tokens.

    The judge occasionally ends its turn one brace short: `{"passed": ...,
    "evidence": "...text."` with no closing `}` (stop_reason end_turn, not a token
    cap, so the evidence value itself is intact). Append the minimal close tokens
    and re-decode, which recovers the full evidence faithfully rather than guessing.
    """
    idx = reply.find("{")
    if idx == -1:
        return None
    dec = json.JSONDecoder()
    body = reply[idx:]
    for suffix in ("}", '"}', '"]}', "]}"):
        try:
            o, _ = dec.raw_decode(body + suffix)
        except ValueError:
            continue
        if isinstance(o, dict) and isinstance(o.get("passed"), bool):
            return {"passed": o["passed"], "evidence": str(o.get("evidence", "")).strip(), "_salvaged": True}
    return None


def _regex_salvage(reply: str) -> "dict|None":
    """Last resort: pull the boolean verdict (and any legible evidence prefix) by regex.

    Reached only when both a clean parse and a tail repair fail. The verdict is
    what matters; the evidence is recorded best effort from the prefix so a human
    can still see what the judge was saying.
    """
    m = _PASSED_RE.search(reply)
    if not m:
        return None
    passed = m.group(1).lower() == "true"
    ev = ""
    em = _EVIDENCE_RE.search(reply)
    if em:
        raw = em.group(1).rstrip()
        for tail in ('"}', '"'):
            if raw.endswith(tail):
                raw = raw[: -len(tail)]
                break
        ev = raw.strip()
    return {"passed": passed, "evidence": ev, "_salvaged": True}


def extract_verdict(reply: str) -> "dict|None":
    """Pull {passed, evidence} out of the judge reply.

    Three tiers, strictest first: a clean object (`_scan_strict`), then a
    brace-short object closed and re-decoded (`_repair_tail`), then a regex grab of
    the boolean verdict (`_regex_salvage`). The last two set `_salvaged` so the
    caller can mark the evidence; only a reply with no legible verdict returns None.
    """
    return _scan_strict(reply) or _repair_tail(reply) or _regex_salvage(reply)


def judge_row(text: str, rubric: str, run_dir: Path) -> dict:
    """One claude -p judge call. Returns {passed, evidence} or raises on limit."""
    prompt = build_prompt(text, rubric, run_dir)
    proc = subprocess.run(
        ["claude", "--safe-mode", "--dangerously-skip-permissions", "--model", MODEL,
         "--output-format", "stream-json", "--verbose", "-p", prompt],
        cwd=str(run_dir), env=clean_env(), stdin=subprocess.DEVNULL,
        capture_output=True, text=True,
    )
    sig = limit_signal(proc.stdout, proc.stderr)
    if proc.returncode != 0 or sig:
        raise SystemExit(
            f"ABORT: judge stopped (rc={proc.returncode}, limit={sig}). "
            f"NOT retrying (execution discipline). Progress is saved for graded rows."
        )
    reply = final_result_text(proc.stdout)
    if reply is None:
        return {"passed": None, "evidence": "grader: stream had no final result event", "_error": True}
    verdict = extract_verdict(reply)
    if verdict is None:
        return {"passed": None, "evidence": f"grader: unparseable reply: {reply[:200]}", "_error": True}
    if verdict.pop("_salvaged", False):
        verdict["evidence"] = f"[salvaged from malformed grader reply] {verdict['evidence']}".strip()
    return verdict


def recompute_summary(expectations: list) -> dict:
    machine = [e for e in expectations if e.get("check_type") != "llm_judged"]
    m_decided = [e for e in machine if e.get("passed") is not None]
    m_passed = sum(1 for e in m_decided if e["passed"])
    m_total = len(m_decided)
    graded = [e for e in expectations if e.get("check_type") == "llm_judged" and e.get("passed") is not None]
    g_passed = sum(1 for e in graded if e["passed"])
    t_passed = m_passed + g_passed
    t_total = m_total + len(graded)
    still_null = sum(1 for e in expectations if e.get("passed") is None)
    return {
        # machine subset: name and meaning unchanged
        "passed": m_passed, "failed": m_total - m_passed, "total": m_total,
        "pass_rate": round(m_passed / m_total, 4) if m_total else 0.0,
        "assertions_total": len(expectations),
        "undecided": still_null,
        # total after backfill: machine + grader
        "total_passed": t_passed, "total_failed": t_total - t_passed, "total_decided": t_total,
        "total_pass_rate": round(t_passed / t_total, 4) if t_total else 0.0,
        "grader_decided": len(graded),
    }


def backfill_run(gpath: Path, harness_commit: str) -> dict:
    """Grade the deferred rows of one run's grading.json. Returns a per-run report."""
    g = json.load(open(gpath))
    exps = g["expectations"]
    run_dir = gpath.parent
    rows = [e for e in exps if e.get("check_type") == "llm_judged" and e.get("passed") is None]
    report = {"grading": str(gpath), "rows": []}
    for e in rows:
        note(f"judge: {run_dir.parent.parent.name}/{run_dir.parent.name} — {e['text'][:60]}")
        verdict = judge_row(e["text"], e.get("rubric", ""), run_dir)
        e["passed"] = verdict["passed"]
        e["evidence"] = verdict["evidence"]
        e["verdict_source"] = "grader"
        report["rows"].append({"text": e["text"], "passed": verdict["passed"],
                               "evidence": verdict["evidence"], "error": verdict.get("_error", False)})
    # rubric_sha256: identity of the rubrics this grader pass consumed for this run
    llm_rows = sorted(({"text": e["text"], "rubric": e.get("rubric", "")}
                       for e in exps if e.get("check_type") == "llm_judged"),
                      key=lambda x: x["text"])
    rubric_sha = hashlib.sha256(json.dumps(llm_rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    g["summary"] = recompute_summary(exps)
    fp = g.setdefault("fingerprint", {})
    # Stamp the grader identity only when this pass judged something: a pass
    # that found no null row (e.g. the re-aggregate after regrade.py) must not
    # overwrite the record of who actually judged.
    if rows or "grader" not in fp:
        fp["grader"] = {"model": MODEL, "rubric_sha256": rubric_sha, "harness_commit": harness_commit}
    json.dump(g, open(gpath, "w"), indent=2)
    report["summary"] = g["summary"]
    return report


def main() -> None:
    if len(sys.argv) != 3:
        die("usage: backfill.py <suite> <iteration>")
    suite, iteration = sys.argv[1], sys.argv[2]
    guard_subscription()

    ws = REPO / "skills" / suite / f"{suite}-workspace" / f"iteration-{iteration}"
    if not ws.exists():
        die(f"no workspace: {ws} (run the suite first; the workspace is the grader input)")
    home = REPO / "evals" / "results" / suite / f"iteration-{iteration}"
    harness_commit = git_short_head()
    note(f"backfill suite={suite} iteration={iteration} model={MODEL} ws={ws}")

    gradings = sorted(ws.glob("eval-*/*/run-*/grading.json"))
    if not gradings:
        die(f"no grading.json under {ws}")

    reports = []
    for gpath in gradings:
        reports.append(backfill_run(gpath, harness_commit))

    # Re-aggregate (machine subset) via skill-creator, then add the total block.
    agg = discover_aggregate()
    if agg:
        subprocess.run(["python3", str(agg), str(ws), "--skill-name", suite],
                       check=True, capture_output=True, text=True)
        note(f"re-aggregated -> {ws}/benchmark.json")
    else:
        note("skill-creator aggregate not found; benchmark.json not regenerated (set SKILL_CREATOR_DIR)")

    bpath = ws / "benchmark.json"
    if bpath.exists():
        bench = json.load(open(bpath))
        totals: dict = {}
        for gpath in gradings:
            g = json.load(open(gpath))
            # config = the arm dir name (eval-N/<arm>/run-M/grading.json)
            config = gpath.parent.parent.name
            totals.setdefault(config, []).append(g["summary"].get("total_pass_rate", 0.0))
        rst = {cfg: {"pass_rate": stats(vals)} for cfg, vals in totals.items()}
        cfgs = [c for c in rst]
        if len(cfgs) >= 2:
            d = rst[cfgs[0]]["pass_rate"]["mean"] - rst[cfgs[1]]["pass_rate"]["mean"]
            rst["delta"] = {"pass_rate": f"{d:+.2f}"}
        bench["run_summary_total"] = rst
        json.dump(bench, open(bpath, "w"), indent=2)
        note("added run_summary_total (machine + grader) to benchmark.json")

    # Harvest small JSON home (overwrite the machine-only copies with the folded ones).
    home.mkdir(parents=True, exist_ok=True)
    if bpath.exists():
        shutil.copy(bpath, home / "benchmark.json")
    for gpath in gradings:
        rel = str(gpath.relative_to(ws)).replace("/", "_")
        shutil.copy(gpath, home / rel)
    note(f"harvested small JSON -> {home}")

    # Final report: per-row verdicts + per-run machine/total, machine-readable tail.
    print("\n==== BACKFILL VERDICTS ====")
    fails, errors = [], []
    for r in reports:
        for row in r["rows"]:
            tag = "ERROR" if row["error"] else ("PASS" if row["passed"] else "FAIL")
            print(f"[{tag}] {r['grading'].split('/iteration-')[1]}")
            print(f"       {row['text']}")
            print(f"       -> {row['evidence'][:200]}")
            if row["error"]:
                errors.append(row)
            elif not row["passed"]:
                fails.append(row)
    print("\n==== SUMMARY (per run: machine pass_rate | total pass_rate) ====")
    for r in reports:
        s = r["summary"]
        print(f"  {r['grading'].split('/iteration-')[1]}: machine {s['pass_rate']} ({s['passed']}/{s['total']}) "
              f"| total {s['total_pass_rate']} ({s['total_passed']}/{s['total_decided']})")
    print(f"\nfails={len(fails)} errors={len(errors)}")
    if errors:
        die(f"{len(errors)} row(s) could not be graded (unparseable/no-result); see ERROR rows above.", 4)


if __name__ == "__main__":
    main()
