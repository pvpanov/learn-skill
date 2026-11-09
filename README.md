# learn: an AI tutor skill for coding agents

A skill for Claude Code (and other agent harnesses that read `SKILL.md`) that tutors one learner
through research papers, concepts and practical skills. It explains before it tests. It has the learner
reason and predict, gives immediate feedback on the core idea, and brings recent material back with
spaced review (FSRS-style). A small stdlib script owns the state, so ids, due dates and schedules are
not invented by the agent.

It grew out of daily use. Most rules carry a dated note of the learner feedback that produced them,
and `references/recurring-feedback.md` records which rules are now enforced by a script rather than prose.

## Layout

| Path | What |
| --- | --- |
| `skill/learn/SKILL.md` | The tutor contract: session start, rules, explanation format, traps, close, prep gate. |
| `skill/learn/references/` | Per-type playbooks (`paper.md`, `concept.md`, `practical.md`), `evidence.md` (what tools can and cannot judge), design notes and the feedback ledger. |
| `skill/learn/scripts/learn.py` | State CLI: topics, booked sessions, review items with spaced scheduling, feedback with repeat detection, prep and ready checks. Stdlib only; `python learn.py selftest`. |
| `skill/learn/scripts/check_page.py`, `check_explanations.py`, `render_check.py` | Pre-publish gates for HTML study pages: script sanity, one Submit per answer box, and an "example first, textbook exposition" check on explanation blocks. |
| `skill/learn/scripts/midi_compare.py`, `midi_capture.py` | Piano practice: compare a MIDI take with a reference (wrong, missed and extra notes, hesitations, tempo drift). |
| `skill/learn/assets/` | Study-page skeleton and the shared per-answer "Submit to tutor" script for claude.ai artifact pages. |
| `labs/kaggle/` | Blind-baseline bench (XGBoost vs TabPFN v2) from a spec written before the run; OpenML finder; dataset shortlist. |
| `labs/tabpfn/` | Small TabPFN experiments: smoke tests, row-order invariance, random vs time split, scaling past 10k rows, fine-tuning smoke. |
| `labs/stateful-nets/` | How far back a tanh RNN's gradient reaches, against the spectral radius. |

## Install

```powershell
git clone https://github.com/pvpanov/learn-skill
Copy-Item -Recurse learn-skill/skill/learn "$HOME/.claude/skills/learn"
$env:LEARN_HOME = "$HOME/learning"   # state folder; this is also the default
python "$HOME/.claude/skills/learn/scripts/learn.py" init
```

Then ask the agent to "learn <topic>". State (profile, topics, reviews, feedback) lives in `$LEARN_HOME`
as small JSON, JSONL and Markdown files. None of it is in this repo.

## Requirements and what is tied to the original setup

- `learn.py`, `check_page.py`, `check_explanations.py` and `midi_compare.py` need only Python 3.10+.
  `check_page.py` also uses Node (`node --check`), and `render_check.py` uses headless Chrome or Edge
  (`LEARN_CHROME` overrides the path).
- Study pages are claude.ai artifacts that use the comments capability. Without them, run the checks in chat.
- `check_explanations.py --review` and the prep gate's outside teaching review call a second model through a
  local `ai ask` front door that is not included. Use another reviewer, or skip it with
  `learn.py topic prep ... --override "<why>"`.
- Calendar sync through the Google Calendar connector is present but switched off in `SKILL.md`.
- The guard scripts named in the docs (`gpu-guard.mjs`, `cpu-guard.mjs`) belong to a separate skill. Any
  check that keeps CPU and VRAM headroom will do.
- References to `profile.md`, `feedback.jsonl`, `tutor-reviews/` and topic files point into the learner's own
  state folder. They are not published.
- Labs need `torch`, `tabpfn`, `xgboost`, `catboost`, `openml`, `pandas`, `scikit-learn` and `scipy`. TabPFN v2
  weights are used deliberately: later versions carry a non-commercial licence.

## Licence

MIT, for the code and text in this repository. Third-party models and datasets keep their own licences.
