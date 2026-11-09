# Recurring feedback: the ledger

Owner, 2026-11-09: "don't just patch this particular piece - you need to repair the lane too essentially (so we
don't keep circling over these)". The pattern was: a correction came in, a prose rule went into SKILL.md, the row
was marked resolved, and the same failure came back.

This file is the ledger. It has one row per underlying rule, built from every row of
`$LEARN_HOME/feedback.jsonl`. Each feedback row carries its rule slug in `rule`, and `repeat_of` when the
rule had been given before. `python learn.py feedback rules` prints the live counts. When a resolve names a check,
update the matching row here.

How to read the "Enforcement now" column:
- **script**: a check fails the work mechanically.
- **template**: the shared page asset or skeleton builds the behaviour in.
- **checklist**: the rule is printed in `learn.py status` under "session-start checklist" (`SESSION_CHECKLIST`)
  every session. It is used for judgement rules that no script can check.
- **prose**: SKILL.md or a reference file only.

Gate: `topic prep --status ready` runs `learn.py ready-check` and refuses on any FAIL. ready-check runs these:
- `prep-check`;
- `check_page.py`;
- `check_explanations.py`, skipped with a WARN if it crashes;
- `render_check.py`;
- a check that `tutor-reviews/<date>-astra-prep-<slug>.md` exists.

`status` runs `prep-check` for every booked session.

## Rules given 2 or more times

| Rule (slug) | The rule | Feedback (date) | Times | Enforcement now | Gap |
| --- | --- | --- | --- | --- | --- |
| `page-submit` | Every answer the owner gives, due reviews included, goes in its own page box. Each box (each sub-question) has its own Submit to tutor. Notifications are armed at start, and the tutor reads the threads on every owner message. This holds learning-wide. | f024, f026, f033, f043 (11-08); f047, f051, f053, f054 (11-09) | 8 | **script**: `check_page.py` (submit script present, unique `data-q`, multi-textarea box, parts); `render_check.py` (every `textarea[data-q]` wired by the shared script, one Submit each, no script errors); `prep-check` (each due review is named on the page or as a page item in the key; FAIL if the key routes it to chat; FAIL if there is no page). **template**: `assets/submit-to-tutor.js`, `assets/page-skeleton.html`. **checklist**: arm notifications at start, read threads on every message (f053). | Arming (republish + watch) and reading threads are session actions, not checkable. On 11-09 render_check fails the tabpfn page: it has its own per-page Submit, not the shared script. |
| `scheduling` | Sessions happen when the owner has time: spare time means the next prepared session, now. A pulled-forward session uses its key and page. Past sessions are dropped, not packed. | f022, f023, f035, f036, f037, f038 (11-08) | 6 | **script**: `learn.py topic next` keeps several bookings and drops sessions whose start has passed (f023, f037). **checklist**: spare time / "do it now" (f035, f036). | Owned by a separate scheduling redesign (f036 to f038 still open). Not duplicated here. |
| `language-correction` | Dutch corrections go: hint, then the owner's own fix, then the corrected sentence (changes in bold), then why, then a quick check on the same principle. Task prompts are short A2, with no whole-prompt translation. | f019, f020, f021, f029, f031 (11-08) | 5 | **template**: the drill page (`topics/dutch/drill-page/`) has hint, a fix-it box and a `check{}` block per item. **checklist** (dutch). | Prompt reading level and the "no translation" rule are judgement; nothing checks the prompt text. |
| `example-first` | Every block of theory opens with why it matters and a running concrete example. The theory is interleaved, in connected prose (textbook exposition, not factoids). Proofs are given only on request. | f041, f042 (11-08); f057, f058, f060 (11-09; f060 = "prep ... not a factoid collection", Astra review) | 5 | **script**: `check_explanations.py`, run by `check_page.py` and by ready-check (why-hook first, example before the first display formula, no list-heavy or compressed blocks; `--review` sends blocks to a model). ready-check requires the Astra teaching review file. **checklist**: also in chat. | Explanations given in chat are not checked. The Astra file is checked for presence, size and a "revis" section; its quality is not judged. |
| `verdict-core-idea` | The verdict is on the core idea. A correct answer gets "right". Sharpen only with something non-obvious and goal-relevant. Never grade wording. | f001, f006, f014, f015 (10-31) | 4 | **checklist** | Judgement; can't be mechanised. No repeat since 10-31. |
| `verify-claims` | Check technical claims before stating them, and label estimates as estimates. | f013, f016, f018 (10-31); f045 (11-08) | 4 | **checklist** | Judgement. The Astra prep review covers prepared explanations, not live chat claims. |
| `explain-and-verify` | An explanation is followed by a check that uses the concept. Side questions become mini-sessions on the page. | f009, f010 (10-31); f040 (11-08) | 3 | **script** (shape only): `check_explanations.py` (Ask field after each block; other agent). **prose**: SKILL.md Explain-and-verify. | No script verifies that a check box follows each explanation block (this belongs in `check_explanations.py`, the other agent's domain). |
| `clickable-sources` | Whenever a step sends the owner to a source, give a bare `file:///` URI with PDF page numbers in chat. | f004 (10-31); f039 (11-08) | 2 | **script**: `prep-check` fails a paper key with no `file:///...pdf` URI to paste. **checklist**. | Whether the URI is actually pasted in chat is a session action. |
| `feedback-loop` | Act on feedback unprompted, in the same turn, without blocking the chat. A repeat needs a check. | f005 (10-31); f050 (11-09); f059 (11-09, this repair) | 3 | **script**: the `learn.py feedback add` repeat detector (rule tag, text similarity as a hint), and `feedback resolve` refuses a repeat without `--check` (existing file) or `--no-check-possible`. **checklist**. | Tagging (`--rule`) is optional, because callers that predate it must keep working. Wording overlap alone is weak (calibration below). |
| `paper-glossary` | Paper and concept keys carry a glossary that is handed over before reading, including the terms to skip. | f007, f008 (10-31) | 2 | **script**: `prep-check` fails a paper or concept key without a glossary. | Glossary content (and the skip list) is not checked. |
| `fair-checks` | Judge against what the owner had been told when they answered. A check must be clear about what it compares. | f011, f017 (10-31) | 2 | **checklist** | Judgement. |
| `reconcile-open-work` | The page and the key show only open work. Answered items are marked done and dropped, reconciled with log.md. | f028 (11-08); f049 (11-09) | 2 | **script**: `prep-check` fails if `log.md` is newer than the key, and warns on review ids in the key that are no longer due (not marked deferred/done). **template**: the drill page archives graded items to `sessions/`. | Page boxes for answered checks can't be detected without reading the db and threads. |
| `review-timing` | Review items come only from material the owner worked through. No review falls due less than 2 days after a check on the same material. | f027 (11-08); f048 (11-09) | 2 | **script**: `review add` sets first due at 3 days (2 with `--error`). The scheduler floor `MIN_GAP_DAYS = 2` means a graded review never comes back the next day. `prep-check` fails a due review last checked less than 2 days before the session, and `review defer` moves it. `status` lists "too soon" rows. | "Worked through" (f027) is judgement (checklist, paper). Same-material links that are not the item's own history (a page check yesterday on material an old review covers) are not detected. |
| `drill-page-fields` | Every open drill item has a question box, and "looked up" has a text field. | f030, f032 (11-08) | 2 | **template**: the drill page v6/v7. | Not repeated since; the template holds it. |
| `communication-authentic` | Communication practice gets no per-turn tags and no LLM-polished lines; the owner writes the redos. | f044, f046 (11-08) | 2 | **checklist** (communication). **prose**: practical.md authenticity guard. | Voice drift is judged by a periodic Astra review only. |
| `slot-readiness` | The slot is for learning. Every page or tooling defect is caught in prep. "Ready" means the gate passed. | f055, f056 (11-09) | 2 | **script**: `topic prep --status ready` runs `ready-check` and refuses on a FAIL. `--override "<why>"` is recorded on the session and shown by `status`. **checklist**. | An override bypasses the gate; status shows it, but nothing blocks the slot. |

## Rules given once (prose or checklist; watch for a second time)

| Rule | Feedback | Enforcement |
| --- | --- | --- |
| `specifics-later`: ask for specifics only when the next step needs them | f002 (10-31) | prose (SKILL.md Rules) |
| `confidence-ratings`: confidence only on checkable claims | f003 (10-31) | prose |
| `owner-sets-pace`: never schedule the owner's breaks | f012 (10-31) | checklist |
| `logistics-at-close`: process changes get one line at the close, no paths to open | f025 (11-08) | checklist |
| `tutor-writes-summary`: no owner recap at the close | f034 (11-08) | prose (Close 1) |
| `page-js`: no raw invisible or line-separator characters in page JS | f052 (11-09) | script: `check_page.py`, `render_check.py` |

## Repeat detector calibration (2026-11-09)

The detector scores the set-cosine of stemmed content words over f001 to f058:
- True repeats score low: f041/f042 0.20, f039/f004 0.16, f057/f042 0.15.
- An unrelated pair scores higher: f052/f043 0.29.

So the `--rule` tag is the reliable signal. Text matching auto-flags a REPEAT only at 0.34 or more, and from 0.20
it prints the closest row as a hint to tag. A deterministic check of meaning is not possible with the standard
library alone. If misses recur, make `--rule` required on `feedback add`; SKILL.md Close step 6 would then need the
flag too.
