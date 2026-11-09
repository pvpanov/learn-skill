#!/usr/bin/env python3
"""Headless render check for a learn study page (stdlib + a local Chrome or Edge).

    python render_check.py <page.html>      # exit 0 ok, 1 FAIL, 2 cannot run (no browser): the gate fails then too
    python render_check.py --selftest

Loads the page in headless Chrome with a fake `window.claude` (comments + an empty db), its local
`<script src>` files copied beside it (from the page folder, else the skill's assets/), and reports:
  - every rendered textarea[data-q] was wired by submit-to-tutor.js and has one "Submit to tutor" button;
  - no uncaught script error or unhandled rejection;
  - a page whose static HTML has answer boxes renders at least one.
A db-driven page (items come from the artifact db) renders no items under the empty stub; that is not a FAIL.

Why: 2026-11-09 a raw U+2028 in the tabpfn page's regex killed its script, so no Submit button rendered, and
nobody noticed for a day; the owner's slot went on fixing it (f052, f056). `learn.py ready-check` runs this.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
BROWSERS = [os.environ.get("LEARN_CHROME", ""), "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", shutil.which("chrome") or "",
            shutil.which("google-chrome") or "", shutil.which("chromium") or ""]

STUB = """<script>
window.__errors = [];
window.addEventListener('error', function (e) { window.__errors.push(String(e.message || e)); });
window.addEventListener('unhandledrejection', function (e) { window.__errors.push('rejection: ' + String(e.reason)); });
(function () {
  function snap() { return { metadata: { fromCache: false }, docs: [], size: 0, empty: true, forEach: function () {} }; }
  var coll = { onSnapshot: function (cb) { setTimeout(function () { cb(snap()); }, 5); return function () {}; },
               get: function () { return Promise.resolve(snap()); }, where: function () { return coll; },
               orderBy: function () { return coll; }, limit: function () { return coll; } };
  var db = { collection: function () { return coll; },
             doc: function () { return { update: function () { return Promise.resolve(); }, set: function () { return Promise.resolve(); },
                                         get: function () { return Promise.resolve({ exists: false, data: function () { return null; } }); },
                                         onSnapshot: function (cb) { return function () {}; } }; } };
  var comments = { anchorFor: function (el) { return Promise.resolve({ path: el.id || el.tagName, x: 1, y: 1 }); },
                   sendToClaude: function () { return Promise.resolve({ threadId: 't', commentId: 'c' }); },
                   list: function () { return Promise.resolve([]); } };
  window.claude = { use: function (name) { return Promise.resolve(name === 'comments' ? comments : name === 'db' ? db : {}); } };
})();
</script>"""

DRIVER = """<script>
setTimeout(function () {
  var boxes = Array.prototype.slice.call(document.querySelectorAll('textarea[data-q]'));
  var out = { boxes: boxes.length, buttons: document.querySelectorAll('button.tutor-submit').length,
              unwired: boxes.filter(function (t) { return !t.__tutorWired; }).map(function (t) { return t.getAttribute('data-q'); }),
              other: Array.prototype.filter.call(document.querySelectorAll('button'), function (b) {
                return !b.classList.contains('tutor-submit') && /submit/i.test(b.textContent); }).length,
              errors: window.__errors };
  var pre = document.createElement('pre'); pre.id = 'RENDER_RESULT'; pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
}, 2500);
</script>"""


def browser() -> str | None:
    return next((b for b in BROWSERS if b and Path(b).exists()), None)


def static_boxes(html: str) -> int:
    no_script = re.sub(r"(?is)<script\b.*?</script>", "", html)
    return len(re.findall(r"(?is)<textarea\b[^>]*\bdata-q=", no_script))


def render(page: Path) -> tuple[int, str]:
    exe = browser()
    if not exe:
        return 2, "no Chrome/Edge found (set LEARN_CHROME): the render check cannot run, so the gate fails"
    html = page.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t = Path(tmp)
        for src in re.findall(r'(?is)<script\b[^>]*\bsrc="([^"]+)"', html):
            if re.match(r"(?i)^(https?:)?//|^data:", src):
                continue
            found = next((c for c in (page.parent / src, ASSETS / src) if c.exists()), None)
            if found is None:
                return 1, f"FAIL local script {src} not found beside the page or in assets/"
            (t / src).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(found, t / src)
        # <head> or <head attr=...>, never <header> (lea-3: the stub landed mid-body on the Dutch page)
        if re.search(r"(?i)<head(?=[\s>])[^>]*>", html):
            doc = re.sub(r"(?i)(<head(?=[\s>])[^>]*>)", lambda m: m.group(1) + STUB, html, count=1)
        else:
            doc = '<!doctype html><html><head><meta charset="utf-8">' + STUB + "</head><body>" + html + "</body></html>"
        doc = re.sub(r"(?i)</body>", DRIVER + "</body>", doc, count=1) if re.search(r"(?i)</body>", doc) else doc + DRIVER
        out = t / "page.html"
        out.write_text(doc, encoding="utf-8")
        try:
            r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                f"--user-data-dir={t / 'profile'}", "--allow-file-access-from-files",
                                "--virtual-time-budget=6000", "--dump-dom", out.as_uri()],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        except subprocess.TimeoutExpired:
            return 2, "browser timed out"
    m = re.search(r'<pre id="RENDER_RESULT">(.*?)</pre>', r.stdout, re.S)
    if not m:
        return 1, "FAIL page did not finish rendering (no result); stderr: " + (r.stderr or "")[-400:]
    raw = m.group(1).replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    res = json.loads(raw)
    fails = []
    if res["errors"]:
        fails.append("script errors: " + "; ".join(res["errors"][:3]))
    if res["unwired"]:
        fails.append("boxes not wired by the shared submit-to-tutor.js: " + ", ".join(map(str, res["unwired"][:8]))
                     + (f" (the page has {res['other']} Submit buttons of its own: a per-page copy, which SKILL.md bans)"
                        if res.get("other") else ""))
    if res["buttons"] != res["boxes"]:
        fails.append(f"{res['boxes']} answer boxes but {res['buttons']} Submit buttons")
    if static_boxes(html) and not res["boxes"]:
        fails.append("the HTML has answer boxes but none rendered")
    summary = f"{res['boxes']} answer boxes, {res['buttons']} Submit buttons, {len(res['errors'])} script errors"
    return (1, "FAIL " + " | ".join(fails) + f" ({summary})") if fails else (0, f"ok: {summary}")


def selftest() -> int:
    if not browser():
        print("selftest skipped: no browser")
        return 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        t = Path(tmp)
        shutil.copy(ASSETS / "submit-to-tutor.js", t / "submit-to-tutor.js")
        good = t / "good.html"
        good.write_text('<div class="box q"><p>Q</p><div class="part"><textarea data-q="a"></textarea></div>'
                        '<div class="part"><textarea data-q="b"></textarea></div></div>'
                        '<script src="submit-to-tutor.js"></script>', encoding="utf-8")
        code, msg = render(good)
        assert code == 0 and "2 answer boxes, 2 Submit" in msg, msg
        bad = t / "bad.html"  # the 2026-11-09 failure: the page's script dies, so the shared one never loads
        bad.write_text('<textarea data-q="a"></textarea><script>var x = ;</script>', encoding="utf-8")
        code, msg = render(bad)
        assert code == 1 and "FAIL" in msg, msg
    print("selftest ok")
    return 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--selftest"]:
        return selftest()
    if len(argv) != 1:
        print(__doc__)
        return 2
    code, msg = render(Path(argv[0]))
    print(f"render_check {argv[0]}: {msg}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
