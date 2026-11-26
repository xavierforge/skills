#!/usr/bin/env python3
"""Re-decide the machine checks of an already-run iteration from its recorded outputs.

Usage:
    regrade.py <suite> <iteration>           # e.g. regrade.py land 8

For the case where an assertion was wrong, not the run: the case file (or
`check.py`) changed after the iteration ran, and the recorded sandbox and
outputs are still the right evidence. No executor runs and no model is called.

- **Machine rows are recomputed** by `check.py` against the run's retained
  workspace (`sandbox/` and `outputs/`), using the case file as it is now.
- **Grader verdicts are kept** when the row's `text` and `rubric` are both
  unchanged. A row whose rubric changed, or that is new, is left
  `passed: null` for the next `backfill.py` pass to judge.
- **The regrade is recorded.** `fingerprint.regrade` is a list that gains one
  `{harness_commit, checker_sha256, timestamp, changed}` entry per pass that
  altered the file, where `changed` lists every row whose verdict moved, so a
  harvested score never silently differs from the one the run first produced.
  A pass that alters nothing leaves the file untouched, so regrading twice is
  safe. The original fingerprint fields stay.

Run `backfill.py <suite> <iteration>` afterwards: it judges any row left null,
then re-aggregates and re-harvests (with no null rows it calls no model).
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
REPO = HARNESS_DIR.parent.parent
sys.path.insert(0, str(HARNESS_DIR))

import check  # noqa: E402  (the universal checker, imported for its grade())
from backfill import recompute_summary  # noqa: E402


def die(msg: str) -> "None":
    print(f"ABORT: {msg}", file=sys.stderr)
    sys.exit(1)


def out(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def regrade_run(gpath: Path, case: Path, fixture: str, stamp: dict) -> list:
    """Rewrite one grading.json in place. Returns the rows whose verdict moved."""
    old = json.load(open(gpath))
    prior = {e["text"]: e for e in old.get("expectations", [])}
    rows, changed = [], []
    for row in check.grade(str(gpath.parent), str(case), fixture):
        before = prior.get(row["text"])
        if row["check_type"] == "llm_judged":
            if before and before.get("rubric", "") == row.get("rubric", ""):
                row = before  # same question, same evidence: the verdict stands
        elif before is None or before.get("passed") != row["passed"]:
            changed.append({"text": row["text"],
                            "from": before.get("passed") if before else None,
                            "to": row["passed"]})
        rows.append(row)
    if rows == old.get("expectations"):
        return []  # nothing moved, not even an evidence string: leave the file alone
    old["expectations"] = rows
    old["summary"] = recompute_summary(rows)
    old.setdefault("fingerprint", {}).setdefault("regrade", []).append({**stamp, "changed": changed})
    json.dump(old, open(gpath, "w"), indent=2)
    return changed


def main() -> None:
    if len(sys.argv) != 3:
        die("usage: regrade.py <suite> <iteration>")
    suite, iteration = sys.argv[1], sys.argv[2]
    ws = REPO / "skills" / suite / f"{suite}-workspace" / f"iteration-{iteration}"
    case = REPO / "evals" / "cases" / f"{suite}.json"
    if not ws.exists():
        die(f"no workspace: {ws} (a regrade needs the recorded sandbox and outputs)")
    gradings = sorted(ws.glob("eval-*/*/run-*/grading.json"))
    if not gradings:
        die(f"no grading.json under {ws}")
    stamp = {
        "harness_commit": out("git", "-C", str(REPO), "rev-parse", "--short", "HEAD") or "unknown",
        "checker_sha256": hashlib.sha256((HARNESS_DIR / "check.py").read_bytes()).hexdigest(),
        "timestamp": out("date", "-u", "+%Y-%m-%dT%H:%M:%SZ"),
    }
    moved = 0
    for gpath in gradings:
        run = gpath.parent
        if not (run / "sandbox").is_dir() or not (run / "outputs").is_dir():
            die(f"{run} has no sandbox/ or outputs/; its evidence is gone, so it cannot be regraded")
        fixture = f"{suite}/{run.parent.parent.name.removeprefix('eval-')}"
        changed = regrade_run(gpath, case, fixture, stamp)
        moved += len(changed)
        label = f"{run.parent.parent.name}/{run.parent.name}/{run.name}"
        if not changed:
            print(f">> {label}: unchanged")
        for c in changed:
            print(f">> {label}: {c['from']} -> {c['to']}  {c['text']}")
    print(f">> regraded {len(gradings)} runs, {moved} verdicts moved; "
          f"now run: backfill.py {suite} {iteration}")


if __name__ == "__main__":
    main()
