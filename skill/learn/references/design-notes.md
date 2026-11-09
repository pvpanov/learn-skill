# Design notes

These notes record why the skill is shaped this way. Read them when you change the skill, not when
running a session.

## Owner interview (2026-10-29)

- **Saved work.** Save the owner both busywork and illusion-of-learning work.
- **Traps.** All four kinds are wanted. Feedback on a wrong statement must be immediate. Coach the
  form of the answer as well as its content.
- **What works:** explaining, debate, and using the idea beyond the material. What fails:
  - passive video;
  - goal-less reading;
  - over-hand-holding;
  - re-testing what is already solid.
- **Time.** Weekdays: medium sessions morning and evening. Weekends: long sessions, morning and
  evening.
- **Papers.** ML/AI, econometrics and finance get depth. Other science is read out of curiosity.
- **Code.** The owner doesn't want to write code, but does own the methodology and data reasoning.
- **Bad days:** shrink the session, don't skip it.
- **Calendar.** Per-topic calendar events. Chosen against both reviewers' advice; the owner's
  reason was that the ICS check-in, never added to Google Calendar, got skipped.
- **Build.** Full v1 at once, with a feedback mechanism. First pilot: a paper (TabPFN). Then one
  pilot per category.

## Research basis (web, 2026-10-29)

- **Desirable difficulties** (Bjork): retrieval, spacing and interleaving hurt short-term performance
  and help long-term learning. Interleaving is weaker for complex material.
- **Bastani et al., PNAS 2025.** Unguardrailed GPT-4 raised practice scores 48% but cut later exam
  scores 17%. A tutor holding the solution and the common mistakes, giving hints only, mostly
  avoided the harm. Hence "prepare the key privately".
- **Productive failure** (Kapur 2021 meta-analysis). Attempting before instruction helps conceptual
  understanding and transfer. Hypercorrection: high-confidence errors, once corrected, are
  corrected best.
- **Conceptual change** (refutation texts, the KReC framework). The misconception and the correct
  idea must be active together. Surprise predicts revision. Hence predict, observe, explain.
- **Expertise reversal** (Kalyuga; Tetzlaff et al. 2025 meta-analysis). Guidance that helps novices
  hurts experts. Matching to "learning styles" has about zero effect.
- **Motor learning.** Chunked practice beats whole-piece repetition. Bad chunk boundaries persist as
  habits.
- **Keshav's three-pass paper reading.** Communication training: roleplay with feedback and a
  debrief. The evidence is small-scale, and simulated talk has an authenticity limit.

## Reviews of the design (2026-10-29)

Fable 5.1 and GPT-6 Astra reviewed the design independently. Both said:
- one skill, with a reference file per type;
- small local state;
- two scripts;
- cap the traps;
- cut tutor-written notes;
- no phone page in v1;
- defer Gemini until a validated need;
- validate through real use before building more.

Both flagged an earlier precedent: a careful curriculum that was never used.

Astra contributed:
- one merged review/error record;
- never planting errors in technique or safety advice, and never fabricating quotes;
- "decision first" is not universal (hard conversations).

Fable contributed:
- "If fewer than three of four pilots happen within a week, stop building; the skill is not the
  bottleneck";
- tag each practical judgement as measured or inferred.

## First real session (2026-10-31): the owner's critique

In the TabPFN pre-reading step the tutor graded open-ended framings like an exam: it marked a
missing "10k samples" scope and the shorthand "universal approximator" as errors, asked for a
metric and split before any dataset existed, required confidence tags on intentions, and added a
trivia guess. The owner: "you're demanding specificity WAY too early"; "wording corrections are
good, just not the core"; "I can be convinced that what you do is useful, but you need to explain".

GPT-6 Astra reviewed it: the owner is mostly right; the failure was misalignment (mixing
comprehension, hypothesis generation, design and trivia, graded against unstated standards).
Evidence: prequestions help even when answered wrongly (Richland et al. 2009), so attempt-first
stays but incomplete foresight isn't penalised; hypercorrection (Butterfield & Metcalfe 2001)
covers checkable factual errors, not mandatory confidence on framings; added guidance becomes
redundant with expertise (Kalyuga et al. 1998). Astra also kept two points: scope matters for the
work decision (say it briefly), and the transfer warning is worth keeping. Resulting rules: prompt
kind, core-idea verdicts, no wording grading, specifics only when needed, confidence only on
checkable claims, one follow-up with a payoff, explain the purpose when asked.

## Language lane: Dutch (2026-11-08, Astra ×2 + Sol)

Reviews: `$LEARN_HOME/tutor-reviews/2026-11-08-astra-dutch.md`, `…-astra-dutch-2.md`, `…-sol-dutch.md`.
The owner delegated pedagogy and chose self-repair first, one error at a time. Sol preferred correction-first, but its own
evidence (Brown, Liu & Norouzian: direct ≈ indirect written CF on average) leaves the owner's preference
decisive. Astra bounded it (Lyster & Ranta 1997; Lyster & Saito 2010; Bitchener & Knoch 2010): at most 2
attempts per error, direct correction for unknown forms and typos. Spacing per Kim & Webb 2022: an immediate
check, then next day, ~1 week, ~3 weeks; no fixed ladder. Translation is a small diagnostic, not the main
drill; the week is a format portfolio (`$LEARN_HOME/topics/dutch/plan.md`). Rules live in
`practical.md` → Languages.

## TabPFN session 2 (2026-11-08): Astra review (`tutor-reviews/2026-11-08-astra.md`)

The session opened with two cold reviews on material the owner never worked through, with no
re-entry, and kept going after signs it wasn't working; the owner called it not useful. Astra: the
governing rule was wrong (testing as the default, teaching as the exception). Changes made: new
opening contract (understanding before retention); attempt-first is conditional; due reviews are
selected for the day's goal (~5 min) after orientation; invalid items are dropped, not failed;
feedback is informative, verdicts not compulsory, counterexamples only for specific misconceptions;
traps only where the owner can catch them, none planned by default; review items need a learning
opportunity plus evidence; a mechanism-first route for papers (`references/paper.md`); checks on a
page built in prep; logistics kept out of the slot. Kept against Astra's advice: none; its "delayed
retrieval after success" was reconciled with the owner's rule (recent material returns until
questioning shows it is known well).

## Borrowed from existing tutor skills

- **sigma** (`github.com/sanyuan0704/sanyuan-skills`): counterexamples for misconceptions; a
  discrimination exit test; recording profile patterns only after two sessions; interleaving.
- **teach** (`github.com/mattpocock/skills`): ground everything in the owner's why ("what do you
  want out of this"); "never trust parametric knowledge" (paper source discipline).
- **claude-tutor** (`github.com/kirilxd/claude-tutor`): a script owns the schema, because agents
  invent field names.

Not borrowed:
- full curricula and roadmaps, and gating on 80% mastery: the flows lesson, and the unit here is a
  session;
- (superseded) HTML lesson generation was rejected as "reading material"; study pages are now built in
  prep with per-answer Submit boxes and gated explanations;
- (superseded) SM-2 ease factors were rejected for a fixed 1/3/7/21-day ladder; the scheduler is now FSRS
  with again/hard/good/easy grades.

### Second harvest (2026-11-09)

148 ideas from 15 public tutor repos, filtered by two outside model reviews (Astra and Fable; the
candidate list and the reviews are private notes, not published).
Adopted:
- grade the unaided answer on four grades; a hint-dependent recall is `again` (both reviewers; Astra's form);
- `review result --retry`: the repair after reteaching is history, not a review (Astra);
- one source for numbers: `DOC_PINS` in `learn.py selftest` pins the doc phrases to the constants, and
  explicit first-due dates obey the `MIN_GAP_DAYS` floor unless `--allow-soon` says why;
- `check_explanations.py --calibrate`: the DeepSeek checklist reviewer measured on labelled fixtures;
- an accuracy item in the DeepSeek checklist and the Astra prep checklist;
- review fingerprints (`learn.py stamp`): ready-check fails a block changed since its Astra review;
- prose: completion problems (fading), generated numbers come from code that ran, slip vs misconception,
  look at the figure image, grade the answer not the claim, a self-explanation box per reading brief.

Deferred ideas wait for named triggers; misgrade correction (`review amend`) waits for an actual
misrecorded grade.

## Out of scope / later

- **A phone page.** Revisit after the check-in freeze ends (2026-11-07), and only if a session was
  skipped because the PC was out of reach.
- **Speech-delivery metrics** from timestamped transcripts.
- **Gemini 4 Argon**, gated as described in `evidence.md`.
- **Seeding the profile from ChatGPT memories.** The owner pastes ChatGPT's answer in.

## Communication design review (Astra, 2026-11-08)

`$LEARN_HOME/tutor-reviews/2026-11-08-astra-comm-design.md`. Changes in `practical.md`: no per-turn
tags (debrief after 3–5 exchanges, observable vs possible effect); real attempts as behavioural experiments
(prediction → attempt → observed); one cue–action plan and one dropped safety behaviour per rep; varied
counterparts; pass criteria on behaviour, not outcomes; "interview questions are bad" replaced by follow-up
vs topic-switch (Huang 2017). Per-turn tags were the main risk: they train self-monitoring.
