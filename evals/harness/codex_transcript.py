#!/usr/bin/env python3
"""Rebuild a codex arm's outputs (result.md, transcript.md) from its stream,
folding in the dispatch evidence the --json stream cannot show.

codex exec's --json stream records a spawned subagent only as receiverless
collab `wait` items; the spawn itself and everything the child did live
solely in the child's session rollout under $CODEX_HOME/sessions, linked by
`parent_thread_id`. A transcript built from the stream alone is therefore
blind to dispatch (observed: 12 real spawns invisible across a 24-run
round, judged as "no dispatch"), so this script harvests the child rollouts
and appends a dispatch section to the transcript.

Usage: codex_transcript.py <run_dir>
  <run_dir>/codex.stream.json   parent event stream (required)
  <run_dir>/last_message.txt    --output-last-message fallback (optional)
  <run_dir>/outputs/            destination for result.md / transcript.md
Env: CODEX_SESSIONS overrides the sessions root (default ~/.codex/sessions).
"""
import glob
import json
import os
import sys

CAP_OUTPUT = 2400   # command output excerpt
CAP_FIELD = 1200    # tool inputs, prompts, child excerpts


def read_events(path):
    events = []
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    except OSError:
        pass
    return events


def harvest_children(thread_id, sessions_root):
    """Child session rollouts whose session_meta names this thread as parent."""
    children = []
    for sf in sorted(glob.glob(os.path.join(sessions_root, "**", "rollout-*.jsonl"),
                               recursive=True)):
        try:
            with open(sf, encoding="utf-8", errors="replace") as fh:
                meta = json.loads(fh.readline())
        except Exception:
            continue
        payload = meta.get("payload", {}) if isinstance(meta, dict) else {}
        if payload.get("parent_thread_id") != thread_id:
            continue
        spawn = (payload.get("source", {}) or {}).get("subagent", {}).get("thread_spawn", {})
        # The meta names the summoned roster role as `agent_role` (there is no
        # `agent_type` key here); the path basename is the model's task label.
        role = spawn.get("agent_role")
        task = os.path.basename(spawn.get("agent_path") or "") or "?"
        prompt, final = None, None
        try:
            for line in open(sf, encoding="utf-8", errors="replace"):
                try:
                    o = json.loads(line.strip())
                except Exception:
                    continue
                pl = o.get("payload", {}) if isinstance(o, dict) else {}
                if o.get("type") == "response_item" and pl.get("type") == "message":
                    texts = [c.get("text", "") for c in pl.get("content", [])
                             if isinstance(c, dict) and c.get("type") in ("input_text", "output_text")]
                    text = "\n".join(t for t in texts if t)
                    if pl.get("role") == "user" and prompt is None \
                            and not text.lstrip().startswith("<environment_context>"):
                        prompt = text
                    elif pl.get("role") == "assistant" and text:
                        final = text
                elif o.get("type") == "event_msg" and pl.get("type") == "task_complete":
                    final = pl.get("last_agent_message") or final
        except OSError:
            pass
        children.append({"role": role, "task": task, "depth": spawn.get("depth"),
                         "prompt": prompt, "final": final, "file": os.path.basename(sf)})
    return children


def main(run):
    out = os.path.join(run, "outputs")
    os.makedirs(out, exist_ok=True)
    events = read_events(os.path.join(run, "codex.stream.json"))
    items = [e["item"] for e in events
             if e.get("type") == "item.completed" and isinstance(e.get("item"), dict)]
    thread_id = next((e.get("thread_id") for e in events if e.get("type") == "thread.started"), None)

    # result.md: last agent message, falling back to --output-last-message.
    final = None
    for it in items:
        if it.get("type") == "agent_message" and isinstance(it.get("text"), str):
            final = it["text"]
    lastp = os.path.join(run, "last_message.txt")
    if final is None and os.path.exists(lastp):
        t = open(lastp, encoding="utf-8", errors="replace").read().strip()
        final = t or None
    rmd = os.path.join(out, "result.md")
    if final is not None:
        open(rmd, "w", encoding="utf-8").write(final)
    elif os.path.exists(rmd):
        os.remove(rmd)

    parts = ["# transcript (reconstructed from codex.stream.json + session rollouts)\n"]
    for it in items:
        t = it.get("type")
        if t == "agent_message":
            txt = (it.get("text") or "").strip()
            if txt:
                parts.append(txt + "\n")
        elif t == "command_execution":
            parts.append("```\n$ " + str(it.get("command") or "") + "\n```\n")
            outp = (it.get("aggregated_output") or "").strip()
            if outp:
                parts.append("```\n" + outp[:CAP_OUTPUT] + "\n```\n")
        elif t == "collab_tool_call":
            parts.append("[collab:%s] status=%s receivers=%d\n" % (
                it.get("tool"), it.get("status"), len(it.get("receiver_thread_ids") or [])))
            p = it.get("prompt")
            if p:
                parts.append("```\n" + str(p)[:CAP_FIELD] + "\n```\n")
        elif t == "file_change":
            parts.append("[file_change] " + json.dumps(it.get("changes"))[:CAP_FIELD] + "\n")
        elif t == "mcp_tool_call":
            parts.append("[tool:%s] %s\n" % (it.get("tool") or it.get("server"),
                                             str(it.get("arguments"))[:CAP_FIELD]))

    # Dispatch evidence: judges decide "a subagent was dispatched" rows on
    # this section, so it is written even (especially) when empty.
    sessions_root = os.environ.get("CODEX_SESSIONS",
                                   os.path.expanduser("~/.codex/sessions"))
    parts.append("\n## dispatched subagents (harvested from codex session rollouts)\n")
    children = harvest_children(thread_id, sessions_root) if thread_id else []
    if not children:
        parts.append("(none: no child session rollout references this run's thread id)\n")
    for c in children:
        parts.append("[dispatch] spawned subagent: role=%r task=%r (depth %s)\n"
                     % (c["role"], c["task"], c["depth"]))
        if c["prompt"]:
            parts.append("prompt:\n```\n" + c["prompt"][:CAP_FIELD] + "\n```\n")
        if c["final"]:
            parts.append("final report:\n```\n" + c["final"][:CAP_FIELD] + "\n```\n")

    open(os.path.join(out, "transcript.md"), "w", encoding="utf-8").write("\n".join(parts))
    print("rebuilt %s (children: %d)" % (run, len(children)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
