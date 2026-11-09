#!/usr/bin/env python3
"""Pre-publish check for a learn study page (stdlib only).

    python check_page.py <page.html> [--assets DIR] [--review]   # one line per finding; exit 1 on any FAIL
    python check_page.py --selftest

Checks:
  (a) every inline <script> without src parses: written to a temp file, `node --check`;
  (b) no raw U+2028, U+2029, U+FEFF, U+200B-U+200F or NUL inside any script
      (U+2028/2029 are JS line terminators: inside a regex or string literal they kill the whole script);
  (c) every local <script src> (not http(s)/data/protocol-relative) resolves next to the page or in the
      assets dir (default: this skill's assets/, which holds submit-to-tutor.js) and passes (a) and (b);
      a missing one FAILs, since it would also be missing from the publish `files` map;
  (d) counts textarea[data-q] and requires the data-q values to be unique;
  (e) a page with textarea[data-q] (static, or `data-q=` in its script templates) must load a submit
      mechanism: <script src=".../submit-to-tutor.js"> or an inline script calling sendToClaude;
  (f) WARN when one .box.q holds more than one textarea outside <div class="part"> (several sub-questions
      sharing one box; give each part its own <div class="part">);
  (g) the explanation gate, check_explanations.py (always, mechanical): data-explain blocks open with a why hook,
      lead with their example, aren't compressed, are followed by an Ask box, and no display formula sits outside
      a marked block. --review also runs its model review (ai ask ds) per block.

Why: 2026-11-09 the tabpfn page's script had raw U+2028/2029 in a regex literal, so it never parsed, no
"Submit to tutor" button rendered, and nobody noticed for a day. The same day, writing the shared
submit-to-tutor.js through an agent's file-write tool turned its backslash-u escapes into raw characters.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

BSL = chr(92)  # backslash; spelled out so no escape sequence passes through an editor or write tool
BAD_CHARS = {0x0000: "NUL", 0x2028: "LINE SEPARATOR", 0x2029: "PARAGRAPH SEPARATOR", 0xFEFF: "BOM/ZWNBSP"}
BAD_CHARS.update({cp: "zero-width/direction mark" for cp in range(0x200B, 0x2010)})
BAD_RE = re.compile("[" + "".join(chr(cp) for cp in sorted(BAD_CHARS)) + "]")
SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.IGNORECASE | re.DOTALL)
JS_TYPES = {"", "text/javascript", "application/javascript", "module"}
REMOTE_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
SUBMIT_JS = "submit-to-tutor.js"
DEFAULT_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
USAGE = "usage: check_page.py <page.html> [--assets DIR] [--review] | --selftest"


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1  # count \n only: str.splitlines would split on U+2028 too


def attr(attrs: str, name: str) -> str | None:
    m = re.search(r"\b" + name + r"""\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", attrs, re.IGNORECASE)
    if m:
        return next(g for g in m.groups() if g is not None)
    return "" if re.search(r"\b" + name + r"\b", attrs, re.IGNORECASE) else None


def check_js(body: str, stype: str, where, line0: int, fails: list[str]) -> None:
    """Raw-character scan plus `node --check` of one script body. line0 = line of the body's first line;
    where(n) renders the location prefix for line n."""
    for b in BAD_RE.finditer(body):
        cp = ord(b.group())
        fails.append(f"FAIL {where(line0 + body.count(chr(10), 0, b.start()))} raw U+{cp:04X} "
                     f"({BAD_CHARS[cp]}); use a {BSL}uXXXX escape")
    if stype not in JS_TYPES:
        return
    node = shutil.which("node")
    if not node:
        fails.append("FAIL: node not on PATH; cannot run node --check")
        return
    fd, path = tempfile.mkstemp(suffix=".mjs" if stype == "module" else ".js", prefix="check_page_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(body)
        r = subprocess.run([node, "--check", path], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if r.returncode != 0:
            err = next((ln.strip() for ln in (r.stderr or "").splitlines() if "Error" in ln), "syntax error")
            hit = re.search(re.escape(os.path.basename(path)) + r":(\d+)", r.stderr or "")
            at = line0 + int(hit.group(1)) - 1 if hit else line0
            fails.append(f"FAIL {where(at)} does not parse (node --check): {err}")
    finally:
        os.unlink(path)


def resolve_src(src: str, page_dir: str, assets: str) -> str | None:
    rel = src.split("?", 1)[0].split("#", 1)[0]
    for base in (page_dir, assets):
        p = os.path.normpath(os.path.join(base, rel))
        if os.path.isfile(p):
            return p
    p = os.path.join(assets, os.path.basename(rel))  # "../assets/x.js" or a bare name: try the asset's own name
    return p if os.path.isfile(p) else None


def check_scripts(text: str, page: str, assets: str, fails: list[str], info: dict) -> None:
    page_dir = os.path.dirname(os.path.abspath(page))
    for m in SCRIPT_RE.finditer(text):
        attrs, body = m.group(1), m.group(2)
        stype = (attr(attrs, "type") or "").strip().lower()
        src_attr = attr(attrs, "src")
        if src_attr is None:
            info["inline"] += 1
            k = info["inline"]
            check_js(body, stype, lambda n, k=k: f"line {n}: inline <script> #{k}", line_of(text, m.start(2)), fails)
            if "sendToClaude" in body:
                info["submit"] = "inline"
            if "data-q=" in body:
                info["dynamic_q"] = True
            continue
        for b in BAD_RE.finditer(body):  # body of a src script is ignored by browsers, but flag stray chars
            fails.append(f"FAIL line {line_of(text, m.start(2) + b.start())}: raw U+{ord(b.group()):04X} in <script>")
        src = src_attr.strip()
        if not src or REMOTE_RE.match(src):
            continue
        path = resolve_src(src, page_dir, assets)
        if not path:
            fails.append(f"FAIL line {line_of(text, m.start())}: <script src=\"{src}\"> not found next to the page "
                         f"or in {assets}; it will 404 unless published in the `files` map")
            continue
        info["local"].append(path)
        if os.path.basename(path) == SUBMIT_JS:
            info["submit"] = path
        try:
            with open(path, "rb") as f:
                js = f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            fails.append(f"FAIL: cannot read {path} as UTF-8 ({e})")
            continue
        base = os.path.basename(path)
        check_js(js, stype, lambda n, base=base: f"{base} line {n}:", 1, fails)


class Boxes(HTMLParser):
    """Track textarea[data-q] and which .box.q / .part div each sits in."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []  # open divs: {"box": bool, "part": bool, "loose": int, "line": int}
        self.qs: list[tuple[str, int]] = []
        self.warns: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            cls = (a.get("class") or "").split()
            self.stack.append({"box": "box" in cls and "q" in cls, "part": "part" in cls, "loose": 0,
                               "line": self.getpos()[0]})
        elif tag == "textarea" and "data-q" in a:
            self.qs.append((a["data-q"] or "", self.getpos()[0]))
            for d in reversed(self.stack):
                if d["part"]:
                    break
                if d["box"]:
                    d["loose"] += 1
                    break

    def handle_endtag(self, tag):
        if tag == "div" and self.stack:
            d = self.stack.pop()
            if d["box"] and d["loose"] > 1:
                self.warns.append(f"WARN line {d['line']}: .box.q holds {d['loose']} textareas outside "
                                  '<div class="part"> (one box, several sub-questions)')


def check(path: str, assets: str = DEFAULT_ASSETS, review: bool = False) -> int:
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"FAIL: {path} is not valid UTF-8 ({e})")
        return 1
    fails: list[str] = []
    info: dict = {"inline": 0, "local": [], "submit": None, "dynamic_q": False}
    check_scripts(text, path, assets, fails, info)
    p = Boxes()
    p.feed(text)
    p.close()
    seen: dict[str, int] = {}
    for q, ln in p.qs:
        if q in seen:
            fails.append(f"FAIL line {ln}: duplicate data-q=\"{q}\" (first at line {seen[q]})")
        else:
            seen[q] = ln
    if (p.qs or info["dynamic_q"]) and not info["submit"]:
        fails.append(f"FAIL: page has textarea[data-q] but loads no submit mechanism (<script src=\"{SUBMIT_JS}\"> "
                     "or an inline sendToClaude); answers would have no Submit to tutor")
    if not p.qs and not info["dynamic_q"]:
        p.warns.append("WARN: no textarea[data-q] on the page")
    for line in fails + p.warns:
        print(line)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import check_explanations  # sibling; the explanation gate (owner, 2026-11-09)

    erc = check_explanations.review(path) if review else check_explanations.check(path)[0]
    if erc:
        fails.append("FAIL: explanation gate (above)")
    status = "FAIL" if fails else "OK"
    qs = f"{len(p.qs)} textarea[data-q]" + (" + script-rendered" if info["dynamic_q"] else "")
    sub = info["submit"]
    sub_s = "none" if not sub else ("inline" if sub == "inline" else os.path.basename(sub))
    print(f"{status}: {path}: {info['inline']} inline script(s), {len(info['local'])} local src script(s), {qs}, "
          f"submit: {sub_s}, {len(fails)} failure(s), {len(p.warns)} warning(s)")
    for lp in info["local"]:
        print(f"  publish with files: {{\"{os.path.basename(lp)}\": \"{lp.replace(os.sep, '/')}\"}}")
    return 1 if fails else 0


SUBMIT_STUB = "window.TutorSubmit = { send: function () { return Promise.resolve({}); } };" + chr(10)
CLEAN_JS = ("var clean = function (x) { return x.replace(/[" + BSL + "u2028" + BSL + "u2029" + BSL + "u200B-"
            + BSL + "u200F" + BSL + "uFEFF]+/g, ' '); };")
GOOD = ("<!doctype html><html><body>" + chr(10)
        + '<div class="box q"><p>Q1</p>' + chr(10)
        + '  <div class="part"><textarea data-q="Q1a"></textarea></div>' + chr(10)
        + '  <div class="part"><textarea data-q="Q1b"></textarea></div>' + chr(10)
        + "</div>" + chr(10)
        + '<div class="box q"><textarea data-q="Q2"></textarea></div>' + chr(10)
        + "<script src=\"https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js\"></script>" + chr(10)
        + "<script>" + CLEAN_JS + "</script>" + chr(10)
        + "<script src=\"" + SUBMIT_JS + "\" data-drafts=\"off\"></script>" + chr(10)
        + "</body></html>" + chr(10))
BAD = ("<!doctype html><html><body>" + chr(10)
       + '<div class="box q"><p>Q1 (a) and (b)</p>' + chr(10)
       + '  <textarea data-q="Q1"></textarea>' + chr(10)
       + '  <textarea data-q="Q1"></textarea>' + chr(10)
       + "</div>" + chr(10)
       + "<script>var clean = function (x) { return x.replace(/[" + chr(0x2028) + chr(0x2029) + "]+/g, ' '); };</script>"
       + chr(10)
       + "<script>var ok = 1;" + chr(0x200B) + "</script>" + chr(10)
       + "<script src=\"missing.js\"></script>" + chr(10)
       + "<script src=\"broken.js\"></script>" + chr(10)
       + "</body></html>" + chr(10))
NOSUBMIT = ('<!doctype html><html><body><div class="box q"><textarea data-q="Q1"></textarea></div>'
            "<script>var x = `<textarea data-q=\"r1\">`;</script></body></html>" + chr(10))


def selftest() -> int:
    import contextlib
    import io

    d = tempfile.mkdtemp(prefix="check_page_selftest_")
    assets = os.path.join(d, "assets")
    os.makedirs(assets)
    try:
        with open(os.path.join(assets, SUBMIT_JS), "w", encoding="utf-8", newline="") as f:
            f.write(SUBMIT_STUB)
        with open(os.path.join(d, "broken.js"), "w", encoding="utf-8", newline="") as f:
            f.write("var y = (;" + chr(10) + "var z = '" + chr(0x2028) + "';" + chr(10))
        results = {}
        for name, html in (("good", GOOD), ("bad", BAD), ("nosubmit", NOSUBMIT)):
            p = os.path.join(d, name + ".html")
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(html)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check(p, assets)
            results[name] = (rc, buf.getvalue())
        ok = True
        rc, out = results["good"]
        if rc != 0 or "FAIL" in out or "WARN" in out or "submit: " + SUBMIT_JS not in out:
            ok = False
            print("selftest: good page should pass cleanly with the shared submit script:" + chr(10) + out)
        rc, out = results["bad"]
        expect = ["U+2028", "U+2029", "U+200B", "does not parse", "duplicate data-q", "outside <div class=\"part\">",
                  "missing.js\"> not found", "broken.js line 1: does not parse", "broken.js line 2: raw U+2028",
                  "loads no submit mechanism"]
        missing = [e for e in expect if e not in out]
        if rc == 0 or missing:
            ok = False
            print(f"selftest: bad page rc={rc}, missing findings {missing}:" + chr(10) + out)
        rc, out = results["nosubmit"]
        if rc == 0 or "loads no submit mechanism" not in out or "script-rendered" not in out:
            ok = False
            print("selftest: page without a submit script should fail:" + chr(10) + out)
        print("selftest: OK" if ok else "selftest: FAILED")
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    assets = DEFAULT_ASSETS
    args = list(argv)
    review = "--review" in args
    if review:
        args.remove("--review")
    if "--assets" in args:
        i = args.index("--assets")
        if i + 1 >= len(args):
            print(USAGE)
            return 2
        assets = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or args[0].startswith("-"):
        print("Pre-publish check for a learn study page.")
        print(USAGE)
        return 2
    return check(args[0], assets, review)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
