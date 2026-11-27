#!/usr/bin/env python3
"""Write a run's `outputs/result.md` without discarding what the executor wrote.

The executor ground rules ask for two things at once: write the final
user-facing reply to `result.md`, and end the session with a 2-3 sentence
summary. An executor that obeys both puts its full reply (a ledger, a fixed
summary block) in the file and only a pointer to it in the closing chat reply.
Rebuilding `result.md` from the closing reply alone, as the harness used to,
threw the full reply away and graded the pointer (observed 2026-11-27: all 36
runs of one round, with retro/2's fixed summary scored missing while it sat in
the overwritten file).

So both are kept: the executor's own file first, then the closing chat reply
under a separator line. Safe because `run_eval.sh` empties the outputs folder
at arm start, so a `result.md` found here was written by this run.

Imported by `run_eval.sh` (claude arm) and `codex_transcript.py` (codex arm),
so both executors get the same evidence contract.
"""

import os

SEPARATOR = ("--- closing chat reply (appended by the harness; "
             "the text above is the executor's own result.md) ---")


def write_result(out_dir: str, final: "str|None") -> "str|None":
    """Merge the executor-written result.md with the closing reply `final`.

    Returns the path written, or None when there is neither a file nor a reply
    (the caller warns). Idempotent: a second call with the same inputs leaves
    the file byte-for-byte the same.
    """
    rmd = os.path.join(out_dir, "result.md")
    written = ""
    if os.path.exists(rmd):
        written = open(rmd, encoding="utf-8", errors="replace").read()
        # Drop a previous pass's appendix so re-running never stacks it.
        written = written.split(SEPARATOR)[0].strip()
    final = (final or "").strip()
    if not written and not final:
        if os.path.exists(rmd):
            os.remove(rmd)
        return None
    if not written or written == final:
        body = final
    elif not final or final in written:
        body = written
    else:
        body = f"{written}\n\n{SEPARATOR}\n\n{final}"
    open(rmd, "w", encoding="utf-8").write(body + "\n")
    return rmd
