#!/usr/bin/env python3
"""The one general mechanical checker for schema-v1 behavioral evals.

It is the *sole* interpreter of the check-type vocabulary defined in
evals/EVALUATION.md. Given one run directory, the suite's case file, and the
fixture key, it evaluates every expectation's typed `check` against two
surfaces:

  * the **sandbox git tree** (`<run>/sandbox`)  -> git / filesystem / json checks
  * the **run's own outputs** (`<run>/outputs/{result,transcript,PR_BODY}.md`)
    -> text_contains

and writes `<run>/grading.json` in the grader schema the aggregate + viewer
consume: `expectations: [{text, passed, evidence}]`. Machine checks resolve to
`passed: true|false`; `llm_judged` expectations are deferred with `passed: null`
and carry their rubric so a later skill-creator grader pass can fold a verdict
into the same file. The driver's normalize pass recomputes `summary` (excluding
the `null` rows) and stamps the fingerprint; the local `summary` written here is
for standalone / calibration use.

Usage:  check.py <run_dir> <case.json> <suite/id>

Design notes:
  * Deterministic: same inputs -> same grading.json (so `fingerprint.checker_sha256`
    is meaningful and the result is reproducible). No LLM call lives here.
  * `git_log_count`'s default `base` is the fixture's pre-run tip, which for every
    current fixture equals the default-branch tip (each feature branch is cut from
    the default branch at scaffold time), so `<default>..HEAD` counts exactly the
    commits the run added. An explicit `base` ref overrides this.
"""
import json
import os
import re
import subprocess
import sys


# --------------------------------------------------------------------------
# small IO / git helpers
# --------------------------------------------------------------------------
def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def git_out(repo, *args):
    return git(repo, *args)[1].strip()


def default_branch(repo):
    """First of main/trunk/master that exists as a local head (matches
    snapshot.sh's convention). Falls back to the current branch."""
    for name in ("main", "trunk", "master"):
        if git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")[0] == 0:
            return name
    return git_out(repo, "branch", "--show-current") or "HEAD"


def rev(repo, ref):
    rc, out, _ = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return out.strip() if rc == 0 else None


# --------------------------------------------------------------------------
# artifact resolution for text_contains
# --------------------------------------------------------------------------
def artifact(run, source):
    """Return the text of the requested run-output artifact ('' if absent)."""
    out = os.path.join(run, "outputs")
    paths = {
        "result": [os.path.join(out, "result.md"), os.path.join(run, "result.md")],
        "transcript": [os.path.join(out, "transcript.md"), os.path.join(run, "transcript.md")],
        "pr_body": [os.path.join(out, "PR_BODY.md"), os.path.join(run, "PR_BODY.md")],
    }
    if source == "any":
        return "\n".join(artifact(run, s) for s in ("result", "transcript", "pr_body"))
    for candidate in paths.get(source, []):
        txt = read_text(candidate)
        if txt is not None:
            return txt
    return ""


# --------------------------------------------------------------------------
# needle / regex matching shared by file_contains and text_contains
# --------------------------------------------------------------------------
def match_body(body, chk):
    """Evaluate the needle(s)/regex(es) of a *_contains check against `body`.
    Returns (present, detail) where `present` is whether the content matched
    BEFORE applying the `present:false` polarity flip."""
    needles = chk.get("needles") or ([chk["needle"]] if "needle" in chk else [])
    regexes = chk.get("regexes") or ([chk["regex"]] if "regex" in chk else [])
    missing = []
    for n in needles:
        if n not in body:
            missing.append(f"needle {n!r}")
    for rx in regexes:
        if not re.search(rx, body):
            missing.append(f"regex {rx!r}")
    present = not missing
    if present:
        detail = "all present: " + ", ".join([repr(n) for n in needles] + [f"/{r}/" for r in regexes])
    else:
        detail = "missing " + "; ".join(missing)
    return present, detail


def apply_polarity(present, chk, detail):
    """`present:false` means the check passes when the content is ABSENT."""
    want_present = chk.get("present", True)
    passed = present if want_present else (not present)
    if not want_present:
        detail = f"(present:false) {detail}"
    return passed, detail


# --------------------------------------------------------------------------
# json_check helpers
# --------------------------------------------------------------------------
def dotted(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return (False, None)
    return (True, cur)


# --------------------------------------------------------------------------
# the check dispatch
# --------------------------------------------------------------------------
def evaluate(chk, sb, run):
    """Return (passed, evidence). passed is True/False, or None for llm_judged."""
    t = chk.get("type")

    # ---- run-output text --------------------------------------------------
    if t == "text_contains":
        body = artifact(run, chk.get("source", "any"))
        present, detail = match_body(body, chk)
        passed, detail = apply_polarity(present, chk, detail)
        return passed, f"[{chk.get('source', 'any')}] {detail}"

    # ---- filesystem -------------------------------------------------------
    if t == "file_exists":
        paths = chk.get("paths") or ([chk["path"]] if "path" in chk else [])
        want = chk.get("expect", True)
        results = {p: os.path.exists(os.path.join(sb, p)) for p in paths}
        ok = all(v == want for v in results.values())
        return ok, f"expect={want}; " + ", ".join(f"{p}:{'yes' if v else 'no'}" for p, v in results.items())

    if t == "file_size":
        path = chk["path"]
        full = os.path.join(sb, path)
        if not os.path.isfile(full):
            return False, f"{path}: file missing"
        n = os.path.getsize(full)
        lo = chk.get("min_bytes", 0)
        hi = chk.get("max_bytes")
        ok = n >= lo and (hi is None or n <= hi)
        bound = f">= {lo}" + (f", <= {hi}" if hi is not None else "")
        return ok, f"{path}: {n} bytes ({bound})"

    if t == "file_contains":
        path = chk["path"]
        body = read_text(os.path.join(sb, path))
        if body is None:
            body = ""  # missing file == empty content (present:false still passes)
        present, detail = match_body(body, chk)
        passed, detail = apply_polarity(present, chk, detail)
        exists = os.path.exists(os.path.join(sb, path))
        return passed, f"{path} (exists={exists}): {detail}"

    if t == "json_check":
        path = chk["path"]
        raw = read_text(os.path.join(sb, path))
        if raw is None:
            return False, f"{path}: file missing"
        try:
            obj = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            return False, f"{path}: invalid JSON ({e})"
        problems = []
        mk = chk.get("min_keys")
        if mk is not None:
            n = len(obj) if isinstance(obj, dict) else 0
            if n < mk:
                problems.append(f"object has {n} keys, want >= {mk}")
        for k in chk.get("has_keys", []):
            if not (isinstance(obj, dict) and k in obj):
                problems.append(f"missing key {k!r}")
        for k in chk.get("absent_keys", []):
            if isinstance(obj, dict) and k in obj:
                problems.append(f"unexpected key {k!r}")
        for dk, expected in (chk.get("equals") or {}).items():
            found, val = dotted(obj, dk)
            if not found or val != expected:
                problems.append(f"{dk}={val!r} != {expected!r}")
        arr = chk.get("array")
        if arr:
            found, lst = dotted(obj, arr["path"])
            if not found or not isinstance(lst, list) or not lst:
                problems.append(f"array {arr['path']!r} missing/empty")
            else:
                for i, el in enumerate(lst):
                    if not isinstance(el, dict):
                        problems.append(f"{arr['path']}[{i}] not an object")
                        continue
                    for k in arr.get("has_keys", []):
                        if k not in el:
                            problems.append(f"{arr['path']}[{i}] missing {k!r}")
                    for field, allowed in (arr.get("enum") or {}).items():
                        if el.get(field) not in allowed:
                            problems.append(f"{arr['path']}[{i}].{field}={el.get(field)!r} not in {allowed}")
        ok = not problems
        return ok, ("ok" if ok else "; ".join(problems))

    if t == "changes_confined_to":
        prefix = chk["prefix"]
        porcelain = git(sb, "status", "--porcelain")[1]
        stray = []
        for line in porcelain.splitlines():
            if not line.strip():
                continue
            p = line[3:] if len(line) > 3 else line
            if " -> " in p:  # rename: check the destination
                p = p.split(" -> ", 1)[1]
            p = p.strip().strip('"')
            if not p.startswith(prefix):
                stray.append(p)
        ok = not stray
        return ok, ("all changes under " + prefix if ok else "stray: " + ", ".join(stray))

    # ---- git state --------------------------------------------------------
    if t == "git_log_count":
        base = chk.get("base") or default_branch(sb)
        lo, hi = chk["range"]
        rc, out, err = git(sb, "rev-list", "--count", f"{base}..HEAD")
        if rc != 0:
            return False, f"rev-list {base}..HEAD failed: {err.strip()}"
        n = int(out.strip() or "0")
        return (lo <= n <= hi), f"{n} commits on HEAD beyond {base} (want [{lo},{hi}])"

    if t == "commit_subject":
        which = chk.get("which", "head")
        rx = chk["regex"]
        if which == "head":
            subj = git_out(sb, "log", "-1", "--format=%s")
            return bool(re.search(rx, subj)), f"head subject {subj!r} vs /{rx}/"
        base = chk.get("base") or default_branch(sb)
        subs = git_out(sb, "log", "--format=%s", f"{base}..HEAD").splitlines()
        bad = [s for s in subs if not re.search(rx, s)]
        ok = bool(subs) and not bad
        return ok, (f"all {len(subs)} added subjects match /{rx}/" if ok
                    else f"non-matching: {bad or '(no commits added)'}")

    if t == "head_branch":
        cur = git_out(sb, "branch", "--show-current")
        if "equals" in chk:
            return cur == chk["equals"], f"HEAD branch {cur!r} vs {chk['equals']!r}"
        rx = chk["regex"]
        return bool(re.search(rx, cur)), f"HEAD branch {cur!r} vs /{rx}/"

    if t == "branch_exists":
        name = chk["name"]
        want = chk.get("expect", True)
        exists = git(sb, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")[0] == 0
        return exists == want, f"branch {name!r} exists={exists} (expect {want})"

    if t == "branch_count":
        lo, hi = chk["range"]
        names = [b for b in git_out(sb, "branch", "--format=%(refname:short)").splitlines() if b.strip()]
        n = len(names)
        return (lo <= n <= hi), f"{n} local branches {names} (want [{lo},{hi}])"

    if t == "is_ancestor":
        a, d = chk["ancestor"], chk["descendant"]
        ra, rd = rev(sb, a), rev(sb, d)
        if ra is None or rd is None:
            return False, f"unresolved ref (ancestor={a}:{ra}, descendant={d}:{rd})"
        rc = git(sb, "merge-base", "--is-ancestor", a, d)[0]
        return rc == 0, f"{a} {'is' if rc == 0 else 'is NOT'} ancestor of {d}"

    if t == "ref_equals":
        lref, rref = chk["left"], chk["right"]
        lc, rc = rev(sb, lref), rev(sb, rref)
        ok = lc is not None and lc == rc
        return ok, f"{lref}={(lc or '?')[:8]} {'==' if ok else '!='} {rref}={(rc or '?')[:8]}"

    if t == "git_clean":
        want = chk.get("expect", True)
        porcelain = git_out(sb, "status", "--porcelain")
        clean = porcelain == ""
        ok = clean == want
        return ok, (f"tree {'clean' if clean else 'dirty'} (expect {'clean' if want else 'dirty'})"
                    + ("" if clean else f"; {porcelain.count(chr(10)) + 1} entries"))

    if t == "git_no_stash":
        stash = git_out(sb, "stash", "list")
        return stash == "", ("no stash entries" if stash == "" else f"stash present: {stash.splitlines()}")

    # ---- judgment fallback ------------------------------------------------
    if t == "llm_judged":
        return None, "pending: llm_judged -> skill-creator grader"

    return False, f"unknown check type {t!r}"


# --------------------------------------------------------------------------
# public API + CLI
# --------------------------------------------------------------------------
def grade(run_dir, case_path, fixture_key):
    """Grade one run. Returns the list of expectation result dicts."""
    case = json.load(open(case_path))
    ev = next((e for e in case["evals"] if e["fixture"] == fixture_key), None)
    if ev is None:
        raise SystemExit(f"check.py: no eval with fixture {fixture_key!r} in {case_path}")
    sb = os.path.join(run_dir, "sandbox")
    results = []
    for exp in ev["expectations"]:
        chk = exp["check"]
        passed, evidence = evaluate(chk, sb, run_dir)
        row = {"text": exp["text"], "passed": passed, "evidence": evidence,
               "check_type": chk.get("type")}
        if chk.get("type") == "llm_judged":
            row["rubric"] = chk.get("rubric", "")
        results.append(row)
    return results


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: check.py <run_dir> <case.json> <suite/id>")
    run_dir, case_path, fixture_key = argv[1], argv[2], argv[3]
    results = grade(run_dir, case_path, fixture_key)
    decided = [r for r in results if r["passed"] is not None]
    passed = sum(1 for r in decided if r["passed"])
    total = len(decided)
    grading = {
        "expectations": results,
        "summary": {
            "passed": passed, "failed": total - passed, "total": total,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "assertions_total": len(results), "undecided": len(results) - total,
        },
    }
    out = os.path.join(run_dir, "grading.json")
    json.dump(grading, open(out, "w"), indent=2)
    print(f"{fixture_key}: {passed}/{total} machine"
          + (f" (+{len(results) - total} llm_judged deferred)" if len(results) - total else ""))


if __name__ == "__main__":
    main(sys.argv)
