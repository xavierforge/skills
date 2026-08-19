#!/usr/bin/env python3
"""Render a diff-review.html for one OpenSpec change from two inputs.

Deterministic layer (this script): parse a captured unified diff, compute the
diffstat, HTML-escape and embed every hunk under a stable id, cross-link with
the spec-viewer twin's review.html, and lay the page out. Judgment layer (the
authoring model): a diff-review.json holding the prose that explains the diff
(overview, intent map, risks, margin annotations, unverified claims). The
script never invents judgment; the JSON never carries markup or layout.

Usage:
    generate.py <change_dir> [--diff PATH] [--review PATH] [--out PATH]
                [--base NAME] [--branch NAME]

Defaults, all inside the change directory: diff.patch, diff-review.json,
diff-review.html. Capture the diff first, e.g.:

    git diff --no-color -M <base>...HEAD > <change_dir>/diff.patch

Two-pass flow, like the spec-viewer gloss: run once without the JSON to get
the hunk ids and spec section ids printed (the authoring contract), write
diff-review.json keyed on them, run again.

Margin annotations anchor by line content, not line number: each annotation
names a substring that must match exactly one line in its hunk. Zero or many
matches are reported and the note is rendered as unplaced, never dropped.

python3 stdlib only, no external requests.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Inline mini-markdown for judgment prose: **bold** and `code` over escaped
# text (same subset as the spec-viewer twin).
# --------------------------------------------------------------------------

def render_inline(text):
    escaped = html.escape(text, quote=False)
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return "\x00%d\x00" % (len(codes) - 1)

    escaped = re.sub(r"`([^`]+)`", stash, escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\x00(\d+)\x00",
                     lambda m: "<code>%s</code>" % codes[int(m.group(1))],
                     escaped)
    return escaped


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "file"


# --------------------------------------------------------------------------
# Unified diff parser: files -> hunks, plus per-file add/del counts.
# --------------------------------------------------------------------------

_DIFF_GIT_RE = re.compile(r'^diff --git (?:"?a/(.+?)"?) (?:"?b/(.+?)"?)$')
_HUNK_RE = re.compile(r"^@@ .* @@")
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testdata|fixtures)(/|$)"
    r"|_test\.|\.test\.|\.spec\.|_spec\.|^conftest\.py$")


def parse_diff(text):
    """Return a list of file dicts:
    {path, old_path, status, binary, adds, dels, hunks: [{id assigned later,
     header, lines: [(kind, text)]}]}  kind in ' ', '+', '-', '\\'."""
    files, cur, cur_hunk = [], None, None
    for raw in text.replace("\r\n", "\n").split("\n"):
        m = _DIFF_GIT_RE.match(raw)
        if m:
            cur = {"path": m.group(2), "old_path": m.group(1),
                   "status": "modified", "binary": False,
                   "adds": 0, "dels": 0, "hunks": []}
            files.append(cur)
            cur_hunk = None
            continue
        if cur is None:
            continue
        if _HUNK_RE.match(raw):
            cur_hunk = {"header": raw, "lines": []}
            cur["hunks"].append(cur_hunk)
            continue
        if cur_hunk is None:
            if raw.startswith("new file mode"):
                cur["status"] = "new"
            elif raw.startswith("deleted file mode"):
                cur["status"] = "deleted"
            elif raw.startswith("rename from "):
                cur["old_path"] = raw[len("rename from "):]
                cur["status"] = "renamed"
            elif raw.startswith("rename to "):
                cur["path"] = raw[len("rename to "):]
            elif raw.startswith("Binary files "):
                cur["binary"] = True
            continue
        if raw.startswith("+"):
            cur["adds"] += 1
            cur_hunk["lines"].append(("+", raw[1:]))
        elif raw.startswith("-"):
            cur["dels"] += 1
            cur_hunk["lines"].append(("-", raw[1:]))
        elif raw.startswith(" ") or raw == "":
            cur_hunk["lines"].append((" ", raw[1:] if raw else ""))
        elif raw.startswith("\\"):
            cur_hunk["lines"].append(("\\", raw))
        else:
            # a line that belongs to the next file's headers (e.g. between
            # hunks and the next diff --git); close the hunk
            cur_hunk = None
    # stable hunk ids: hunk-<path-slug>[-<n>], de-duped when two paths slugify
    # to the same stem
    seen = set()
    for f in files:
        base = "hunk-%s" % slugify(f["path"])
        stem, k = base, 2
        while stem in seen:
            stem, k = "%s-%d" % (base, k), k + 1
        seen.add(stem)
        f["idstem"] = stem
        for n, h in enumerate(f["hunks"], 1):
            h["id"] = stem if len(f["hunks"]) == 1 else "%s-%d" % (stem, n)
    return files


def is_test_path(path):
    return bool(_TEST_PATH_RE.search(path))


# --------------------------------------------------------------------------
# Diffstat block: totals, test share, per-file table with proportional bars.
# --------------------------------------------------------------------------

def render_diffstat(files):
    total_a = sum(f["adds"] for f in files)
    total_d = sum(f["dels"] for f in files)
    test_a = sum(f["adds"] for f in files if is_test_path(f["path"]))
    peak = max((f["adds"] + f["dels"] for f in files), default=1) or 1

    out = ['<div class="diffstat">']
    out.append('<p class="stat-total"><strong>%d files</strong>, '
               '<span class="plus">+%d</span> <span class="minus">&minus;%d</span>'
               % (len(files), total_a, total_d))
    if total_a:
        share = round(100 * test_a / total_a)
        out.append(' &middot; %d%% of added lines are in test files' % share)
    out.append('</p>')
    out.append('<div class="stat-scroll"><table class="stat"><tbody>')
    for f in sorted(files, key=lambda f: -(f["adds"] + f["dels"])):
        label = f["path"]
        if f["status"] == "renamed":
            label = "%s → %s" % (f["old_path"], f["path"])
        badge = ""
        if f["status"] in ("new", "deleted"):
            badge = ' <span class="fbadge">%s</span>' % f["status"]
        if is_test_path(f["path"]):
            badge += ' <span class="fbadge test">test</span>'
        if f["binary"]:
            cells = '<td class="num" colspan="2">binary</td><td></td>'
        else:
            aw = round(120 * f["adds"] / peak)
            dw = round(120 * f["dels"] / peak)
            cells = ('<td class="num plus">+%d</td>'
                     '<td class="num minus">&minus;%d</td>'
                     '<td class="bar"><span class="b-add" style="width:%dpx"></span>'
                     '<span class="b-del" style="width:%dpx"></span></td>'
                     % (f["adds"], f["dels"], aw, dw))
        target = f["hunks"][0]["id"] if f["hunks"] else ""
        name = html.escape(label)
        if target:
            name = '<a href="#%s">%s</a>' % (target, name)
        out.append('<tr><td class="fname">%s%s</td>%s</tr>' % (name, badge, cells))
    out.append('</tbody></table></div></div>')
    return "".join(out)


# --------------------------------------------------------------------------
# Hunk rendering: every line is escaped text in an element body. Annotated
# hunks are a two-column grid (code row, margin note); plain hunks omit the
# note column entirely.
# --------------------------------------------------------------------------

_KIND_CLASS = {"+": "add", "-": "del", " ": "", "\\": "meta"}


def render_hunk(hunk, notes=None, warnings=None):
    """notes: {line_index: note_html}; lines with a note are highlighted."""
    notes, warnings = notes or {}, warnings or []
    annotated = bool(notes) or bool(warnings)
    cls = "hunk annotated" if annotated else "hunk"
    out = ['<div class="%s" id="%s">' % (cls, hunk["id"])]

    def row(code_html, note_html):
        out.append(code_html)
        if annotated:
            out.append('<div class="mn">%s</div>' % note_html)

    row('<div class="dl hunkhead">%s</div>' % html.escape(hunk["header"]), "")
    for i, (kind, text) in enumerate(hunk["lines"]):
        klass = _KIND_CLASS[kind]
        hl = " hl" if i in notes else ""
        prefix = kind if kind != "\\" else ""
        row('<div class="dl %s%s">%s</div>'
            % (klass, hl, html.escape(prefix + text) or "&nbsp;"),
            notes.get(i, ""))
    for w in warnings:
        row('<div class="dl unplaced">⚠ unplaced note</div>', w)
    out.append('</div>')
    return "".join(out)


def place_annotations(hunk, annotations, report):
    """Map annotations to line indexes by content substring; exactly one
    match places the note, otherwise it is reported and rendered unplaced."""
    notes, warnings = {}, []
    for ann in annotations:
        needle, note = ann.get("match", ""), ann.get("note", "")
        hits = [i for i, (kind, text) in enumerate(hunk["lines"])
                if needle and needle in text]
        if len(hits) == 1:
            notes[hits[0]] = render_inline(note)
        else:
            why = "no line matches" if not hits else "%d lines match" % len(hits)
            report.append("annotation %r on %s: %s" % (needle, hunk["id"], why))
            warnings.append("%s (match: <code>%s</code>)"
                            % (render_inline(note), html.escape(needle)))
    return notes, warnings


# --------------------------------------------------------------------------
# Page shell.
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#fbfaf7;--fg:#23201b;--muted:#6b6459;--rule:#e4ded3;--card:#fff;
--accent:#8a5a2b;--req:#b45309;--add:#116329;--addbg:#e6f4ea;--del:#a12622;
--delbg:#fbeaea;--hl:#fff3cf;--hlline:#d9a066;--code:#f0ece3;--navbg:#f4f1ea;
--risk:#a12622;--unv:#7c3aed;}
@media (prefers-color-scheme:dark){:root{--bg:#181614;--fg:#e9e4da;
--muted:#a49b8c;--rule:#332f29;--card:#211e1b;--accent:#d9a066;--req:#f0a95a;
--add:#8bd08b;--addbg:#12261a;--del:#e07a76;--delbg:#2e1a19;--hl:#33290f;
--hlline:#d9a066;--code:#2a2723;--navbg:#1f1c19;--risk:#e07a76;--unv:#c4a7f0;}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
code{background:var(--code);padding:.1em .35em;border-radius:4px;
font:.85em/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
.topbar{position:sticky;top:0;z-index:5;background:var(--navbg);
border-bottom:1px solid var(--rule);padding:.7rem 1.2rem;display:flex;
flex-wrap:wrap;gap:.6rem 1rem;align-items:baseline;}
.topbar h1{margin:0;font-size:1.05rem;font-weight:700}
.topbar .sub{color:var(--muted);font-size:.85rem}
.topbar a{margin-left:auto;font-size:.8rem;color:var(--accent);
text-decoration:none;border:1px solid var(--rule);border-radius:6px;
padding:.1em .55em;white-space:nowrap}
.topbar a:hover{background:var(--card)}
main{max-width:1120px;margin:0 auto;padding:1.4rem clamp(1rem,4vw,3rem) 6rem}
h2{font-size:1.25rem;margin:2.2rem 0 .6rem;border-bottom:2px solid var(--rule);
padding-bottom:.25rem;scroll-margin-top:70px}
h3{font-size:1rem;margin:1.3rem 0 .4rem}
.meta{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;
font-size:.85rem;color:var(--muted);margin:.4rem 0 1rem}
.pill{display:inline-block;font-size:.7rem;font-weight:700;border-radius:20px;
padding:.15em .6em;color:#fff}
.pill.pass{background:var(--add)}
.pill.fail{background:var(--del)}
.pill.creep{background:var(--del)}
.pill.gap{background:var(--unv)}
.card{background:var(--card);border:1px solid var(--rule);border-radius:10px;
padding:.9rem 1.1rem;margin:.8rem 0}
.imap{border-left:3px solid var(--req);scroll-margin-top:70px}
.imap h3{margin:.1rem 0 .3rem}
.imap h3 a{color:inherit;text-decoration:none}
.imap h3 a:hover{text-decoration:underline}
.imap .spec-link{font-size:.72rem;font-weight:600;color:var(--accent);
text-decoration:none;margin-left:.5em}
.imap ul{margin:.3rem 0;padding-left:1.3rem}
.imap li{margin:.2rem 0}
a.hunk-ref{color:var(--accent)}
.risk{border-left:3px solid var(--risk)}
.unverified{border:2px dashed var(--unv)}
.unverified .tag{color:var(--unv);font-weight:800;font-size:.75rem;
letter-spacing:.08em}
.lede{margin:.5rem 0 .6rem}
.diffstat{margin:.6rem 0 1rem}
.stat-total{margin:.3rem 0 .5rem}
.plus{color:var(--add);font-weight:650}
.minus{color:var(--del);font-weight:650}
.stat-scroll{overflow-x:auto}
table.stat{border-collapse:collapse;font-size:.82rem;min-width:520px}
table.stat td{padding:.14rem .6rem .14rem 0;vertical-align:baseline}
td.fname{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-size:.78rem;max-width:430px;overflow:hidden;text-overflow:ellipsis;
white-space:nowrap}
td.fname a{color:inherit}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.bar{white-space:nowrap}
td.bar span{display:inline-block;height:.6em}
.b-add{background:var(--add)}
.b-del{background:var(--del)}
.fbadge{display:inline-block;font-size:.62rem;font-weight:700;
text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
border:1px solid var(--rule);border-radius:4px;padding:0 .35em;
vertical-align:.1em}
.fbadge.test{color:var(--accent);border-color:var(--accent)}
.hunk{background:var(--code);border:1px solid var(--rule);border-radius:8px;
padding:.6rem .8rem;overflow-x:auto;scroll-margin-top:70px;margin:.6rem 0}
.hunk.annotated{display:grid;grid-template-columns:minmax(0,1fr) 300px;
gap:0 1rem}
.hunk .dl{font:.8rem/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
white-space:pre;min-width:0}
.hunk .dl.add{color:var(--add);background:var(--addbg)}
.hunk .dl.del{color:var(--del);background:var(--delbg)}
.hunk .dl.hl{box-shadow:inset 3px 0 0 var(--hlline);background:var(--hl)}
.hunk .dl.hunkhead,.hunk .dl.meta{color:var(--muted)}
.hunk .dl.unplaced{color:var(--unv)}
.hunk .mn{font-size:.78rem;line-height:1.45;color:var(--muted);
border-left:2px solid var(--hlline);padding:.1rem 0 .3rem .6rem;margin:.05rem 0}
.hunk .mn:empty{border-left:none;padding:0;margin:0}
.filehead{font:.78rem ui-monospace,Menlo,Consolas,monospace;color:var(--muted);
margin:1rem 0 .3rem}
details.file{margin:.5rem 0}
details.file>summary{cursor:pointer;
font:.82rem ui-monospace,Menlo,Consolas,monospace;color:var(--muted)}
details.file>summary .plus,details.file>summary .minus{font-size:.78rem}
@media (max-width:760px){.hunk.annotated{grid-template-columns:1fr}
.hunk .mn{border-left:none;border-top:1px dashed var(--rule);
padding:.25rem 0 .5rem;margin:0 0 .3rem}}
"""

JS = """
(function(){
// anchor navigation into a closed <details>: open every <details> ancestor
function reveal(){
var id=location.hash.slice(1);if(!id)return;
var el=document.getElementById(id);if(!el)return;
for(var p=el;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true;}
el.scrollIntoView();
}
window.addEventListener('hashchange',reveal);
reveal();
})();
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>diff review: __TITLE__</title>
<style>__CSS__</style>
</head>
<body>
<div class="topbar">
<h1>__TITLE__</h1>
<span class="sub">diff review__SUB__</span>
__SPECLINK__
</div>
<main>
__BODY__
</main>
<script>__JS__</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Sections from the judgment JSON.
# --------------------------------------------------------------------------

def render_test_meta(status, unverified_bucket):
    if not isinstance(status, dict) or not status:
        unverified_bucket.append(
            "Test status was not provided; treat the diff as unverified.")
        return '<div class="meta"><span class="pill fail">tests: unknown</span>' \
               '<span>no test run recorded, see UNVERIFIED</span></div>'
    if "unobtainable" in status:
        unverified_bucket.append(
            "Test status unobtainable: %s" % status["unobtainable"])
        return '<div class="meta"><span class="pill fail">tests: unobtainable</span>' \
               '<span>%s</span></div>' % render_inline(status["unobtainable"])
    ok = str(status.get("result", "")).lower().startswith("pass")
    pill = "pass" if ok else "fail"
    label = html.escape(status.get("result", "unknown"))
    detail = "<code>%s</code>, %s" % (
        html.escape(status.get("command", "?")),
        render_inline(status.get("when", "")))
    return ('<div class="meta"><span class="pill %s">tests: %s</span>'
            '<span>%s</span></div>' % (pill, label, detail))


def spec_section_ids(change):
    page = change / "review.html"
    if not page.is_file():
        return None
    return set(re.findall(r'<section id="([^"]+)"',
                          page.read_text(encoding="utf-8")))


def render_intent_map(entries, hunk_ids, spec_ids, report):
    out = []
    for e in entries:
        rid = e.get("id", "")
        title = render_inline(e.get("title", rid))
        if spec_ids is not None and rid and rid not in spec_ids:
            report.append("intent-map id %r not found in review.html" % rid)
        head = title
        if spec_ids is not None and rid in (spec_ids or set()):
            head = ('<a href="review.html#%s">%s</a>'
                    '<a class="spec-link" href="review.html#%s">spec ↗</a>'
                    % (rid, title, rid))
        out.append('<div class="card imap" id="%s"><h3>%s</h3><ul>'
                   % (html.escape(rid), head))
        for item in e.get("items", []):
            refs = []
            for hid in item.get("hunks", []):
                if hid not in hunk_ids:
                    report.append("intent-map hunk id %r does not exist" % hid)
                    continue
                refs.append('<a class="hunk-ref" href="#%s">%s</a>'
                            % (hid, html.escape(hid)))
            suffix = (" &middot; " + ", ".join(refs)) if refs else ""
            out.append("<li>%s%s</li>" % (render_inline(item.get("text", "")), suffix))
        if e.get("gap"):
            out.append('<li><span class="pill gap">gap</span> %s</li>'
                       % render_inline(e["gap"]))
        out.append("</ul></div>")
    return "".join(out)


def render_list_card(items, extra_class=""):
    out = ['<div class="card %s"><ul>' % extra_class]
    out += ["<li>%s</li>" % render_inline(i) for i in items]
    out.append("</ul></div>")
    return "".join(out)


# --------------------------------------------------------------------------

def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Render diff-review.html for an OpenSpec change.")
    ap.add_argument("change_dir", help="path to openspec/changes/<name>/")
    ap.add_argument("--diff", help="captured unified diff (default: <change>/diff.patch)")
    ap.add_argument("--review", help="judgment JSON (default: <change>/diff-review.json)")
    ap.add_argument("--out", help="output HTML (default: <change>/diff-review.html)")
    ap.add_argument("--base", default="", help="base ref name, shown in the header")
    ap.add_argument("--branch", default="", help="branch name, shown in the header")
    args = ap.parse_args(argv)

    change = Path(args.change_dir)
    if not change.is_dir():
        print("error: not a directory: %s" % change, file=sys.stderr)
        return 2

    diff_path = Path(args.diff) if args.diff else change / "diff.patch"
    if not diff_path.is_file():
        print("error: no diff at %s\ncapture it first, e.g.:\n"
              "  git diff --no-color -M <base>...HEAD > %s"
              % (diff_path, diff_path), file=sys.stderr)
        return 2
    files = parse_diff(diff_path.read_text(encoding="utf-8-sig", errors="replace"))
    if not files:
        print("error: %s contains no file diffs" % diff_path, file=sys.stderr)
        return 2

    review_path = Path(args.review) if args.review else change / "diff-review.json"
    review = {}
    if review_path.is_file():
        try:
            review = json.loads(review_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            print("error: could not read %s: %s" % (review_path, exc), file=sys.stderr)
            return 2
        if not isinstance(review, dict):
            print("error: %s must be a JSON object" % review_path, file=sys.stderr)
            return 2

    hunk_ids = {h["id"] for f in files for h in f["hunks"]}
    spec_ids = spec_section_ids(change)
    report, unverified = [], []
    body = []

    # Overview: test status, diffstat, prose, scope creep.
    body.append('<h2 id="overview">Overview</h2>')
    body.append(render_test_meta(review.get("test_status"), unverified))
    body.append(render_diffstat(files))
    for para in review.get("overview", []):
        body.append("<p>%s</p>" % render_inline(para))
    for creep in review.get("scope_creep", []):
        body.append('<p><span class="pill creep">not in spec</span> %s</p>'
                    % render_inline(creep))
    if not review:
        body.append('<p><em>Judgment layer not authored yet: run the skill\'s '
                    'Step 3 to write diff-review.json, then re-run this '
                    'script.</em></p>')

    if review.get("intent_map"):
        body.append('<h2 id="intent-map">Intent map</h2>')
        body.append(render_intent_map(review["intent_map"], hunk_ids,
                                      spec_ids, report))

    if review.get("risks"):
        body.append('<h2 id="risk">Behavior changes and risk flags</h2>')
        body.append(render_list_card(review["risks"], "risk"))

    # Hotspots: annotated hunks. Hunks shown here are omitted from the
    # remaining-hunks section.
    shown = set()
    hotspots = review.get("hotspots", [])
    if hotspots:
        body.append('<h2 id="hotspots">Reviewer hotspots</h2>')
        by_id = {h["id"]: h for f in files for h in f["hunks"]}
        for spot in hotspots:
            hid = spot.get("hunk", "")
            hunk = by_id.get(hid)
            body.append('<h3 id="hotspot-%s">%s</h3>'
                        % (slugify(spot.get("title", hid)),
                           render_inline(spot.get("title", hid))))
            if spot.get("lede"):
                body.append('<p class="lede">%s</p>' % render_inline(spot["lede"]))
            if hunk is None:
                report.append("hotspot hunk id %r does not exist" % hid)
                body.append('<p><em>hunk %s not found in the diff</em></p>'
                            % html.escape(hid))
                continue
            notes, warns = place_annotations(hunk, spot.get("annotations", []),
                                             report)
            body.append(render_hunk(hunk, notes, warns))
            shown.add(hid)

    # Remaining hunks, grouped per file in a collapsible block.
    rest = [f for f in files if any(h["id"] not in shown for h in f["hunks"])
            or f["binary"]]
    if rest:
        body.append('<h2 id="hunks">%s</h2>'
                    % ("Remaining hunks" if shown else "All hunks"))
        for f in rest:
            label = f["path"] if f["status"] != "renamed" \
                else "%s → %s" % (f["old_path"], f["path"])
            summary = ('%s <span class="plus">+%d</span> '
                       '<span class="minus">&minus;%d</span>'
                       % (html.escape(label), f["adds"], f["dels"]))
            body.append('<details class="file"><summary>%s</summary>' % summary)
            if f["binary"]:
                body.append("<p><em>binary file</em></p>")
            for h in f["hunks"]:
                if h["id"] not in shown:
                    body.append(render_hunk(h))
            body.append("</details>")

    if review.get("unverified") or unverified:
        body.append('<h2 id="unverified">UNVERIFIED</h2>')
        items = unverified + list(review.get("unverified", []))
        body.append('<div class="card unverified"><p><span class="tag">'
                    'UNVERIFIED</span> Beliefs without a hunk to anchor to; '
                    'treat as leads, not facts.</p><ul>%s</ul></div>'
                    % "".join("<li>%s</li>" % render_inline(i) for i in items))

    sub = ""
    if args.branch or args.base:
        sub = " &middot; %s vs %s (merge-base)" % (
            html.escape(args.branch or "HEAD"), html.escape(args.base or "?"))
    spec_link = '<a href="review.html">spec page ↗</a>' if spec_ids is not None else ""
    name = change.name
    page = (PAGE
            .replace("__CSS__", CSS)
            .replace("__JS__", JS)
            .replace("__SUB__", sub)
            .replace("__SPECLINK__", spec_link)
            .replace("__TITLE__", html.escape(name))
            .replace("__BODY__", "\n".join(body)))

    out_path = Path(args.out) if args.out else change / "diff-review.html"
    out_path.write_text(page, encoding="utf-8")

    # stdout: the authoring contract, then problems.
    print("wrote %s (%d files, %d hunks)" % (out_path, len(files), len(hunk_ids)))
    print("review json: %s" % (review_path if review else
                               "none (looked for %s)" % review_path))
    print("spec page: %s" % ("review.html found, %d section ids" % len(spec_ids)
                             if spec_ids is not None else
                             "none (run spec-viewer first for cross-links)"))
    print("hunk ids:")
    for f in files:
        for h in f["hunks"]:
            print("  %s  %s" % (h["id"], h["header"][:70]))
    if spec_ids:
        print("spec section ids (requirements only):")
        for sid in sorted(s for s in spec_ids if "--requirement-" in s):
            print("  %s" % sid)
    for r in report:
        print("problem: %s" % r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
