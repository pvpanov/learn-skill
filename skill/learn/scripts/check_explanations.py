#!/usr/bin/env python3
"""Explanation gate for a learn study page (stdlib only). check_page.py runs the mechanical part on every page.

    python check_explanations.py <page.html>            # mechanical checks; exit 1 on any FAIL
    python check_explanations.py --review <page.html>   # mechanical, then a model review per block (ai ask ds)
    python check_explanations.py --calibrate [--runs N]   # the --review model on labelled fixtures (DS calls)
    python check_explanations.py --selftest

Markup: every explanation block (a box that teaches: definitions, mechanism, formulas) carries
`data-explain="<id>"`, e.g. <div class="box" data-explain="S2">. Inside it:
  data-role="why"      the "why you care" hook, inside the block's first paragraph (on the <p> or a child);
  data-role="example"  the running concrete example, on the element that introduces it.
Mechanical checks, per block:
  (a) the first content element is a <p>, not a formula, list or example: no display math, at most half its text
      in inline math, some prose, and a data-role="why" hook with text;
  (b) a data-role="example" element opens before the first display formula;
  (c) a block with any formula (display or inline) has a data-role="example";
  (d) WARN when the example only starts in the second half of the block's text (example at the end);
  (e) not compressed: at most half the block's text in <ul>/<ol> items, and its paragraphs average at least
      25 words (factoids and bullet conclusions are not an explanation).
Page-wide: a display formula outside every data-explain block, .box.q and script/style FAILs: an unmarked
explanation would skip the gate.
--review sends each block that passed the mechanical checks to a cheap model with the beat-order checklist
(SKILL.md "Example first, everywhere") and prints PASS/FAIL with its reasons; a FAIL means the block is
rewritten, not published.

Why: 2026-11-09 the tabpfn page's S2 "VI vs MCMC" opened straight into definitions and formulas, with no reason to
care, and its only example came last; the rule was already in SKILL.md and was ignored (owner: third time). The
same day: "a bunch of factoids/high level logic; no textbook is structured like that".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

BSL = chr(92)  # backslash; spelled out so no escape sequence passes through an editor or write tool
DISPLAY = BSL + "["
INLINE_RE = re.compile(re.escape(BSL + "(") + r".*?" + re.escape(BSL + ")"), re.DOTALL)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
INLINE_TAGS = {"span", "strong", "em", "b", "i", "a", "code", "sub", "sup", "abbr", "mark", "small"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
LABEL_CLASSES = {"kind", "eyebrow"}
MIN_PROSE = 40       # characters of non-math text the opening paragraph needs
MIN_AVG_WORDS = 25   # average words per <p> in a block (inline math counts as one word)
MAX_LIST_SHARE = 0.5  # share of block text allowed inside <li>
AI_MJS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                                       "plugins", "ai-hub", "bin", "ai.mjs"))
USAGE = "usage: check_explanations.py [--review] <page.html> | --calibrate [--runs N] | --selftest"
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "explain-fixtures", "topics", "demo")


class Block:
    def __init__(self, bid: str, line: int, start: int) -> None:
        self.id, self.line, self.start, self.end = bid, line, start, start
        self.first: tuple[str, int] | None = None  # (what, line) of the first content element
        self.first_p_open = False                  # inside the first <p> right now
        self.first_p_text: list[str] = []
        self.first_p_why = ""                      # text inside a why hook within the first <p>
        self.example: tuple[int, int] | None = None  # (seq, chars of block text before it)
        self.display: tuple[int, int] | None = None  # (seq, line) of the first display formula
        self.inline = 0
        self.chars = 0
        self.li_chars = 0
        self.p_words: list[int] = []  # word count per <p>
        self.ask = ""  # "" not seen yet, "missing", "box" (.box.ask without an Ask textarea), "ok"


def words(s: str) -> int:
    return len(INLINE_RE.sub(" M ", s).split())


class Explain(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.text = text
        self.line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.stack: list[dict] = []  # open elements
        self.blocks: list[Block] = []
        self.cur: Block | None = None
        self.seq = 0
        self.fails: list[str] = []
        self.unmarked: dict[int, int] = {}  # enclosing element line -> display formulas in it
        self.pending: Block | None = None  # block just closed, waiting for its .box.ask

    def char_pos(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def flag(self, key: str) -> bool:
        return any(e[key] for e in self.stack)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        cls = set(a.get("class", "").split())
        role = a.get("data-role", "").strip().lower()
        line = self.getpos()[0]
        self.seq += 1
        e = {"tag": tag, "explain": None, "q": "box" in cls and "q" in cls, "skip": tag in ("script", "style"),
             "label": tag in HEADINGS or bool(cls & LABEL_CLASSES), "firstp": False, "why": False,
             "li": tag == "li", "p": None, "ask": None, "line": line}
        if self.pending is not None:  # the element right after a data-explain block must be its .box.ask
            b0, self.pending = self.pending, None
            if "box" in cls and "ask" in cls:
                e["ask"], b0.ask = b0, "box"
            else:
                b0.ask = "missing"
        if tag == "textarea" and a.get("data-q", "").startswith("Ask:"):
            ab = next((x["ask"] for x in reversed(self.stack) if x["ask"]), None)
            if ab:
                ab.ask = "ok"
        if "data-explain" in a:
            if self.cur:
                self.fails.append(f"FAIL line {line}: data-explain block nested inside \"{self.cur.id}\" "
                                  f"(line {self.cur.line}); mark only the outer box")
            else:
                b = Block(a["data-explain"].strip() or f"line {line}", line, self.char_pos())
                self.blocks.append(b)
                self.cur = b
                e["explain"] = b
                if role == "why":
                    self.fails.append(f"FAIL line {line}: data-role=\"why\" on the block itself; put it on its "
                                      "first <p>")
        b = self.cur
        if b and not e["explain"] and not e["label"] and not self.flag("label"):
            if b.first is None and tag not in VOID and tag not in INLINE_TAGS:
                b.first = ("example" if role == "example" else "<" + tag + ">", line)
                if tag == "p":
                    b.first_p_open, e["firstp"] = True, True
            if role == "example" and b.example is None:
                b.example = (self.seq, b.chars)
            if role == "why" and b.first_p_open:
                e["why"] = True
            if tag == "p":
                b.p_words.append(0)
                e["p"] = len(b.p_words) - 1
        if tag not in VOID:
            self.stack.append(e)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1]["tag"] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        idx = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i]["tag"] == tag), None)
        if idx is None:
            return
        while len(self.stack) > idx:
            e = self.stack.pop()
            if e["firstp"] and self.cur:
                self.cur.first_p_open = False
            b = e["explain"]
            if b:
                gt = self.text.find(">", self.char_pos())
                b.end = len(self.text) if gt < 0 else gt + 1
                self.cur = None
                self.pending = b

    def handle_data(self, data):
        if self.flag("skip"):
            return
        b = self.cur
        pos = data.find(DISPLAY)
        if pos >= 0 and not b and not self.flag("q"):
            box = next((e["line"] for e in reversed(self.stack) if e["tag"] in ("div", "section")),
                       self.getpos()[0] + data.count("\n", 0, pos))
            self.unmarked[box] = self.unmarked.get(box, 0) + data.count(DISPLAY)
        if not b or self.flag("label"):
            return
        if pos >= 0:
            self.seq += 1
            if b.display is None:
                b.display = (self.seq, self.getpos()[0] + data.count("\n", 0, pos))
            if b.first is None:
                b.first = ("a display formula", b.display[1])
        b.inline += len(INLINE_RE.findall(data))
        if b.first is None and data.strip():
            b.first = ("loose text", self.getpos()[0])
        if b.first_p_open:
            b.first_p_text.append(data)
            if self.flag("why"):
                b.first_p_why += data
        n = len(data.strip())
        b.chars += n
        if self.flag("li"):
            b.li_chars += n
        pi = next((e["p"] for e in reversed(self.stack) if e["p"] is not None), None)
        if pi is not None:
            b.p_words[pi] += words(data)


def scan(text: str) -> tuple[list[str], list[str], list[Block]]:
    p = Explain(text)
    p.feed(text)
    p.close()
    fails, warns = list(p.fails), []
    for ln, n in sorted(p.unmarked.items()):
        fails.append(f"FAIL line {ln}: {n} display formula(s) outside any data-explain block (and not in a .box.q): "
                     "mark the explanation box data-explain=\"<id>\" so the gate checks it")
    for b in p.blocks:
        tag = f"line {b.line}: data-explain=\"{b.id}\":"
        if b.ask != "ok":
            fails.append(f"FAIL {tag} (f) " + ("its .box.ask has no <textarea data-q=\"Ask: ...\">" if b.ask == "box"
                         else "not directly followed by a <div class=\"box ask\"> with <textarea data-q=\"Ask: "
                         f"{b.id}\">") + " (owner, 2026-11-09: an Ask about this field after every explanation)")
        if b.first is None:
            fails.append(f"FAIL {tag} empty block")
            continue
        what, fl = b.first
        if what != "<p>":
            fails.append(f"FAIL {tag} (a) opens with {what} (line {fl}); open with a <p> saying why the owner "
                         "cares, in their world, before any definition, formula or example")
        else:
            ptxt = "".join(b.first_p_text)
            if DISPLAY in ptxt:
                fails.append(f"FAIL {tag} (a) first paragraph holds a display formula")
            dense = len(re.sub(r"\s", "", ptxt))
            math = sum(len(re.sub(r"\s", "", m)) for m in INLINE_RE.findall(ptxt))
            prose = len(re.sub(r"\s", "", INLINE_RE.sub("", ptxt)))
            if dense and math * 2 > dense:
                fails.append(f"FAIL {tag} (a) first paragraph is mostly inline math ({math}/{dense} chars); "
                             "it should be motivation, not a definition")
            if prose < MIN_PROSE:
                fails.append(f"FAIL {tag} (a) first paragraph has {prose} chars of prose; say why this matters")
            if not b.first_p_why.strip():
                fails.append(f"FAIL {tag} (a) first paragraph has no data-role=\"why\" hook (why the owner "
                             "should care, e.g. for a decision they face at work)")
        if b.display and (b.example is None or b.example[0] > b.display[0]):
            fails.append(f"FAIL {tag} (b) first display formula (line {b.display[1]}) comes before any "
                         "data-role=\"example\"; introduce the running example first")
        if (b.display or b.inline) and b.example is None:
            fails.append(f"FAIL {tag} (c) has formulas but no data-role=\"example\"")
        if b.example and b.chars and b.example[1] * 2 > b.chars:
            warns.append(f"WARN {tag} (d) the example starts in the second half of the block; lead with it")
        if b.chars and b.li_chars > MAX_LIST_SHARE * b.chars:
            fails.append(f"FAIL {tag} (e) {round(100 * b.li_chars / b.chars)}% of the text is list items; explain "
                         "in connected paragraphs (bullets are for summaries and checklists)")
        if b.p_words:
            avg = sum(b.p_words) / len(b.p_words)
            if avg < MIN_AVG_WORDS:
                fails.append(f"FAIL {tag} (e) paragraphs average {avg:.0f} words (< {MIN_AVG_WORDS}): factoids, "
                             "not exposition; give the reasoning between the claims")
    return fails, warns, p.blocks


def check(path: str) -> tuple[int, list[str], list[Block], str]:
    """Print the mechanical findings. Returns (rc, failure lines, blocks, page text)."""
    with open(path, "rb") as f:
        text = f.read().decode("utf-8")
    fails, warns, blocks = scan(text)
    for line in fails + warns:
        print(line)
    print(f"{'FAIL' if fails else 'OK'}: explanations: {len(blocks)} data-explain block(s), "
          f"{len(fails)} failure(s), {len(warns)} warning(s)")
    return (1 if fails else 0), fails, blocks, text


CHECKLIST = """You review one explanation block from a study page for a single learner. {LEARNER} Their
stated rules: theory needs motivation first, with examples before or while going through it, otherwise "why learn
this" and they drift; an explanation must read like a textbook section, connected exposition, never "a bunch of
factoids/high level logic"; "don't overcompress the material". Formal proofs are NOT wanted unless the learner
asked for them: the reasoning between steps is given in words. Length is fine; compression is not.
The block is HTML; formulas are TeX between backslash-[ ... backslash-] (display) or backslash-( ... backslash-)
(inline). data-role="why" marks the hook, data-role="example" the example.

Judge each item, in order, PASS or FAIL with a reason that quotes the block:
1. MOTIVATION FIRST: the opening paragraph poses the question in the learner's own world (why they would care,
   e.g. a decision or situation from the topic goal above), not a definition, a notation line or a bare claim.
2. EXAMPLE AT ONCE: one concrete running example is introduced immediately after (within the first two or three
   paragraphs), before the general statement, and it actually shows the concept (not answerable by recall).
3. INTERLEAVED, WORKED CONCRETELY: the theory is interleaved with that same example, and the example is worked
   through concretely: with actual numbers when the topic is quantitative (formulas, quantities), with actual
   words, actions and situations when it is not (language, conversation, skills); do not demand numbers for a
   block with no quantities in it. Every formula or definition is followed by what it means in the example. Any formula or
   definition that never goes back to the example is a FAIL; so is a run of two or more definitions or formulas
   with no example between them; so is an example that appears only at the end.
4. EVERY STEP: Would a learner new to this follow every step? Is every term defined before it is used? Is any
   claim asserted without the step (in words; no formal proof needed) that gets there? Is the conclusion stated
   only after the reasoning that reaches it?
5. TEXTBOOK, NOT FACTOIDS: Does it read like a textbook section, connected paragraphs where each step follows
   from the previous one and says why? A list of conclusions, terse one-line claims, or overcompressed
   paragraphs is a FAIL. Bullets are fine only as a summary after the exposition.
6. TAKEAWAY: the block ends with what it changes for the learner's decision (what to do or choose differently).
7. ACCURACY: every claim, formula, number and piece of arithmetic in the block is correct, and each conclusion
   follows from what the block states. Recompute the example's arithmetic. A wrong mechanism, formula or number
   is a FAIL however well the block is written; so is a strong claim ("exactly", "equivalent", "always") that
   is only approximately or sometimes true.

Then a final line that is exactly "VERDICT: PASS" or "VERDICT: FAIL". FAIL if any item fails. If it fails,
add one line "REWRITE:" naming the smallest change (which paragraph to move, add or expand).
"""
def learner_context(path: str) -> str:
    """Topic context for the review, from topics/<slug>/meta.json next to the page (lea-2: was TabPFN-only)."""
    parts = os.path.abspath(path).replace(os.sep, "/").split("/")
    if "topics" in parts:
        i = len(parts) - 1 - parts[::-1].index("topics")
        if i + 1 < len(parts):
            meta = "/".join(parts[:i + 2]) + "/meta.json"
            try:
                with open(meta, encoding="utf-8") as f:
                    m = json.load(f)
                goal = (m.get("goal") or "").strip()
                kind = (m.get("type") or "").strip()
                if goal:
                    return (f"The topic is '{parts[i + 1]}'" + (f" ({kind})" if kind else "")
                            + f"; the learner's goal for it: {goal}")
            except (OSError, ValueError):
                pass
    return "The topic and the learner's goal are not recorded; judge against the page's own framing."


PROMPT = ("Review the attached explanation block against the attached checklist. Follow the checklist output "
          "format exactly and end with the VERDICT line.")
VERDICT_RE = re.compile(r"^\W*VERDICT\W*(PASS|FAIL)\b", re.IGNORECASE | re.MULTILINE)


def ai_cmd() -> list[str] | None:
    node = shutil.which("node")
    if node and os.path.isfile(AI_MJS):
        return [node, AI_MJS]  # direct: no cmd.exe quoting of the prompt
    ai = shutil.which("ai")
    return [ai] if ai else None


def review_block(base: list[str], checklist: str, src: str, workdir: str, tag: str) -> tuple[str, str, int, str]:
    """One model review of one block: (PASS|FAIL|ERROR, model output, exit code, stderr)."""
    bp = os.path.join(workdir, f"block-{tag}.html")
    with open(bp, "w", encoding="utf-8", newline="") as f:
        f.write(src + chr(10))
    cmd = base + ["ask", "ds", "@" + checklist.replace(os.sep, "/"), "@" + bp.replace(os.sep, "/"), PROMPT]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    hits = VERDICT_RE.findall(out)
    verdict = hits[-1].upper() if hits and r.returncode == 0 else "ERROR"
    return verdict, out, r.returncode, (r.stderr or "").strip()


def write_checklist(workdir: str, page: str, name: str = "checklist.md") -> str:
    cl = os.path.join(workdir, name)
    with open(cl, "w", encoding="utf-8", newline="") as f:
        f.write(CHECKLIST.replace("{LEARNER}", learner_context(page)))
    return cl


def review(path: str) -> int:
    rc, fails, blocks, text = check(path)
    base = ai_cmd()
    if not base:
        print("FAIL: review: neither node + ai.mjs nor `ai` found; cannot run the model review")
        return 1
    if not blocks:
        print("review: no data-explain blocks")
        return rc
    bad = {m.group(1) for f in fails for m in [re.search(r'data-explain="([^"]*)"', f)] if m}
    worst = rc
    d = tempfile.mkdtemp(prefix="check_explanations_")
    try:
        cl = write_checklist(d, path)
        for i, b in enumerate(blocks, 1):
            if b.id in bad:
                print(f"REVIEW {b.id} (line {b.line}): SKIPPED, fix the mechanical failures first")
                worst = 1
                continue
            verdict, out, code, err = review_block(base, cl, text[b.start:b.end], d, str(i))
            if verdict != "PASS":
                worst = 1
            print(f"REVIEW {b.id} (line {b.line}): {verdict}")
            for ln in (out or err).splitlines():
                print("    " + ln)
            if verdict == "ERROR":
                print(f"    (ai ask exit {code}; no VERDICT line)")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("review: FAIL (rewrite the failing blocks; do not publish)" if worst else "review: OK")
    return worst


def calibrate(runs: int) -> int:
    """Measure the --review model on labelled fixtures (Astra/Fable borrow review, 2026-11-09: the cheap reviewer
    was never shown to catch what it is meant to catch). good-*.html must PASS, bad-*.html must FAIL; every
    fixture passes the mechanical gate, so only the model's judgement is measured. Rerun after changing the
    checklist or the reviewer model."""
    from concurrent.futures import ThreadPoolExecutor

    base = ai_cmd()
    if not base:
        print("FAIL: calibrate: neither node + ai.mjs nor `ai` found")
        return 1
    names = sorted(n for n in os.listdir(FIXTURES) if n.endswith(".html") and n.startswith(("good-", "bad-")))
    jobs, rc, results = [], 0, []
    d = tempfile.mkdtemp(prefix="check_explanations_cal_")
    try:
        for n in names:
            path = os.path.join(FIXTURES, n)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            fails, _warns, blocks = scan(text)
            if fails or len(blocks) != 1:
                print(f"FAIL fixture {n}: must be one block that passes the mechanical gate: {fails or len(blocks)}")
                rc = 1
                continue
            cl = write_checklist(d, path, f"checklist-{n}.md")
            src = text[blocks[0].start:blocks[0].end]
            jobs += [(n, k, cl, src) for k in range(runs)]
        with ThreadPoolExecutor(max_workers=min(6, len(jobs) or 1)) as ex:
            results = list(ex.map(lambda j: (j[0], review_block(base, j[2], j[3], d, f"{j[0]}-{j[1]}")), jobs))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    by: dict[str, list[tuple[str, str]]] = {}
    for n, (verdict, out, _code, err) in results:
        by.setdefault(n, []).append((verdict, out or err))
    fp = ff = errs = stable = 0
    for n, rs in by.items():
        want = "PASS" if n.startswith("good-") else "FAIL"
        verdicts = [v for v, _ in rs]
        wrong = [o for v, o in rs if v != want]
        fp += sum(v == "PASS" for v in verdicts) if want == "FAIL" else 0
        ff += sum(v == "FAIL" for v in verdicts) if want == "PASS" else 0
        errs += verdicts.count("ERROR")
        stable += len(set(verdicts)) == 1
        print(f"{'OK  ' if not wrong else 'MISS'} {n}: want {want}, got {' '.join(verdicts)}")
        if wrong:
            print("    first mismatching review:")
            for ln in wrong[0].splitlines():
                print("      " + ln)
    print(f"calibrate: {len(by)} fixture(s) x {runs} run(s): false passes {fp}, false fails {ff}, errors {errs}, "
          f"repeatable {stable}/{len(by)}")
    return 1 if rc or fp or ff or errs or not results else 0


P_LONG = ("The point of this paragraph is to carry the reasoning in connected prose, so that each step is said "
          "and the reader is never left to fill in why one claim follows from the one before it.")
# S1-shaped: why hook, example at once, formula, meaning in the example, takeaway.
GOOD = ("<!doctype html><html><body>" + chr(10)
        + '<div class="box" data-explain="S1">' + chr(10)
        + '  <span class="kind">Side question</span>' + chr(10)
        + '  <p data-role="why"><strong>Your question:</strong> why would you pick a PFN over a sampler for your '
        + "forecasting model at all? Because what you can <em>do</em> with the prior decides what you may put in it, "
        + "and that decides what your own PFN can learn.</p>" + chr(10)
        + '  <p data-role="example"><strong>Start with an example.</strong> A drifting coefficient '
        + BSL + "(" + BSL + "beta_t = " + BSL + "beta_{t-1} + " + BSL + "eta_t" + BSL + ") with t-noise. "
        + P_LONG + "</p>" + chr(10)
        + "  " + DISPLAY + " p(D) = " + BSL + "int p(D " + BSL + "mid " + BSL + "beta) p(" + BSL + "beta) d"
        + BSL + "beta " + BSL + "]" + chr(10)
        + "  <p>In the example this is an integral over the whole path. " + P_LONG
        + " Takeaway for your PFN: write the prior as a sampler.</p>" + chr(10)
        + "</div>" + chr(10)
        + '<div class="box ask"><textarea data-q="Ask: S1" aria-label="Ask about S1"></textarea></div>' + chr(10)
        + '<div class="box q"><p>Check</p>' + DISPLAY + " x^2 " + BSL + "]" + '<textarea data-q="Q1"></textarea></div>'
        + chr(10)
        + "<script>window.MathJax = { tex: { displayMath: [['" + BSL * 2 + "[', '" + BSL * 2 + "]']] } };</script>"
        + chr(10) + "</body></html>" + chr(10))
# S2 as it was on 2026-11-09: definitions first, formulas, example last.
BAD_S2 = ("<!doctype html><html><body>" + chr(10)
          + '<div class="box" data-explain="S2">' + chr(10)
          + "  <p>Both approximate the posterior " + BSL + "(p(" + BSL + "phi " + BSL + "mid D)" + BSL
          + "); both need the joint.</p>" + chr(10)
          + "  <p><strong>VI</strong>: pick a family and optimise:</p>" + chr(10)
          + "  " + DISPLAY + " " + BSL + "lambda^* = " + BSL + "arg" + BSL + "min KL(q " + BSL + "| p) " + BSL + "]"
          + chr(10)
          + "  <p>Direction of the KL matters.</p>" + chr(10)
          + "  " + DISPLAY + " KL(q " + BSL + "| p) " + BSL + "]" + chr(10)
          + '  <p data-role="example"><strong>Example.</strong> A bimodal posterior on beta, near +1 or -1; '
          + "well-mixed MCMC visits both, Gaussian VI sits on one mode and is confidently wrong half the time.</p>"
          + chr(10) + "</div>" + chr(10) + "</body></html>" + chr(10))
MISC = ("<!doctype html><html><body>" + chr(10)
        + '<div class="box" data-explain="F">' + chr(10)
        + "  " + DISPLAY + " a = b " + BSL + "]" + chr(10)
        + '  <p data-role="why">Why you care: this sets the step size in your model. ' + P_LONG + "</p>"
        + chr(10)
        + '  <p data-role="example">Example. ' + P_LONG + "</p>" + chr(10)
        + "</div>" + chr(10)
        + '<div class="box ask"><p>Ask about this</p></div>' + chr(10)
        + '<div class="box" data-explain="N"><p data-role="why">Why it matters for your PFN prior choice. '
        + P_LONG + "</p>" + chr(10)
        + "  <p>Inline only: " + BSL + "(x" + BSL + ") and " + BSL + "(y" + BSL + "). " + P_LONG + "</p></div>"
        + chr(10)
        + '<div class="box" data-explain="M"><p data-role="why">' + BSL + "(a + b + c + d + e + f + g + h + i + j + "
        + "k + l + m + n + o + p + q + r + s + t + u + v + w + x + y + z + aa + bb + cc + dd + ee + ff + gg + hh"
        + BSL + ") ok, short</p>" + chr(10)
        + '  <p data-role="example">Example. ' + P_LONG + "</p></div>" + chr(10)
        + '<div class="box" data-explain="E"><p data-role="why">Why it matters for your forecast. ' + P_LONG
        + "</p><p>Theory " + BSL + "(x" + BSL + "). " + P_LONG + " " + P_LONG + "</p>" + chr(10)
        + '  <p data-role="example">Example at the end, with enough words to be a real paragraph here. '
        + P_LONG + "</p></div>" + chr(10)
        + '<div class="box ask"><textarea data-q="Ask: E"></textarea></div>' + chr(10)
        + '<div class="box" data-explain="L"><p data-role="why">Why it matters for your forecast. ' + P_LONG
        + "</p>" + chr(10)
        + "  <ul><li>" + P_LONG + "</li><li>" + P_LONG + "</li><li>" + P_LONG + "</li></ul></div>" + chr(10)
        + '<div class="box"><p>Unmarked theory.</p>' + DISPLAY + " y = x " + BSL + "]</div>" + chr(10)
        + "</body></html>" + chr(10))


def selftest() -> int:
    import contextlib
    import io

    d = tempfile.mkdtemp(prefix="check_explanations_selftest_")
    ok = True
    try:
        res = {}
        for name, html in (("good", GOOD), ("bad", BAD_S2), ("misc", MISC)):
            p = os.path.join(d, name + ".html")
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(html)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc, _fails, blocks, text = check(p)
            res[name] = (rc, buf.getvalue(), blocks, text)
        rc, out, blocks, text = res["good"]
        src = text[blocks[0].start:blocks[0].end] if blocks else ""
        if rc != 0 or "FAIL" in out or "WARN" in out or len(blocks) != 1:
            ok = False
            print("selftest: S1-shaped block (why, example, formula, takeaway) should pass:" + chr(10) + out)
        elif not (src.startswith('<div class="box" data-explain="S1">') and src.endswith("</div>")):
            ok = False
            print("selftest: block source slice is wrong: " + repr(src[:40]) + " ... " + repr(src[-40:]))
        rc, out, _, _ = res["bad"]
        expect = ['"S2": (a) first paragraph has no data-role="why"', '"S2": (b) first display formula',
                  '"S2": (e) paragraphs average', '"S2": (f) not directly followed']
        missing = [e for e in expect if e not in out]
        if rc == 0 or missing:
            ok = False
            print(f"selftest: S2-shaped block rc={rc}, missing {missing}:" + chr(10) + out)
        rc, out, _, _ = res["misc"]
        expect = ['"F": (a) opens with a display formula', '"F": (b) first display formula',
                  '"N": (c) has formulas but no data-role="example"', '"M": (a) first paragraph is mostly inline math',
                  '"M": (a) first paragraph has', '"L": (e)', "% of the text is list items",
                  "1 display formula(s) outside any data-explain", '"F": (f) its .box.ask has no',
                  '"N": (f) not directly followed', '"E": (d) the example starts in the second half']
        missing = [e for e in expect if e not in out]
        unexpected = [u for u in ('"N": (e)', '"L": (c)', '"F": (e)', '"E": (f)', '"E": (b)', '"E": (e)')
                      if u in out]
        if rc == 0 or missing or unexpected:
            ok = False
            print(f"selftest: misc page rc={rc}, missing {missing}, unexpected {unexpected}:" + chr(10) + out)
        # Calibration fixtures must stay mechanically clean, so --calibrate measures only the model's judgement.
        fixtures = sorted(n for n in os.listdir(FIXTURES) if n.endswith(".html"))
        for n in fixtures:
            with open(os.path.join(FIXTURES, n), encoding="utf-8") as f:
                fx_fails, _, fx_blocks = scan(f.read())
            if fx_fails or len(fx_blocks) != 1:
                ok = False
                print(f"selftest: fixture {n} must be one mechanically clean block: {fx_fails}")
        if not any(n.startswith("good-") for n in fixtures) or not any(n.startswith("bad-") for n in fixtures):
            ok = False
            print(f"selftest: calibration needs good-* and bad-* fixtures in {FIXTURES}")
        m = VERDICT_RE.findall("1. PASS" + chr(10) + "**VERDICT: FAIL**" + chr(10))
        if m != ["FAIL"]:
            ok = False
            print(f"selftest: VERDICT parse got {m}")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("selftest: OK" if ok else "selftest: FAILED")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if argv and argv[0] == "--calibrate":
        if len(argv) == 1:
            return calibrate(1)
        if len(argv) == 3 and argv[1] == "--runs" and argv[2].isdigit() and int(argv[2]) > 0:
            return calibrate(int(argv[2]))
        print(USAGE)
        return 2
    args = list(argv)
    rev = "--review" in args
    if rev:
        args.remove("--review")
    if len(args) != 1 or args[0].startswith("-"):
        print("Explanation gate for a learn study page.")
        print(USAGE)
        return 2
    return review(args[0]) if rev else check(args[0])[0]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
