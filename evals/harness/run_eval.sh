#!/usr/bin/env bash
# One-shot behavioral-eval driver: build sandboxes, run each arm, grade, and
# aggregate through skill-creator's benchmark + viewer. Folds in the old
# scaffold_all.sh (metadata + sandbox tree) so the reproducible triad is just
# cases/ + build_sandbox.sh + this driver (see EVALUATION.md, iron rule 1).
#
# Usage:
#   run_eval.sh <skill> <eval_id> [runs] [iteration]
#     <skill>     suite name (begin|land|section|factory|vibe-diff|cross-check|spec-viewer|preflight) or "all"
#     <eval_id>   numeric fixture index (1,2,3...) or "all" for every eval in the suite
#     [runs]      runs per arm (default 1; the cheapest scenario is the sentinel)
#     [iteration] iteration number -> iteration-<N> (default 1)
#
# Environment:
#   EVAL_MODEL=sonnet          model locked for every arm (cheap tier, decision-4)
#   EVAL_EXECUTOR=claude       executor CLI: claude (default) or codex. codex runs
#                              `codex exec` on the ChatGPT subscription and requires
#                              an explicit EVAL_MODEL (e.g. gpt-5.6-terra)
#   SKILL_CREATOR_DIR=...       override skill-creator location (else auto-discovered)
#   RUN_EVAL_DRY=1             skip `claude -p`; write stub outputs so the whole
#                              pipeline (scaffold->grade->aggregate->viewer) can be
#                              exercised offline without spending a subscription run
#
# Execution discipline is built in (EVALUATION.md "Execution discipline"):
# subscription only (ANTHROPIC_API_KEY must be unset), strictly serial, cheapest
# eval first, and an immediate stop on any 401/429/limit signal. The nested
# `claude -p` runs here in the main loop, never inside a subagent prompt.
set -euo pipefail

# ---------------------------------------------------------------------------
# Paths and args
# ---------------------------------------------------------------------------
HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HARNESS_DIR/../.." && pwd)"
BUILD="$HARNESS_DIR/build_sandbox.sh"
SNAPSHOT="$HARNESS_DIR/snapshot.sh"
CHECK_PY="$HARNESS_DIR/check.py"                 # the universal schema-v1 checker (sole grader)

SKILL="${1:?usage: run_eval.sh <skill> <eval_id> [runs] [iteration]}"
EVAL_ID="${2:?usage: run_eval.sh <skill> <eval_id> [runs] [iteration]}"
NRUNS="${3:-1}"
ITER="${4:-1}"
MODEL="${EVAL_MODEL:-sonnet}"
EXECUTOR="${EVAL_EXECUTOR:-claude}"
case "$EXECUTOR" in claude|codex) ;; *) echo "ABORT: unknown EVAL_EXECUTOR '$EXECUTOR' (claude|codex)" >&2; exit 3;; esac
if [ "$EXECUTOR" = "codex" ] && [ -z "${EVAL_MODEL:-}" ]; then
  echo "ABORT: EVAL_EXECUTOR=codex requires an explicit EVAL_MODEL (e.g. gpt-5.6-terra)." >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Execution-discipline guard: subscription only
# ---------------------------------------------------------------------------
# Cover every env var that would route a run off the subscription: the API key,
# a custom bearer token, and an endpoint redirect (proxy / gateway / Bedrock-style
# setups). Guarding only ANTHROPIC_API_KEY would let a token or base-URL override
# silently send the run through the API instead. The codex executor has the same
# rule against its own vendor: ChatGPT login only, never an OpenAI API key.
GUARD_VARS="ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL"
[ "$EXECUTOR" = "codex" ] && GUARD_VARS="OPENAI_API_KEY OPENAI_BASE_URL"
for v in $GUARD_VARS; do
  if [ -n "$(eval "echo \${$v:-}")" ]; then
    echo "ABORT: $v is set; eval runs must go through the subscription." >&2
    echo "       unset $v (and any other ANTHROPIC_* override) and retry." >&2
    exit 3
  fi
done

die()  { echo "ABORT: $*" >&2; exit 1; }
note() { echo ">> $*"; }

# ---------------------------------------------------------------------------
# Discover skill-creator (aggregate + viewer are its only contribution)
# ---------------------------------------------------------------------------
discover_skill_creator() {
  if [ -n "${SKILL_CREATOR_DIR:-}" ]; then echo "$SKILL_CREATOR_DIR"; return; fi
  local hit
  hit="$(find "$HOME/.claude/plugins" -type f -path '*skill-creator/scripts/aggregate_benchmark.py' 2>/dev/null | head -1 || true)"
  [ -n "$hit" ] && echo "$(cd "$(dirname "$hit")/.." && pwd)"
}
SC_DIR="$(discover_skill_creator || true)"
AGG="${SC_DIR:+$SC_DIR/scripts/aggregate_benchmark.py}"
VIEWER="${SC_DIR:+$SC_DIR/eval-viewer/generate_review.py}"

# ---------------------------------------------------------------------------
# Enumerate the (skill, id) work-list
# ---------------------------------------------------------------------------
suites() {
  if [ "$SKILL" = "all" ]; then echo "begin land section factory vibe-diff cross-check spec-viewer preflight"; else echo "$SKILL"; fi
}
ids_for() { # ascending numeric ids present in a suite's case file (cheapest = first = sentinel)
  local s="$1"
  if [ "$EVAL_ID" != "all" ]; then echo "$EVAL_ID"; return; fi
  python3 - "$REPO/evals/cases/$s.json" "$s" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); s=sys.argv[2]
ids=sorted(int(e["fixture"].split("/")[1]) for e in d["evals"])
print(" ".join(map(str,ids)))
PY
}

# ---------------------------------------------------------------------------
# Per-eval metadata (schema v1 -> skill-creator's eval_metadata.json shape)
# ---------------------------------------------------------------------------
write_metadata() { # <case_json> <suite> <numeric_id> <eval_dir>
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import json,sys
case,suite,idn,E=sys.argv[1],sys.argv[2],int(sys.argv[3]),sys.argv[4]
ev=next(e for e in json.load(open(case))["evals"] if e["fixture"]==f"{suite}/{idn}")
# Numeric eval_id keys the run-dir (eval-N) so skill-creator's viewer/aggregate
# stay happy; the stable kebab id and skill_under_test are carried alongside.
json.dump({"eval_id":idn,"eval_name":ev["eval_id"],
           "skill_under_test":ev.get("skill_under_test",suite),
           "prompt":ev["prompt"],"expected_output":ev["expected_output"],
           "assertions":[x["text"] for x in ev["expectations"]]},
          open(f"{E}/eval_metadata.json","w"),indent=2)
PY
}

sut_for() { # skill_under_test for (case, numeric id); defaults to the suite
  python3 - "$1" "$2" "$3" <<'PY'
import json,sys
case,suite,idn=sys.argv[1],sys.argv[2],int(sys.argv[3])
ev=next(e for e in json.load(open(case))["evals"] if e["fixture"]==f"{suite}/{idn}")
print(ev.get("skill_under_test",suite))
PY
}
prompt_for() {
  python3 - "$1" "$2" "$3" <<'PY'
import json,sys
case,suite,idn=sys.argv[1],sys.argv[2],int(sys.argv[3])
ev=next(e for e in json.load(open(case))["evals"] if e["fixture"]==f"{suite}/{idn}")
sys.stdout.write(ev["prompt"])
PY
}
arms_for() {
  python3 - "$1" "$2" "$3" <<'PY'
import json,sys
case,suite,idn=sys.argv[1],sys.argv[2],int(sys.argv[3])
ev=next(e for e in json.load(open(case))["evals"] if e["fixture"]==f"{suite}/{idn}")
print(" ".join(ev["arms"]))
PY
}

# ---------------------------------------------------------------------------
# The executor ground rules (single source: EVALUATION.md). Extract the blockquote.
# ---------------------------------------------------------------------------
ground_rules() {
  python3 - "$REPO/evals/EVALUATION.md" <<'PY'
import re,sys
md=open(sys.argv[1]).read()
# Heading-level agnostic: the 2026-07-19 EVALUATION.md rewrite demoted this
# section from H2 to H3 and the old H2-anchored pattern silently extracted
# nothing from then on. Match any heading level and stop at the next heading
# (or end of file); the blockquote body never contains '#'-prefixed lines.
m=re.search(r"#{2,6} Executor ground rules\n(.*?)(?=\n#{1,6} |\Z)",md,re.S)
body=m.group(1) if m else ""
# strip the leading "> " quote markers
print("\n".join(re.sub(r"^> ?","",l) for l in body.splitlines() if l.startswith(">") or not l.strip()))
PY
}
GROUND_RULES="$(ground_rules)"
[ -n "$(echo "$GROUND_RULES" | tr -d '[:space:]')" ] \
  || die "extracted empty executor ground rules from EVALUATION.md (heading moved again?)"

# ---------------------------------------------------------------------------
# Run one arm: build sandbox, run the executor, snapshot git state
# ---------------------------------------------------------------------------
run_arm() { # <run_dir> <suite> <numeric_id> <arm> <sut> <task_prompt>
  local RUN="$1" suite="$2" idn="$3" arm="$4" sut="$5" task="$6"
  local SB="$RUN/sandbox" OUT="$RUN/outputs"
  # A rerun reuses the same run-N dir, so start the outputs folder empty: an
  # executor that finds a prior run's reports there has to decide what to do
  # with them, which is behavior the eval never asked for (observed 2026-11-26:
  # land/2 moved the stale reports into outputs/previous/ before writing).
  rm -rf "$OUT"
  mkdir -p "$OUT"
  bash "$BUILD" "$suite" "$idn" "$SB" >/dev/null

  # Precondition: every tool the fixture's quality gate invokes must exist on
  # this machine. A skill-following run blocks at a gate it cannot run, and
  # that block reads as a regression in the scores (observed 2026-11-26: a
  # machine without pytest turned section/1 and land/2 red for both arms).
  if [ -f "$SB/Makefile" ]; then
    local gate_tool
    for gate_tool in $(awk '/^\t/ {print $1}' "$SB/Makefile" | sort -u); do
      gate_tool="${gate_tool#@}"
      command -v "$gate_tool" >/dev/null 2>&1 \
        || die "fixture $suite/$idn gates on '$gate_tool', which is not on PATH; install it first (a missing gate tool invalidates the run)."
    done
  fi

  # Compose the executor prompt: ground rules + sandbox/outputs paths + task,
  # and (with_skill only) the explicit SKILL.md path. The skill is NEVER
  # auto-installed: safe mode strips ambient auto-load, so the with_skill arm
  # simply reads the SKILL.md the prompt points it at (EVALUATION.md "Safe mode
  # is load-bearing"). That is the whole install mechanism.
  local skill_line=""
  if [ "$arm" = "with_skill" ]; then
    skill_line="SKILL UNDER TEST: read and follow $REPO/skills/$sut/SKILL.md exactly, resolving any <skill-base> references against $REPO/skills/$sut ."
  else
    skill_line="No skill is named for this run; use your own best judgment (baseline)."
  fi
  local prompt
  prompt="$(cat <<EOF
$GROUND_RULES

SANDBOX (your working directory): $SB
OUTPUTS DIR (write transcript.md / result.md / PR_BODY.md here): $OUT
$skill_line

## Eval Prompt

$task
EOF
)"

  if [ "${RUN_EVAL_DRY:-0}" = "1" ]; then
    # Offline plumbing test: no subscription run. Emit stub outputs so grading,
    # aggregation, and the viewer can be exercised end to end.
    printf '## Eval Prompt\n\n%s\n\n## (dry run, no executor invoked)\n' "$task" > "$OUT/transcript.md"
    printf '(dry run: %s / %s / %s -- no executor output)\n' "$suite" "$idn" "$arm" > "$OUT/result.md"
    printf '{"arm_rc":0,"stderr_scan":"dry","stderr_bytes":0,"model":"%s"}\n' "$MODEL" > "$RUN/exec.json"
    note "DRY $suite/$idn $arm -> stub outputs"
  elif [ "$EXECUTOR" = "codex" ]; then
    # Codex executor arm: `codex exec` non-interactive in the MAIN loop, ChatGPT
    # subscription only (OPENAI_API_KEY guarded away above), hermetic
    # (--ignore-user-config keeps auth but drops user config/hooks), and
    # approvals+sandbox bypassed to mirror the claude arm's
    # --dangerously-skip-permissions. `< /dev/null` for the same reason as the
    # claude arm: codex exec appends piped stdin to the prompt.
    local err_log="$RUN/codex.stderr" json_log="$RUN/codex.stream.json"
    set +e
    ( cd "$SB" && env -u OPENAI_API_KEY -u OPENAI_BASE_URL -u CLAUDECODE \
        codex exec --skip-git-repo-check --ignore-user-config \
               --dangerously-bypass-approvals-and-sandbox \
               -C "$SB" -m "$MODEL" --json -o "$RUN/last_message.txt" \
               "$prompt" >"$json_log" 2>"$err_log" </dev/null )
    local rc=$?
    set -e
    # Same two-layer limit detection as the claude arm: stderr keyword scan first,
    # then a proper JSON parse of the event stream (never grep the JSON body --
    # token counts like "input_tokens":14429 would false-positive on 429). Codex
    # has no rate_limit_event type; limit/auth failures surface as `error` or
    # `turn.failed` events, so match limit keywords inside those events only.
    local scan="clean"
    if grep -qiE '(rate.?limit|usage limit|quota|unauthor)|\b(401|429)\b' "$err_log"; then scan="flagged"; fi
    if [ "$scan" = "clean" ]; then
      set +e
      local lim_msg
      lim_msg="$(python3 - "$json_log" <<'PY'
import json,re,sys
pat=re.compile(r"rate.?limit|usage limit|\b401\b|\b429\b|quota|unauthor",re.I)
for line in open(sys.argv[1],encoding="utf-8",errors="replace"):
    line=line.strip()
    if not line: continue
    try: o=json.loads(line)
    except Exception: continue
    blob=None
    if o.get("type") in ("error","turn.failed"):
        blob=json.dumps(o)
    elif o.get("type")=="item.completed" and isinstance(o.get("item"),dict) and o["item"].get("type")=="error":
        blob=json.dumps(o["item"])
    if blob and pat.search(blob):
        print(blob[:200]); sys.exit(0)
sys.exit(1)
PY
)"
      local wrc=$?
      set -e
      [ $wrc -eq 0 ] && { scan="flagged"; note "stream limit/auth event: $lim_msg"; }
    fi
    printf '{"arm_rc":%d,"stderr_scan":"%s","stderr_bytes":%s,"model":"%s","executor":"codex"}\n' \
      "$rc" "$scan" "$(wc -c <"$err_log" | tr -d ' ')" "$MODEL" > "$RUN/exec.json"
    if [ $rc -ne 0 ] || [ "$scan" = "flagged" ]; then
      echo "----- codex stderr -----" >&2; tail -20 "$err_log" >&2
      die "executor stopped ($suite/$idn $arm, rc=$rc, scan=$scan): auth/limit/other. NOT retrying (execution discipline)."
    fi
    # Rebuild result.md / transcript.md unconditionally via the shared
    # reconstructor, which also harvests child session rollouts: codex's
    # --json stream never surfaces a spawn, so dispatch evidence exists only
    # in $CODEX_HOME/sessions and must be folded into the transcript here.
    python3 "$HARNESS_DIR/codex_transcript.py" "$RUN" >/dev/null
    [ -f "$OUT/result.md" ] || note "warning: $suite/$idn $arm produced no result.md (stream had no agent_message)"
    note "ran $suite/$idn $arm via codex (rc=0, stderr $scan)"
  else
    # Nested `claude -p` in the MAIN loop (never a subagent). Subscription only,
    # locked to the cheap tier, offline. `< /dev/null` so the prompt heredoc
    # cannot swallow a surrounding loop's stdin.
    local err_log="$RUN/claude.stderr" json_log="$RUN/claude.stream.json"
    set +e
    ( cd "$SB" && env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_BASE_URL -u CLAUDECODE \
        claude --safe-mode --dangerously-skip-permissions --model "$MODEL" \
               --output-format stream-json --verbose -p "$prompt" \
               >"$json_log" 2>"$err_log" </dev/null )
    local rc=$?
    set -e
    # Scan stderr for auth/limit (never grep the JSON body -- "duration_ms":102429
    # false-positives on 429). Residual gap: a mid-stream usage-limit delivered as
    # a JSON error event on stdout with rc=0 would slip past both this scan and the
    # rc check; the rc check is the primary defense and serial execution bounds the
    # blast radius to one extra run, so we accept it rather than parse the JSON.
    local scan="clean"
    if grep -qiE '(rate.?limit|usage limit|quota|unauthor)|\b(401|429)\b' "$err_log"; then scan="flagged"; fi
    # Close the documented residual gap: a usage-limit can arrive as a stream
    # event on stdout (rc stays 0), which the stderr scan never sees. Parse the
    # JSON properly (not grep, so "duration_ms":102429 cannot false-positive).
    # A *blocking* status (anything not starting "allowed") is a hard limit ->
    # flag + stop-loss. "allowed_warning" (e.g. 90% of the window used) is NOT a
    # block: the run succeeded, so only note it and keep going. Exit codes:
    # 0 = hard limit, 2 = soft warning, 1 = clean.
    if [ "$scan" = "clean" ]; then
      set +e
      local lim_msg
      lim_msg="$(python3 - "$json_log" <<'PY'
import json,sys
hard=None; warn=None
for line in open(sys.argv[1],encoding="utf-8",errors="replace"):
    line=line.strip()
    if not line: continue
    try: o=json.loads(line)
    except Exception: continue
    if o.get("type")=="rate_limit_event":
        info=o.get("rate_limit_info",{}) or {}
        st=info.get("status")
        if st and not str(st).startswith("allowed"):
            hard=st; break
        if st=="allowed_warning":
            warn=info.get("utilization")
if hard is not None: print("hard-limit status=%s"%hard); sys.exit(0)
if warn is not None: print("utilization=%s"%warn); sys.exit(2)
sys.exit(1)
PY
)"
      local wrc=$?
      set -e
      if   [ $wrc -eq 0 ]; then scan="flagged"; note "stream limit event: $lim_msg"
      elif [ $wrc -eq 2 ]; then note "usage warning ($lim_msg); window near cap, continuing"; fi
    fi
    # Record the per-arm execution outcome so the discipline claim (subscription
    # only, clean rc, no limit signal) is post-hoc verifiable from the harvested
    # fingerprint. Written BEFORE the stop-loss, so a tripped run still leaves it.
    printf '{"arm_rc":%d,"stderr_scan":"%s","stderr_bytes":%s,"model":"%s"}\n' \
      "$rc" "$scan" "$(wc -c <"$err_log" | tr -d ' ')" "$MODEL" > "$RUN/exec.json"
    # Stop-loss: rc!=0 or a limit signal aborts the whole batch, no retry.
    if [ $rc -ne 0 ] || [ "$scan" = "flagged" ]; then
      echo "----- claude stderr -----" >&2; tail -20 "$err_log" >&2
      die "executor stopped ($suite/$idn $arm, rc=$rc, scan=$scan): auth/limit/other. NOT retrying (execution discipline)."
    fi
    # The executor is asked to write result.md / transcript.md, but a run that
    # stops to ask/block often ends on a reply without writing them (observed on
    # begin/1: correct dirty-tree refusal, no files). claude.stream.json is THIS
    # run's authoritative record, so both artifacts are settled from it here:
    # - transcript.md is rebuilt UNCONDITIONALLY from the ordered assistant text
    #   + tool calls (+ truncated tool results), replacing any narration the
    #   executor wrote: what it did outranks what it says it did.
    # - result.md keeps what the executor wrote and gains the stream's closing
    #   reply under a separator (result_md.py). The ground rules ask for the
    #   full user-facing reply in the file and a 2-3 sentence chat summary, so
    #   replacing the file with the summary graded a pointer to the reply
    #   instead of the reply. Keeping the executor's file is safe because the
    #   outputs folder is emptied at arm start: nothing stale can sit there.
    OUT="$OUT" JSON_LOG="$json_log" HARNESS_DIR="$HARNESS_DIR" python3 - <<'PY'
import json,os,sys
sys.path.insert(0,os.environ["HARNESS_DIR"])
from result_md import write_result
out=os.environ["OUT"]; stream=os.environ["JSON_LOG"]
events=[]
try:
    for line in open(stream,encoding="utf-8",errors="replace"):
        line=line.strip()
        if line:
            try: events.append(json.loads(line))
            except Exception: pass
except OSError:
    events=[]
final=None
for e in events:
    if e.get("type")=="result" and isinstance(e.get("result"),str):
        final=e["result"]
write_result(out,final)
tmd=os.path.join(out,"transcript.md")
parts=["# transcript (reconstructed from claude.stream.json)\n"]
for e in events:
    msg=e.get("message") if isinstance(e.get("message"),dict) else {}
    content=msg.get("content") if isinstance(msg.get("content"),list) else []
    if e.get("type")=="assistant":
        for b in content:
            if b.get("type")=="text":
                t=(b.get("text") or "").strip()
                if t: parts.append(t+"\n")
            elif b.get("type")=="tool_use":
                name=b.get("name"); inp=b.get("input") or {}
                cmd=inp.get("command")
                if cmd:
                    parts.append("```\n$ "+str(cmd)+"\n```\n")
                else:
                    summ=", ".join("%s=%s"%(k,str(v)[:1200]) for k,v in inp.items())
                    parts.append("[tool:%s] %s\n"%(name,summ))
    elif e.get("type")=="user":
        for b in content:
            if b.get("type")=="tool_result":
                c=b.get("content")
                if isinstance(c,list):
                    txt="".join(x.get("text","") for x in c if isinstance(x,dict))
                else:
                    txt=str(c)
                txt=txt.strip()
                if txt: parts.append("```\n"+txt[:2400]+"\n```\n")
open(tmd,"w",encoding="utf-8").write("\n".join(parts))
PY
    [ -f "$OUT/result.md" ] || note "warning: $suite/$idn $arm produced no result.md (no executor-written file and no final result event)"
    note "ran $suite/$idn $arm (rc=0, stderr $scan)"
  fi

  bash "$SNAPSHOT" "$SB" "$OUT" >/dev/null
}

# ---------------------------------------------------------------------------
# Grade one run -> grading.json (check.py if present, else interim path),
# then normalize to the aggregate/viewer contract and stamp the fingerprint.
# ---------------------------------------------------------------------------
grade_run() { # <run_dir> <suite> <numeric_id> <arm> <sut>
  local RUN="$1" suite="$2" idn="$3" arm="$4" sut="$5"

  # The universal checker owns grading for every suite: it interprets each
  # expectation's typed check against the sandbox git tree and the run's own
  # outputs, and defers llm_judged rows (passed:null) for a skill-creator grader
  # pass. Machine checks are decided here.
  [ -f "$CHECK_PY" ] || die "missing $CHECK_PY (the universal checker)"
  python3 "$CHECK_PY" "$RUN" "$REPO/evals/cases/$suite.json" "$suite/$idn" >/dev/null

  # Normalize + fingerprint: guarantee summary.{pass_rate,passed,failed,total}
  # (aggregate_benchmark reads these) and stamp provenance on every grading.json.
  local skill_commit harness_commit checker_sha
  harness_commit="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  skill_commit="$(git -C "$REPO" log -1 --format=%h -- "skills/$sut/" 2>/dev/null || echo unknown)"
  checker_sha="$(shasum -a 256 "$CHECK_PY" | cut -d' ' -f1)"
  python3 - "$RUN/grading.json" "$sut" "$skill_commit" "$harness_commit" "$checker_sha" "$MODEL" "$NRUNS" "$ITER" "$RUN/exec.json" <<'PY'
import json,os,sys,subprocess
p,sut,scommit,hcommit,csha,model,runs,iteration,execp=sys.argv[1:10]
g=json.load(open(p))
ex=g.get("expectations",[])
decided=[e for e in ex if e.get("passed") is not None]
passed=sum(1 for e in decided if e["passed"])
total=len(decided)
g["summary"]={"passed":passed,"failed":total-passed,"total":total,
              "pass_rate":round(passed/total,4) if total else 0.0,
              "assertions_total":len(ex),"undecided":len(ex)-total}
ts=subprocess.run(["date","-u","+%Y-%m-%dT%H:%M:%SZ"],capture_output=True,text=True).stdout.strip()
fp={"checker_sha256":csha,"harness_commit":hcommit,
    "skill_name":sut,"skill_commit":scommit,"iteration":int(iteration),
    "model":model,"runs":int(runs),"timestamp":ts,"environment":"local"}
# Fold the per-arm execution record (rc + stderr auth/limit scan) into the
# fingerprint so "subscription only, clean rc, no limit signal" is auditable
# from the harvested JSON alone, not just from the live log.
if os.path.isfile(execp):
    try: fp["execution"]=json.load(open(execp))
    except Exception: pass
g["fingerprint"]=fp
json.dump(g,open(p,"w"),indent=2)
PY
}

# ---------------------------------------------------------------------------
# Aggregate + viewer (skill-creator) + harvest small JSON home
# ---------------------------------------------------------------------------
finalize_suite() { # <suite> <workspace_iter_dir>
  local suite="$1" WS="$2"
  if [ -n "$AGG" ] && [ -f "$AGG" ]; then
    python3 "$AGG" "$WS" --skill-name "$suite" >/dev/null && note "aggregated -> $WS/benchmark.json"
  else
    note "skill-creator aggregate not found; skipping (set SKILL_CREATOR_DIR)"
  fi
  if [ -n "$VIEWER" ] && [ -f "$VIEWER" ]; then
    python3 "$VIEWER" "$WS" --skill-name "$suite" --static "$WS/review.html" >/dev/null 2>&1 \
      && note "viewer (static) -> $WS/review.html" || true
  fi
  # Harvest: only the small JSON comes home (iron rule 3). Workspaces are gitignored.
  local HOME_DIR="$REPO/evals/results/$suite/iteration-$ITER"
  mkdir -p "$HOME_DIR"
  [ -f "$WS/benchmark.json" ] && cp "$WS/benchmark.json" "$HOME_DIR/benchmark.json"
  local g
  while IFS= read -r g; do
    local rel; rel="${g#"$WS"/}"; rel="${rel//\//_}"
    cp "$g" "$HOME_DIR/$rel"
  done < <(find "$WS" -name grading.json | sort)
  note "harvested small JSON -> $HOME_DIR"
}

# ---------------------------------------------------------------------------
# Main: strictly serial, cheapest eval first
# ---------------------------------------------------------------------------
[ -f "$BUILD" ] || die "missing $BUILD"
note "repo=$REPO  executor=$EXECUTOR  model=$MODEL  runs=$NRUNS  iteration=$ITER  dry=${RUN_EVAL_DRY:-0}"
[ -n "$SC_DIR" ] && note "skill-creator=$SC_DIR" || note "skill-creator=NOT FOUND (aggregate/viewer will be skipped)"

for suite in $(suites); do
  CASE="$REPO/evals/cases/$suite.json"
  [ -f "$CASE" ] || die "no case file: $CASE"
  WS="$REPO/skills/$suite/$suite-workspace/iteration-$ITER"
  first=1
  for idn in $(ids_for "$suite"); do
    E="$WS/eval-$idn"
    mkdir -p "$E"
    write_metadata "$CASE" "$suite" "$idn" "$E"
    sut="$(sut_for "$CASE" "$suite" "$idn")"
    task="$(prompt_for "$CASE" "$suite" "$idn")"
    [ $first -eq 1 ] && { note "sentinel: $suite/$idn (cheapest first)"; first=0; }
    for arm in $(arms_for "$CASE" "$suite" "$idn"); do
      for n in $(seq 1 "$NRUNS"); do
        RUN="$E/$arm/run-$n"
        note "=== $suite/$idn $arm run-$n ==="
        run_arm "$RUN" "$suite" "$idn" "$arm" "$sut" "$task"
        grade_run "$RUN" "$suite" "$idn" "$arm" "$sut"
      done
    done
  done
  finalize_suite "$suite" "$WS"
done
note "---- run_eval complete ----"
