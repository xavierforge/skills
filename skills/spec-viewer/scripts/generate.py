#!/usr/bin/env python3
"""Assemble a self-contained HTML review page for one OpenSpec change.

Reads the fixed OpenSpec file set from a change directory (proposal.md,
design.md, specs/**/*.md, tasks.md), converts a small Markdown subset to
HTML, and writes a single standalone page: navigable sections, highlighted
requirements and Given/When/Then scenarios, and rendered tasks.md checkbox
state. python3 stdlib only, deterministic, no external requests.

A per-section side gloss slot is reserved. When a gloss JSON file is present
(default <change>/gloss.zh-TW.json, or --gloss PATH), its entries, keyed by
section id, are embedded beside the matching sections as an additive reading
aid. The English normative text is never altered or replaced.

When --quiz PATH points at a quiz JSON file, a Quiz tab is appended after the
last document tab. The tab's HTML and JS are fixed in this template; the JSON
supplies only question data (see load_quiz for the schema). Omitting --quiz
leaves the page exactly as it was before this feature existed.

Usage:
    generate.py <change_dir> [--out PATH] [--gloss PATH] [--quiz PATH]

Section ids (needed to author a gloss file) are printed to stdout on every
run, so the flow is: run once, read the ids, write the gloss JSON, run again.
"""

import argparse
import base64
import hashlib
import html
import json
import os
import random
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Inline Markdown: **bold** and `code` over HTML-escaped text.
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


# --------------------------------------------------------------------------
# Block parser: headings, paragraphs, and (nested, checkbox-aware) lists.
# --------------------------------------------------------------------------

_LIST_RE = re.compile(r"^(\s*)([-*])\s+(\[([ xX])\]\s+)?(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def parse_blocks(md):
    lines = md.replace("\r\n", "\n").split("\n")
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = stripped[:3]
            code, i = [], i + 1
            while i < n and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            i += 1  # consume the closing fence (harmless if absent at EOF)
            blocks.append(("code", "\n".join(code)))
            continue
        h = _HEADING_RE.match(line)
        if h:
            blocks.append(("heading", len(h.group(1)), h.group(2).strip()))
            i += 1
            continue
        if _LIST_RE.match(line):
            items = []
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    i += 1
                    break  # a blank line ends the list
                m = _LIST_RE.match(cur)
                if m:
                    indent = len(m.group(1))
                    chk = None if m.group(3) is None else (m.group(4).lower() == "x")
                    items.append([indent, chk, m.group(5).strip()])
                    i += 1
                elif items:
                    items[-1][2] += " " + cur.strip()  # wrapped continuation
                    i += 1
                else:
                    break
            blocks.append(("list", items))
            continue
        para = []
        while i < n and lines[i].strip() and not _HEADING_RE.match(lines[i]) \
                and not _LIST_RE.match(lines[i]):
            para.append(lines[i].strip())
            i += 1
        blocks.append(("para", " ".join(para)))
    return blocks


# --------------------------------------------------------------------------
# List rendering: build an indent tree, then emit proper nested <ul>/<li>.
# --------------------------------------------------------------------------

_GWT_RE = re.compile(r"^\*\*(GIVEN|WHEN|THEN|AND)\*\*\s*(.*)$", re.I)


def _build_tree(items):
    root = {"children": []}
    stack = [(-1, root)]
    for indent, chk, text in items:
        node = {"chk": chk, "text": text, "children": []}
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        stack[-1][1]["children"].append(node)
        stack.append((indent, node))
    return root["children"]


def _render_item_body(chk, text):
    body, pill = text, ""
    m = _GWT_RE.match(text)
    if m:
        kw = m.group(1).upper()
        pill = '<span class="gwt gwt-%s">%s</span> ' % (kw.lower(), kw)
        body = m.group(2)
    inner = pill + render_inline(body)
    if chk is None:
        return inner
    state = "done" if chk else "todo"
    mark = "✔" if chk else ""
    return ('<span class="chk chk-%s" aria-hidden="true">%s</span>'
            '<span class="chk-text">%s</span>') % (state, mark, inner)


def _render_tree(nodes):
    out = ["<ul>"]
    for node in nodes:
        cls = ""
        if node["chk"] is not None:
            cls = ' class="task %s"' % ("done" if node["chk"] else "todo")
        out.append("<li%s>" % cls)
        out.append(_render_item_body(node["chk"], node["text"]))
        if node["children"]:
            out.append(_render_tree(node["children"]))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)


def render_block(block):
    if block[0] == "para":
        return "<p>%s</p>" % render_inline(block[1])
    if block[0] == "list":
        return _render_tree(_build_tree(block[1]))
    if block[0] == "code":
        return "<pre><code>%s</code></pre>" % html.escape(block[1], quote=False)
    return ""


# --------------------------------------------------------------------------
# Section assembly: each heading starts a section that carries a stable id
# and a reserved gloss aside.
# --------------------------------------------------------------------------

def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def unique_id(registry, base):
    cand, k = base, 2
    while cand in registry:
        cand, k = "%s-%d" % (base, k), k + 1
    registry.add(cand)
    return cand


def _split_sections(md):
    blocks = parse_blocks(md)
    sections, cur = [], None
    for b in blocks:
        if b[0] == "heading":
            cur = {"level": b[1], "title": b[2], "blocks": []}
            sections.append(cur)
        else:
            if cur is None:
                cur = {"level": 0, "title": None, "blocks": []}
                sections.append(cur)
            cur["blocks"].append(b)
    return sections


def render_document(prefix, title, md, gloss, registry, nav, index,
                    extra_after_title="", active=True, diff_href=None):
    sections = _split_sections(md)
    nav.append({"id": prefix, "title": title, "level": 0})
    out = ['<div class="doc" id="%s"%s>' % (prefix, "" if active else " hidden")]
    out.append('<h1 class="doc-title">%s</h1>' % html.escape(title))
    if extra_after_title:
        out.append(extra_after_title)

    for sec in sections:
        _render_section(prefix, sec, gloss, registry, nav, index, out, diff_href)
    out.append("</div>")
    return "\n".join(out)


def _render_section(prefix, sec, gloss, registry, nav, index, out, diff_href=None):
    title, level = sec["title"], sec["level"]
    kind, chip, display = "", None, title
    if title and title.startswith("Requirement:"):
        kind, chip, display = "requirement", "Requirement", title[len("Requirement:"):].strip()
    elif title and title.startswith("Scenario:"):
        kind, chip, display = "scenario", "Scenario", title[len("Scenario:"):].strip()

    base = "%s--%s" % (prefix, slugify(title) if title else "intro")
    sid = unique_id(registry, base)
    index.append((sid, display or "(intro)"))
    if title and level in (2, 3):
        nav.append({"id": sid, "title": display, "level": level, "kind": kind})

    classes = "sec lvl-%d%s" % (level, (" " + kind) if kind else "")
    out.append('<section id="%s" class="%s">' % (sid, classes))
    out.append('<div class="sec-main">')
    if title:
        hl = min(max(level, 2), 4)
        chip_html = '<span class="chip chip-%s">%s</span> ' % (kind, chip) if chip else ""
        # The vibe-diff twin gives its intent-map entries ids equal to these
        # section ids, so a requirement can deep-link into the diff page.
        link_html = ""
        if kind == "requirement" and diff_href:
            link_html = ('<a class="diff-link" href="%s#%s">diff ↗</a>'
                         % (html.escape(diff_href), sid))
        out.append('<h%d class="sec-h">%s%s%s</h%d>'
                   % (hl, chip_html, render_inline(display), link_html, hl))
    for b in sec["blocks"]:
        out.append(render_block(b))
    out.append("</div>")

    g = gloss.get(sid)
    if isinstance(g, str) and g.strip():
        paras = "".join("<p>%s</p>" % render_inline(ln)
                        for ln in g.split("\n") if ln.strip())
        out.append('<aside class="sec-gloss has-gloss">'
                   '<span class="gloss-label">譯</span>%s</aside>' % paras)
    else:
        out.append('<aside class="sec-gloss"></aside>')
    out.append("</section>")


def render_spec_group(group_id, title, specs, gloss, registry, nav, index,
                      active=True, diff_href=None):
    # specs: [(spec_prefix, spec_title, md_text), ...], used when a change
    # has more than one spec delta file. Each spec keeps its own section-id
    # prefix (so section ids, and any /vibe-diff links into them, are
    # unchanged by grouping), but all of them share one tab and one
    # nav-group, group_id, since render_nav and the JS tab switcher both key
    # off that shared id. Each spec renders inside its own collapsed
    # <details>, default closed, so N spec files do not blow out the tab bar.
    nav.append({"id": group_id, "title": title, "level": 0})
    out = ['<div class="doc" id="%s"%s>' % (group_id, "" if active else " hidden")]
    out.append('<h1 class="doc-title">%s</h1>' % html.escape(title))
    for spec_prefix, spec_title, md in specs:
        inner = []
        for sec in _split_sections(md):
            _render_section(spec_prefix, sec, gloss, registry, nav, index, inner, diff_href)
        out.append('<details class="spec-toggle"><summary>%s</summary>'
                   '<div class="spec-toggle-body">%s</div></details>'
                   % (html.escape(spec_title), "".join(inner)))
    out.append("</div>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Tasks progress: count checkbox state across the parsed tasks blocks.
# --------------------------------------------------------------------------

def count_tasks(md):
    done = total = 0
    trees = [_build_tree(b[1]) for b in parse_blocks(md) if b[0] == "list"]
    nodes = [n for tree in trees for n in tree]
    while nodes:
        node = nodes.pop()
        if node["chk"] is not None:
            total += 1
            done += 1 if node["chk"] else 0
        nodes.extend(node["children"])
    return done, total


def progress_html(done, total):
    pct = round(100 * done / total) if total else 0
    return ('<div class="progress"><div class="progress-bar">'
            '<span style="width:%d%%"></span></div>'
            '<span class="progress-text">%d / %d tasks done (%d%%)</span></div>'
            ) % (pct, done, total, pct)


# --------------------------------------------------------------------------
# Page shell.
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#fbfaf7;--fg:#23201b;--muted:#6b6459;--rule:#e4ded3;--card:#fff;
--accent:#8a5a2b;--req:#b45309;--scn:#0e7490;--code:#f0ece3;
--when:#1d4ed8;--then:#15803d;--and:#6b6459;--given:#7c3aed;
--done:#15803d;--todo:#b8b0a2;--navbg:#f4f1ea;
--wrong:#dc2626;--wrong-bg:#fbe4e4;--done-bg:#e3f3e6;}
@media (prefers-color-scheme:dark){:root{--bg:#181614;--fg:#e9e4da;
--muted:#a49b8c;--rule:#332f29;--card:#211e1b;--accent:#d9a066;--req:#f0a95a;
--scn:#4fc4dc;--code:#2a2723;--when:#7aa2f7;--then:#8bd08b;--and:#a49b8c;
--given:#c4a7f0;--done:#8bd08b;--todo:#5a5347;--navbg:#1f1c19;
--wrong:#f87171;--wrong-bg:#3a2020;--done-bg:#1f3324;}}
:root[data-theme=light]{--bg:#fbfaf7;--fg:#23201b;--muted:#6b6459;--rule:#e4ded3;
--card:#fff;--accent:#8a5a2b;--req:#b45309;--scn:#0e7490;--code:#f0ece3;
--when:#1d4ed8;--then:#15803d;--and:#6b6459;--given:#7c3aed;--done:#15803d;
--todo:#b8b0a2;--navbg:#f4f1ea;
--wrong:#dc2626;--wrong-bg:#fbe4e4;--done-bg:#e3f3e6;}
:root[data-theme=dark]{--bg:#181614;--fg:#e9e4da;--muted:#a49b8c;--rule:#332f29;
--card:#211e1b;--accent:#d9a066;--req:#f0a95a;--scn:#4fc4dc;--code:#2a2723;
--when:#7aa2f7;--then:#8bd08b;--and:#a49b8c;--given:#c4a7f0;--done:#8bd08b;
--todo:#5a5347;--navbg:#1f1c19;
--wrong:#f87171;--wrong-bg:#3a2020;--done-bg:#1f3324;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
code{background:var(--code);padding:.1em .35em;border-radius:4px;
font:0.85em/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
pre{background:var(--code);border:1px solid var(--rule);border-radius:8px;
padding:.8rem 1rem;overflow-x:auto;margin:.6rem 0;
font:0.82rem/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
pre code{background:none;padding:0;border-radius:0;font-size:inherit}
strong{font-weight:650}
.topbar{position:sticky;top:0;z-index:5;background:var(--navbg);
border-bottom:1px solid var(--rule);padding:.7rem 1.2rem;
display:flex;flex-wrap:wrap;gap:.6rem 1rem;align-items:baseline;}
.topbar h1{margin:0;font-size:1.05rem;font-weight:700}
.topbar .sub{color:var(--muted);font-size:.85rem}
.legend{margin-left:auto;display:flex;gap:.5rem;flex-wrap:wrap;font-size:.72rem}
[hidden]{display:none!important}
.tabs{position:sticky;top:48px;z-index:4;display:flex;gap:.15rem;
overflow-x:auto;background:var(--navbg);border-bottom:1px solid var(--rule);
padding:0 .6rem}
.tab{flex:0 0 auto;border:none;background:none;color:var(--muted);font:inherit;
font-size:.85rem;padding:.55rem .9rem;cursor:pointer;white-space:nowrap;
border-bottom:2px solid transparent}
.tab:hover{color:var(--fg)}
.tab.active{color:var(--fg);border-bottom-color:var(--accent);font-weight:650}
.layout{display:grid;grid-template-columns:250px 1fr;align-items:start}
.sidenav{position:sticky;top:97px;max-height:calc(100vh - 97px);overflow:auto;
padding:1rem .6rem 3rem;border-right:1px solid var(--rule);background:var(--navbg);
font-size:.85rem}
.sidenav a{display:block;color:var(--muted);text-decoration:none;
padding:.15rem .5rem;border-radius:5px;border-left:2px solid transparent}
.sidenav a:hover{color:var(--fg);background:var(--card)}
.sidenav a.active{color:var(--fg);border-left-color:var(--accent);font-weight:600}
.sidenav a.nav-l3{padding-left:1.3rem;font-size:.8rem}
.content{padding:1.4rem clamp(1rem,4vw,3rem);padding-bottom:80vh;max-width:1180px}
.doc-title{font-size:1.5rem;border-bottom:2px solid var(--rule);
padding-bottom:.3rem;margin:.5rem 0 1rem}
.sec{display:grid;grid-template-columns:1fr;gap:0 1.4rem;margin:0 0 .2rem;
scroll-margin-top:104px}
body.has-any-gloss .sec{grid-template-columns:minmax(0,1fr) 230px}
.sec-main{min-width:0}
.sec-h{margin:1.2rem 0 .5rem;line-height:1.3}
h2.sec-h{font-size:1.2rem}h3.sec-h{font-size:1.02rem}h4.sec-h{font-size:.92rem}
.sec.requirement{background:var(--card);border:1px solid var(--rule);
border-left:3px solid var(--req);border-radius:8px;padding:.2rem 1rem;margin:1.1rem 0}
.sec.scenario{border-left:2px solid var(--scn);padding:.1rem 0 .1rem 1rem;
margin:.7rem 0 .7rem .4rem}
.chip{display:inline-block;font-size:.62rem;font-weight:700;text-transform:uppercase;
letter-spacing:.06em;padding:.12em .5em;border-radius:20px;vertical-align:.15em}
.chip-requirement{background:var(--req);color:#fff}
.chip-scenario{background:var(--scn);color:#fff}
.gwt{display:inline-block;font-size:.66rem;font-weight:700;letter-spacing:.05em;
padding:.08em .45em;border-radius:4px;color:#fff;margin-right:.15em}
.gwt-when{background:var(--when)}.gwt-then{background:var(--then)}
.gwt-and{background:var(--and)}.gwt-given{background:var(--given)}
.content ul{margin:.4rem 0;padding-left:1.4rem}
.content li{margin:.22rem 0}
li.task{list-style:none;margin-left:-1.1rem;display:flex;gap:.5rem;align-items:baseline}
li.task .chk{flex:0 0 auto;width:1.05em;height:1.05em;border-radius:4px;
border:1.5px solid var(--todo);display:inline-flex;align-items:center;
justify-content:center;font-size:.75em;line-height:1;transform:translateY(.12em)}
li.task.done .chk{background:var(--done);border-color:var(--done);color:#fff}
li.task.done>.chk-text{color:var(--muted)}
.sec-gloss{font-size:.82rem;color:var(--muted);line-height:1.55}
body:not(.has-any-gloss) .sec-gloss{display:none}
.sec-gloss.has-gloss{border-left:2px solid var(--rule);padding-left:.9rem;
padding-top:.2rem}
.sec-gloss p{margin:.3rem 0}
.gloss-label{display:inline-block;font-size:.62rem;font-weight:700;color:#fff;
background:var(--accent);border-radius:4px;padding:.05em .4em;margin-right:.35em}
.progress{display:flex;align-items:center;gap:.7rem;margin:.2rem 0 1rem}
.progress-bar{flex:0 0 220px;height:9px;background:var(--rule);border-radius:6px;overflow:hidden}
.progress-bar span{display:block;height:100%;background:var(--done)}
.progress-text{font-size:.82rem;color:var(--muted)}
.leg{display:inline-flex;align-items:center;gap:.25em;color:var(--muted)}
.leg .sw{width:.8em;height:.8em;border-radius:3px;display:inline-block}
.topbar-diff{font-size:.8rem;color:var(--accent);text-decoration:none;
border:1px solid var(--rule);border-radius:6px;padding:.1em .55em;white-space:nowrap}
.topbar-diff:hover{background:var(--card)}
.sec-h .diff-link{font-size:.68rem;font-weight:600;color:var(--accent);
text-decoration:none;margin-left:.6em;vertical-align:.15em;opacity:.75}
.sec-h .diff-link:hover{opacity:1;text-decoration:underline}
@media (max-width:820px){.layout{grid-template-columns:1fr}
.sidenav{position:static;max-height:none;border-right:none;
border-bottom:1px solid var(--rule)}
body.has-any-gloss .sec{grid-template-columns:1fr}
body.has-any-gloss .sec-gloss.has-gloss{margin:.3rem 0 .6rem;border-left:none;
border-top:1px dashed var(--rule);padding:.5rem 0 0}}
.layout.wide{grid-template-columns:1fr}
.layout.wide .sidenav{display:none}
.layout.wide .content{max-width:760px;margin:0 auto}
.quiz-status{display:flex;align-items:center;gap:.8rem;margin:.4rem 0 1.3rem;
flex-wrap:wrap}
.quiz-gauge{display:inline-flex;align-items:center;gap:.4em;font-size:.92rem;
font-weight:700;padding:.4em 1.05em;border-radius:20px;background:var(--req);
color:#fff;transition:background .3s}
.quiz-gauge.full{background:var(--done)}
.quiz-gauge-check{margin-left:.05em}
.quiz-tab-dot{margin-left:.35em;font-size:.7em;color:var(--wrong)}
.quiz-tab-dot.full{color:var(--done);font-weight:800}
.quiz-extra{display:inline-flex;align-items:center;gap:.35em;font-size:.8rem;
color:var(--muted);padding:.28em .75em;border:1px dashed var(--rule);border-radius:20px}
.quiz-celebrate{position:fixed;left:50%;top:97px;
transform:translateX(-50%) translateY(-14px);background:var(--done);color:#fff;
padding:.6rem 1.3rem;border-radius:30px;font-weight:700;font-size:.92rem;
box-shadow:0 8px 22px rgba(0,0,0,.28);opacity:0;pointer-events:none;z-index:50}
.quiz-celebrate.show{animation:quizCelebrate 2.6s ease forwards}
@keyframes quizCelebrate{
0%{opacity:0;transform:translateX(-50%) translateY(-14px)}
15%{opacity:1;transform:translateX(-50%) translateY(0)}
82%{opacity:1;transform:translateX(-50%) translateY(0)}
100%{opacity:0;transform:translateX(-50%) translateY(-6px)}
}
.quiz-list{background:var(--card);border:1px solid var(--rule);border-radius:10px;
padding:1rem 1.2rem}
.quiz-item{margin:.9rem 0}
.quiz-item:first-child{margin-top:0}
.quiz-item[hidden]{display:none}
.quiz-item.revealing{animation:quizReveal .38s ease both}
@keyframes quizReveal{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.quiz-q{font-weight:650;font-size:.94rem;margin:0 0 .5rem;line-height:1.4}
.quiz-options{display:flex;flex-direction:column;gap:.4rem}
.quiz-opt{text-align:left;font:inherit;font-size:.86rem;padding:.55rem .8rem;
border-radius:8px;border:1px solid var(--rule);background:var(--card);color:var(--fg);
cursor:pointer}
.quiz-opt:hover:not(:disabled){border-color:var(--accent)}
.quiz-opt.correct{border-color:var(--done);background:var(--done-bg)}
.quiz-opt.wrong{border-color:var(--wrong);background:var(--wrong-bg)}
.quiz-opt:disabled{cursor:default;opacity:.85}
.quiz-feedback{font-size:.82rem;padding:.6rem .8rem;border-radius:7px;
margin-top:.5rem;line-height:1.5}
.quiz-feedback[hidden]{display:none}
.quiz-feedback.correct{background:var(--done-bg)}
.quiz-feedback.wrong{background:var(--wrong-bg)}
.quiz-more-wrap{display:flex;flex-direction:column;align-items:center;gap:.4rem;
margin:1.4rem 0 2rem}
.quiz-more{font:inherit;font-size:.86rem;font-weight:600;padding:.6rem 1.5rem;
border-radius:20px;border:1px solid var(--rule);background:var(--card);color:var(--fg);
cursor:pointer}
.quiz-more:hover:not(:disabled){border-color:var(--accent)}
.quiz-more:disabled{cursor:not-allowed;opacity:.75;color:var(--muted);font-weight:500}
.quiz-shown-count{font-size:.74rem;color:var(--muted)}
.quiz-reset{margin-top:.3rem;border:none;background:none;color:var(--muted);
font:inherit;font-size:.72rem;text-decoration:underline;cursor:pointer;padding:.2rem .4rem}
.quiz-reset:hover{color:var(--fg)}
.quiz-reset.armed{color:var(--wrong);font-weight:650;text-decoration:none}
.spec-toggle{border:1px solid var(--rule);border-radius:8px;margin:0 0 1rem;
background:var(--card);overflow:hidden}
.spec-toggle>summary{cursor:pointer;list-style:none;padding:.7rem 1rem;
font-weight:650;font-size:1.02rem;display:flex;align-items:center;gap:.5em}
.spec-toggle>summary::-webkit-details-marker{display:none}
.spec-toggle>summary::before{content:'▸';display:inline-block;
transition:transform .15s;color:var(--muted);font-size:.8em}
.spec-toggle[open]>summary::before{transform:rotate(90deg)}
.spec-toggle>summary:hover{background:var(--navbg)}
.spec-toggle-body{padding:.2rem 1.1rem 1rem}
"""

JS = """
(function(){
var OFFSET=112;  // header height + a little; the "current section" line
var links={};
document.querySelectorAll('.sidenav a').forEach(function(a){
links[a.getAttribute('href').slice(1)]=a;});
function show(doc){
document.querySelectorAll('.tab').forEach(function(t){
t.classList.toggle('active',t.dataset.doc===doc);});
document.querySelectorAll('.doc').forEach(function(d){d.hidden=d.id!==doc;});
document.querySelectorAll('.nav-group').forEach(function(g){
g.hidden=g.dataset.doc!==doc;});
var layout=document.querySelector('.layout');
if(layout)layout.classList.toggle('wide',doc==='quiz');
}
function setActive(id){
Object.keys(links).forEach(function(k){links[k].classList.toggle('active',k===id);});
}
function spy(){
// Only sections in the visible doc that have a ToC link (offsetParent is
// null for a display:none section, so hidden docs drop out).
var secs=[].slice.call(document.querySelectorAll('section[id]'))
.filter(function(s){return s.offsetParent!==null&&links[s.id];});
if(!secs.length)return;
var doc=document.documentElement;
if(window.innerHeight+window.scrollY>=doc.scrollHeight-4){
setActive(secs[secs.length-1].id);return;}  // at page bottom: last item wins
var cur=secs[0].id;
for(var i=0;i<secs.length;i++){
if(secs[i].getBoundingClientRect().top<=OFFSET)cur=secs[i].id;else break;}
setActive(cur);
}
document.querySelectorAll('.tab').forEach(function(t){
t.addEventListener('click',function(){show(t.dataset.doc);
window.scrollTo(0,0);spy();});});
// A sidebar link may point into a not-yet-active doc; switch to it first.
// It may also point inside a collapsed spec <details>; open that too, before
// the browser's own hash navigation tries to scroll to it.
document.querySelectorAll('.sidenav a').forEach(function(a){
a.addEventListener('click',function(){
var g=a.closest('.nav-group');if(g)show(g.dataset.doc);
var target=document.getElementById(a.getAttribute('href').slice(1));
var det=target?target.closest('details'):null;
if(det)det.open=true;});});
window.addEventListener('scroll',spy,{passive:true});
window.addEventListener('resize',spy);
spy();
})();
(function(){
// Quiz tab. Inert when the page carries no quiz data (QUIZ_B64 unset, or
// no #quiz-list element because --quiz was not passed to generate.py).
var listEl=document.getElementById('quiz-list');
var b64=(typeof QUIZ_B64!=='undefined')?QUIZ_B64:null;
if(!listEl||!b64)return;
var change=(typeof QUIZ_CHANGE!=='undefined')?QUIZ_CHANGE:'';
var PREFIX='spec-viewer-review:'+change+':';
var items;
try{
var bin=atob(b64);
var bytes=new Uint8Array(bin.length);
for(var i=0;i<bin.length;i++)bytes[i]=bin.charCodeAt(i);
items=JSON.parse(new TextDecoder('utf-8').decode(bytes));
}catch(e){
listEl.textContent='Quiz data failed to load.';
return;
}
if(!items||!items.length)return;

var FIRST=Math.min(8,items.length);
var BATCH=8;

function key(suffix){return PREFIX+suffix;}
function isSolved(id){
try{return localStorage.getItem(key('q:'+id))==='1';}
catch(e){return false;}
}
function setSolved(id){
try{localStorage.setItem(key('q:'+id),'1');}catch(e){}
}
function getShown(){
var v=0;
try{v=parseInt(localStorage.getItem(key('shown'))||'',10);}catch(e){}
if(!v||v<FIRST)v=FIRST;
return Math.min(v,items.length);
}
function setShown(n){
try{localStorage.setItem(key('shown'),String(n));}catch(e){}
}

var shown=getShown();

var gaugeEl=document.getElementById('quiz-gauge');
var gaugeN=document.getElementById('quiz-gauge-n');
var gaugeD=document.getElementById('quiz-gauge-d');
var gaugeCheckEl=document.getElementById('quiz-gauge-check');
var tabDotEl=document.getElementById('quiz-tab-dot');
var extraEl=document.getElementById('quiz-extra');
var extraN=document.getElementById('quiz-extra-n');
var extraD=document.getElementById('quiz-extra-d');
var celebrateEl=document.getElementById('quiz-celebrate');
var moreBtn=document.getElementById('quiz-more');
var shownCountEl=document.getElementById('quiz-shown-count');

gaugeD.textContent=String(FIRST);

function countUnderstanding(){
var n=0;
for(var i=0;i<FIRST;i++)if(isSolved(items[i].id))n++;
return n;
}
function countExtra(){
var n=0,d=0;
for(var i=FIRST;i<shown;i++){d++;if(isSolved(items[i].id))n++;}
return [n,d];
}

var understandingCount=countUnderstanding();

function renderGauge(prevCount){
gaugeN.textContent=String(understandingCount);
var full=FIRST>0&&understandingCount>=FIRST;
gaugeEl.classList.toggle('full',full);
if(gaugeCheckEl)gaugeCheckEl.hidden=!full;
if(tabDotEl){
tabDotEl.textContent=full?'✓':'●';
tabDotEl.classList.toggle('full',full);
}
if(full&&prevCount!==undefined&&prevCount<FIRST){
celebrateEl.classList.remove('show');
void celebrateEl.offsetWidth;  // restart the CSS animation
celebrateEl.classList.add('show');
}
}
renderGauge();

function renderExtra(){
var r=countExtra();
if(r[1]>0){
extraEl.hidden=false;
extraN.textContent=String(r[0]);
extraD.textContent=String(r[1]);
}else{
extraEl.hidden=true;
}
}
renderExtra();

function renderShownCount(){
shownCountEl.textContent='Shown '+shown+'/'+items.length;
}

function updateMoreButton(){
renderShownCount();
if(shown>=items.length){
moreBtn.disabled=true;
moreBtn.textContent='All questions shown. Ask your session to generate more for this change.';
}
}

function onAnswer(item,idx,oi,buttons,feedbackEl,itemEl){
if(itemEl.classList.contains('solved'))return;
buttons.forEach(function(b){b.classList.remove('wrong');});
if(oi===item.correct){
buttons.forEach(function(b,i){
b.disabled=true;
if(i===oi)b.classList.add('correct');
});
feedbackEl.hidden=false;
feedbackEl.className='quiz-feedback correct';
feedbackEl.textContent=item.cite;
itemEl.classList.add('solved');
setSolved(item.id);
if(idx<FIRST){
var prev=understandingCount;
understandingCount=countUnderstanding();
renderGauge(prev);
}
renderExtra();
}else{
buttons[oi].classList.add('wrong');
feedbackEl.hidden=false;
feedbackEl.className='quiz-feedback wrong';
feedbackEl.textContent=(item.why&&item.why[oi])||'Not quite, try again.';
}
}

function buildItem(item,idx){
var el=document.createElement('div');
el.className='quiz-item';
el.id='qz-'+item.id;
el.dataset.id=String(item.id);
if(idx>=shown)el.hidden=true;

var qEl=document.createElement('div');
qEl.className='quiz-q';
qEl.textContent=(idx+1)+'. '+item.q;
el.appendChild(qEl);

var optsEl=document.createElement('div');
optsEl.className='quiz-options';
var feedbackEl=document.createElement('div');
feedbackEl.className='quiz-feedback';
feedbackEl.hidden=true;

var solved=isSolved(item.id);
var buttons=[];
item.options.forEach(function(opt,oi){
var b=document.createElement('button');
b.type='button';
b.className='quiz-opt';
b.textContent=opt;
b.disabled=solved;
if(solved&&oi===item.correct)b.classList.add('correct');
b.addEventListener('click',function(){onAnswer(item,idx,oi,buttons,feedbackEl,el);});
buttons.push(b);
optsEl.appendChild(b);
});
el.appendChild(optsEl);

if(solved){
feedbackEl.hidden=false;
feedbackEl.className='quiz-feedback correct';
feedbackEl.textContent=item.cite;
el.classList.add('solved');
}
el.appendChild(feedbackEl);
return el;
}

items.forEach(function(item,idx){listEl.appendChild(buildItem(item,idx));});
updateMoreButton();

moreBtn.addEventListener('click',function(){
var newShown=Math.min(shown+BATCH,items.length);
var kids=listEl.children;
for(var i=shown;i<newShown;i++){
var node=kids[i];
if(node){
node.hidden=false;
node.classList.add('revealing');
(function(n){setTimeout(function(){n.classList.remove('revealing');},450);})(node);
}
}
shown=newShown;
setShown(shown);
renderExtra();
updateMoreButton();
});

var resetBtn=document.getElementById('quiz-reset');
if(resetBtn){
var resetArmed=false,resetTimer=null;
resetBtn.addEventListener('click',function(){
if(!resetArmed){
resetArmed=true;
resetBtn.textContent='Sure? Reset';
resetBtn.classList.add('armed');
resetTimer=setTimeout(function(){
resetArmed=false;
resetBtn.textContent='Reset answers';
resetBtn.classList.remove('armed');
},4000);
return;
}
clearTimeout(resetTimer);
try{
var toRemove=[];
for(var i=0;i<localStorage.length;i++){
var k=localStorage.key(i);
if(k&&k.indexOf(PREFIX)===0)toRemove.push(k);
}
toRemove.forEach(function(k){localStorage.removeItem(k);});
}catch(e){}
location.reload();
});
}
})();
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body class="__BODYCLASS__">
<div class="topbar">
<h1>__HEADING__</h1>
<span class="sub">OpenSpec change review</span>
__DIFFLINK__
__QUIZTOPBAR__
<div class="legend">
<span class="leg"><span class="chip chip-requirement">Req</span></span>
<span class="leg"><span class="chip chip-scenario">Scn</span></span>
<span class="leg"><span class="gwt gwt-when">WHEN</span></span>
<span class="leg"><span class="gwt gwt-then">THEN</span></span>
<span class="leg"><span class="sw" style="background:var(--done)"></span>done</span>
<span class="leg"><span class="sw" style="border:1.5px solid var(--todo)"></span>todo</span>
</div>
</div>
__TABS__
<div class="layout">
<nav class="sidenav">__NAV__</nav>
<main class="content">__BODY__</main>
</div>
__QUIZINIT__
<script>__JS__</script>
</body>
</html>
"""


def render_tabs(tab_items):
    # tab_items: [(prefix, title), ...], real docs plus the optional trailing
    # Quiz tab; the first entry is always the initially active one. The Quiz
    # tab carries an extra status dot, kept in sync with the topbar gauge by
    # the fixed JS (red until 8/8, then a green check).
    out = ['<div class="tabs" role="tablist">']
    for i, (prefix, title) in enumerate(tab_items):
        cls = "tab active" if i == 0 else "tab"
        dot = ('<span class="quiz-tab-dot" id="quiz-tab-dot" aria-hidden="true">●</span>'
               if prefix == "quiz" else "")
        out.append('<button class="%s" data-doc="%s">%s%s</button>'
                   % (cls, prefix, html.escape(title), dot))
    out.append("</div>")
    return "".join(out)


def render_nav(nav):
    # Group the section links per document; only the active doc's group is
    # shown, and the tab bar switches between groups. A group with no section
    # links (a doc that is all intro prose) still renders, so its tab has a
    # matching, if empty, side panel.
    out, open_group, first = [], False, True
    for e in nav:
        if e["level"] == 0:
            if open_group:
                out.append("</div>")
            out.append('<div class="nav-group" data-doc="%s"%s>'
                       % (e["id"], "" if first else " hidden"))
            open_group, first = True, False
        else:
            out.append('<a class="nav-l%d" href="#%s">%s</a>'
                       % (e["level"], e["id"], render_inline(e["title"])))
    if open_group:
        out.append("</div>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Quiz tab (optional, --quiz PATH): a JSON question bank, always the last
# tab. All interactive behavior lives in the fixed JS above; this side only
# validates the JSON and emits the static shell plus the base64 data blob it
# reads at runtime. No question text is ever rendered server-side.
# --------------------------------------------------------------------------

def load_quiz(path):
    p = Path(path)
    if not p.is_file():
        print("error: quiz file not found: %s" % p, file=sys.stderr)
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        print("error: could not read quiz %s: %s" % (p, exc), file=sys.stderr)
        return None
    if not isinstance(data, list) or not data:
        print("error: quiz %s must be a non-empty JSON array" % p, file=sys.stderr)
        return None

    required = ("id", "q", "options", "correct", "why", "cite")
    seen_ids = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not all(k in item for k in required):
            print("error: quiz item %d missing one of %s" % (i, required), file=sys.stderr)
            return None
        opts = item["options"]
        if not isinstance(opts, list) or not (3 <= len(opts) <= 4) \
                or not all(isinstance(o, str) for o in opts):
            print("error: quiz item %d 'options' must be 3-4 strings" % i, file=sys.stderr)
            return None
        why = item["why"]
        if not isinstance(why, list) or len(why) != len(opts):
            print("error: quiz item %d 'why' must have one entry per option" % i,
                  file=sys.stderr)
            return None
        correct = item["correct"]
        if not isinstance(correct, int) or isinstance(correct, bool) \
                or not (0 <= correct < len(opts)):
            print("error: quiz item %d 'correct' must be a valid option index" % i,
                  file=sys.stderr)
            return None
        qid = item["id"]
        if not isinstance(qid, str) or not qid:
            print("error: quiz item %d 'id' must be a non-empty string" % i, file=sys.stderr)
            return None
        if qid in seen_ids:
            print("error: duplicate quiz id: %s" % qid, file=sys.stderr)
            return None
        seen_ids.add(qid)
    return data


def _shuffle_seed(qid):
    # sha256, not the builtin hash(), so the seed is stable across processes
    # and platforms (Python randomizes str hashing per process by default).
    digest = hashlib.sha256(qid.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def shuffle_options(items):
    # Quiz authors tend to write the correct option first far more often
    # than chance alone would explain, letting a reader guess by position
    # instead of reading. Each question's options are permuted with a seed
    # derived from its own id, so the same id always yields the same order
    # (stable across re-renders) while different ids yield different orders.
    # Only presentation order changes; correct and why are carried along so
    # they still point at the right option, and the JSON on disk is untouched.
    shuffled = []
    for item in items:
        order = list(range(len(item["options"])))
        random.Random(_shuffle_seed(item["id"])).shuffle(order)
        new_item = dict(item)
        new_item["options"] = [item["options"][i] for i in order]
        new_item["why"] = [item["why"][i] for i in order]
        new_item["correct"] = order.index(item["correct"])
        shuffled.append(new_item)
    return shuffled


QUIZ_SHELL = """<div class="doc" id="quiz" hidden>
<h1 class="doc-title">Quiz</h1>
<div class="quiz-status">
<span class="quiz-extra" id="quiz-extra" hidden>Extra <span id="quiz-extra-n">0</span>/<span id="quiz-extra-d">0</span></span>
</div>
<div class="quiz-list" id="quiz-list"></div>
<div class="quiz-more-wrap">
<button type="button" class="quiz-more" id="quiz-more">Ask me more</button>
<span class="quiz-shown-count" id="quiz-shown-count"></span>
<button type="button" class="quiz-reset" id="quiz-reset">Reset answers</button>
</div>
</div>"""


# --------------------------------------------------------------------------

def collect_docs(change):
    # Doc prefixes are load-bearing ids (the tab's data-doc, the doc div id,
    # the nav-group's data-doc), so they must be unique. Two spec files whose
    # capability names slugify the same (e.g. specs/user auth/ and
    # specs/user-auth/) would otherwise collide and break tab switching; run
    # every prefix through the same de-dup as section ids.
    docs, seen = [], set()

    def add(base, title, path):
        docs.append((unique_id(seen, base), title, path))

    if (change / "proposal.md").is_file():
        add("proposal", "Proposal", change / "proposal.md")
    if (change / "design.md").is_file():
        add("design", "Design", change / "design.md")
    specs = change / "specs"
    if specs.is_dir():
        for sp in sorted(specs.glob("**/*.md")):
            cap = sp.parent.name if sp.name == "spec.md" else sp.stem
            add("spec-%s" % slugify(cap), "Spec: %s" % cap, sp)
    if (change / "tasks.md").is_file():
        add("tasks", "Tasks", change / "tasks.md")
    return docs


def main(argv=None):
    # The stdout report echoes section titles and gloss keys, which for a
    # zh-TW gloss are non-ASCII; force UTF-8 so a legacy console (e.g. Windows
    # cp1252) does not raise UnicodeEncodeError after the file is written.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Render an OpenSpec change to one HTML page.")
    ap.add_argument("change_dir", help="path to openspec/changes/<name>/")
    ap.add_argument("--out", help="output HTML path (default: <change_dir>/review.html)")
    ap.add_argument("--gloss", help="zh-TW gloss JSON (default: <change_dir>/gloss.zh-TW.json)")
    ap.add_argument("--quiz", help="quiz JSON; when given, appends a Quiz tab after the last document")
    args = ap.parse_args(argv)

    change = Path(args.change_dir)
    if not change.is_dir():
        print("error: not a directory: %s" % change, file=sys.stderr)
        return 2

    docs = collect_docs(change)
    if not docs:
        print("error: no OpenSpec files found in %s" % change, file=sys.stderr)
        return 2

    gloss_path = Path(args.gloss) if args.gloss else change / "gloss.zh-TW.json"
    gloss = {}
    if gloss_path.is_file():
        try:
            gloss = json.loads(gloss_path.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as exc:
            print("error: could not read gloss %s: %s" % (gloss_path, exc), file=sys.stderr)
            return 2
        if not isinstance(gloss, dict):
            print("error: gloss %s must be a JSON object keyed by section id" % gloss_path,
                  file=sys.stderr)
            return 2

    quiz_items = None
    if args.quiz:
        quiz_items = load_quiz(args.quiz)
        if quiz_items is None:
            return 2
        quiz_items = shuffle_options(quiz_items)

    out_path = Path(args.out) if args.out else change / "review.html"

    # Twin link: when /vibe-diff's page already sits next to the change, link
    # into it (topbar link + per-requirement "diff ↗" anchors). The href is
    # computed relative to where this page is written so it works from --out
    # locations too; forward slashes keep it a valid URL on Windows.
    diff_page = change / "diff-review.html"
    diff_href = None
    if diff_page.is_file():
        diff_href = Path(os.path.relpath(diff_page, out_path.parent)).as_posix()

    # Spec deltas: one tab each normally, but a change with several (each
    # its own file under specs/) would blow out the tab bar (it has, up to
    # 7 in practice), pushing the Quiz tab off-screen behind horizontal
    # scroll. Past the first spec file, merge them into one "specs (N)" tab
    # of collapsed toggles instead; a single spec file still gets its own
    # plain tab, unchanged.
    registry, nav, index, body = set(), [], [], []
    spec_docs = [d for d in docs if d[0].startswith("spec-")]
    grouped_specs = len(spec_docs) > 1
    tab_items, spec_group_done, first_rendered = [], False, True
    for prefix, title, path in docs:
        if grouped_specs and prefix.startswith("spec-"):
            if spec_group_done:
                continue
            group_title = "specs (%d)" % len(spec_docs)
            specs_payload = [(sp_prefix, sp_title, sp_path.read_text(encoding="utf-8-sig"))
                             for sp_prefix, sp_title, sp_path in spec_docs]
            body.append(render_spec_group("specs", group_title, specs_payload, gloss,
                                          registry, nav, index, active=first_rendered,
                                          diff_href=diff_href))
            tab_items.append(("specs", group_title))
            spec_group_done, first_rendered = True, False
            continue
        md = path.read_text(encoding="utf-8-sig")
        extra = ""
        if prefix == "tasks":
            extra = progress_html(*count_tasks(md))
        body.append(render_document(prefix, title, md, gloss, registry, nav,
                                    index, extra, active=first_rendered,
                                    diff_href=diff_href))
        tab_items.append((prefix, title))
        first_rendered = False

    name = change.name
    # Substitute the fixed-template slots first and the document body last, so
    # a source document that literally contains a slot token (e.g. the text
    # "__TITLE__") cannot be rewritten by a later replace pass.
    diff_link_html = ""
    if diff_href:
        diff_link_html = ('<a class="topbar-diff" href="%s">diff review ↗</a>'
                          % html.escape(diff_href))

    # Quiz tab: appended after every real doc tab. No question text is ever
    # rendered server-side; the shell is a fixed constant, and the questions
    # travel as a base64 JSON blob the fixed JS decodes at runtime (base64
    # has no HTML-significant characters, so it needs no escaping to sit
    # inside a <script> tag).
    quiz_body_html = ""
    quiz_init_html = ""
    quiz_topbar_html = ""
    if quiz_items:
        tab_items.append(("quiz", "Quiz"))
        quiz_body_html = QUIZ_SHELL
        blob = base64.b64encode(
            json.dumps(quiz_items, ensure_ascii=False).encode("utf-8")).decode("ascii")
        quiz_init_html = ("<script>var QUIZ_B64=%s;var QUIZ_CHANGE=%s;</script>"
                          % (json.dumps(blob), json.dumps(name)))
        # The understanding gate: persistent in the topbar (visible on every
        # tab, not just Quiz), solid-filled so it reads as a status, not
        # decoration. quiz-gauge-check is the 8/8 checkmark; the amber-to-
        # green fill and the Quiz tab's dot (see render_tabs) are driven by
        # the same JS state.
        quiz_topbar_html = (
            '<span class="quiz-gauge" id="quiz-gauge">Understanding '
            '<span id="quiz-gauge-n">0</span>/<span id="quiz-gauge-d">8</span>'
            '<span class="quiz-gauge-check" id="quiz-gauge-check" hidden> ✓</span>'
            '</span>'
            '<div class="quiz-celebrate" id="quiz-celebrate" aria-hidden="true">'
            'Great work, full understanding of the first 8!</div>')

    page = (PAGE
            .replace("__CSS__", CSS)
            .replace("__JS__", JS)
            .replace("__QUIZINIT__", quiz_init_html)
            .replace("__QUIZTOPBAR__", quiz_topbar_html)
            .replace("__BODYCLASS__", "has-any-gloss" if gloss else "")
            .replace("__HEADING__", html.escape(name))
            .replace("__TITLE__", html.escape(name))
            .replace("__TABS__", render_tabs(tab_items))
            .replace("__NAV__", render_nav(nav))
            .replace("__DIFFLINK__", diff_link_html)
            .replace("__BODY__", "\n".join(body) + quiz_body_html))

    out_path.write_text(page, encoding="utf-8")

    # Report to stdout: the ids a gloss author keys on, and gloss coverage.
    print("wrote %s (%d sections, %d docs)" % (out_path, len(index), len(docs)))
    if diff_href:
        print("diff page: linked (%s)" % diff_href)
    else:
        print("diff page: none (looked for %s)" % diff_page)
    if len(spec_docs) > 1:
        print("specs: merged %d files into one tab" % len(spec_docs))
    elif len(spec_docs) == 1:
        print("specs: 1 file (own tab)")
    else:
        print("specs: none")
    matched = sum(1 for sid, _ in index if sid in gloss)
    if gloss:
        print("gloss: %s (%d/%d sections matched)" % (gloss_path, matched, len(index)))
        stale = [k for k in gloss if k not in registry]
        if stale:
            print("gloss keys with no matching section: %s" % ", ".join(sorted(stale)))
    else:
        print("gloss: none (looked for %s)" % gloss_path)
    if quiz_items:
        print("quiz: %s (%d questions)" % (args.quiz, len(quiz_items)))
    else:
        print("quiz: none (pass --quiz PATH to add the Quiz tab)")
    print("section ids:")
    for sid, disp in index:
        flag = " [gloss]" if sid in gloss else ""
        print("  %s  %s%s" % (sid, disp, flag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
