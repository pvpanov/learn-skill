# Practical skills: piano, guitar and voice, communication

The aim is a performance that is measurably better under realistic conditions. Feedback follows a
short attempt, not every movement.

## Common loop

1. **Baseline.** Record a short chunk, 4–8 bars or one phrase. For communication, one exchange.
2. **Owner first.** They name the weakest moment before seeing any report or hearing yours.
   Comparing their judgement with the measurement is itself training.
3. **Evidence.** Measured report first (`references/evidence.md`), then your reading, labelled
   *inferred*.
4. **One correction.** Pick a single change, for example: "left hand lands late on beat 3",
   "decision buried in sentence four". Then pick the drill:
   - slow it down;
   - isolate the chunk;
   - loop the transition across a chunk boundary (bad chunk boundaries become habits).
5. **Two focused takes,** then compare. If two takes are close, give the owner a blind A/B
   comparison before the numbers.
6. **Exit under changed conditions:**
   - at tempo;
   - from memory;
   - starting mid-phrase;
   - with an unexpected objection (communication).

Traps are mostly off here, except one: you misjudge a take on purpose and see whether they catch it.
Never give false technique advice.

## Piano (silent piano over MIDI)

1. Capture with `scripts/midi_capture.py` (check `--list` first; the first session verifies the
   port).
2. Compare with `scripts/midi_compare.py --ref <ref.mid> --take <take.mid> --from-bar a --to-bar b`.
   The reference is a score MIDI, or an earlier clean take at a slow tempo.
3. Work the worst bars it names: wrong, missed and extra notes, hesitations, timing outliers, tempo
   drift, velocity spread.
4. Expressive rubato shows up as timing deviation. Ask whether it was intended before calling it an
   error.

Store takes in `$LEARN_HOME/recordings/<slug>/`.

## Guitar and voice

1. Phone or interface recording, copied to the PC (cloud drive connector or USB).
2. For pitch work, record an **isolated** voice take as well. The analysis cannot separate voice from
   strummed guitar.
3. Measured: sung pitch against the target notes, onset timing and level
   (`references/evidence.md`, transcribe-performance).
4. Tone, breath support, placement and presence are not measured. Say so, and judge them from the
   owner's own A/B and their description, until a multimodal judge has been validated.

## Communication

Practise with text roleplay first. The point is phrasing and structure under pressure.

**Authenticity guard: no LLM clone** (owner, 2026-11-08; standing rule for every communication session).
The goal is better social skill with the owner's own voice kept.
- Never hand over lines to recite. Feedback names the *effect* of a line (opens a thread, closes it, edge,
  sounds like an interview) and leaves the wording to the owner. Every redo is written by the owner.
- Keep the owner's humour, bluntness, register and phrasing unless a line actually lands badly with the
  counterpart; "I'd phrase it differently" is not a correction.
- Watch for drift: if the owner's lines start sounding polished, balanced, over-qualified or assistant-like
  ("That's a great question!", tidy three-part answers), flag it as a defect like any sharp edge.
- If an example is truly needed, give 2–3 contrasting ones from different registers, never one model answer.
- Every few sessions, an outside model (Astra) reviews a session transcript for voice drift and for
  tutor rewrites that crept in; save it as `tutor-reviews/<date>-astra-comm-voice.md`.

**Setting up.** Ask for the real situation: who the other person is, what the owner wants, what they
fear will happen. Play the counterpart realistically: interrupt, deflect, object. Don't play a
pushover.

**Feedback during the roleplay** (revised after an outside review: per-turn grading trains self-monitoring):
- no tags during the scene; stay in character for 3–5 exchanges, then debrief;
- debrief separates the *observable* ("you changed topic without picking up his answer") from the *possible
  effect* ("that can feel impersonal"); one moment that mattered, then the owner rewrites that turn;
- two questions per line the owner can judge: "was my interest readable?" (tutor's call) and "would I
  actually say this?" (owner's call, final);
- vary counterparts: receptive, distracted, unavailable. Practise continuing when welcome, not only exiting;
- say the line aloud before typing it once spoken drills exist (TTS counterpart, owner records; measure
  latency, pauses, fillers only).

**Real attempts are the core; roleplay prepares them** (Sandstrom 2022, Taylor & Alden 2011):
- each real rep is a behavioural experiment: one predicted outcome → attempt → what observably happened;
- one cue–action plan per rep (implementation intention: "passing reception → greet"), never a script;
- drop one safety behaviour per experiment (e.g. withholding reactions until asked), one cue at a time;
- rejection practice = genuine, reasonable bids with uncertain outcome, never a rejection quota;
- pass = initiating, following an answer, offering something genuine, respecting disengagement; a smile,
  number or date is not the grade. Reconstructed transcripts are recollections, not evidence of feelings.

**Form by situation:**
- work: the decision or ask comes first;
- hard conversations: acknowledgement → position → ask;
- social: questions that open threads, and talking about yourself as well as asking. Don't call questions
  bad in general: follow-up questions (building on what they just said) raise liking (Huang et al. 2017,
  JPSP, d≈0.3, contested by Kluger & Malloy 2019). The "interview" defect is topic-switching questions with
  nothing of one's own;
- warmth: holding back to look safe (self-monitoring, rehearsing lines, minimal answers) reads as cold;
  dropping those safety behaviours raises felt authenticity (Plasencia et al. 2016). Use behavioural
  experiments: predict, drop one, compare;
- speaking: one idea per breath, ending on the point.

**Real-world check.** The owner tries it for real and reports back, or pastes a transcript. Compare
what they did with what they rehearsed. Real conversations count for more than roleplays.

## Languages (Dutch)

- **Correction loop: self-repair first, one error at a time** (owner f019/f020/f021; bounds from Astra,
  `$LEARN_HOME/tutor-reviews/2026-11-08-astra-dutch-2.md`).
  1. Keep the first attempt. Check that it is really unacceptable, not a valid variant.
  2. Pick one priority error: meaning-blocking errors first, then the current teaching target. At most 2 repair
     targets per response, and about 8–10 min of correction per session.
  3. Hint = location + the distinction to consider, never the answer ("in the clause after *waarom*, check the
     finite verb: embedded question"). "Word order?" is too vague.
  4. The owner rewrites the whole sentence (page: `rounds[{hint, fix}]`, the tutor appends `{hint}`). Each hint
     ends with "rewrite the whole sentence"; a described fix ("verb first") counts as the right idea, but still
     ask for the sentence.
  5. Partial progress earns one stronger hint and one more rewrite (at most 2 attempts per error). If the owner lacks
     the construction or makes no progress, give it.
  6. Then show the minimal corrected sentence (changed words in bold) and 1–2 lines of why.
  7. One quick check per distinct target: a new carrier, model hidden, 30–90 s (`check{q, answer, verdict, ok}`).
  Correct directly, with no hint, for: unfamiliar fixed expressions, typos outside the target, constructions not
  yet taught, and a repair that failed within the bounds. One "ready" covers the whole batch. If feedback lands
  after the session, the repair moves into the next session's focused block.
- **Check schedule** (replaces the 1/3/7/14/30 ladder for language): immediate check = "immediate transfer";
  next session (24–48 h) a cold, short production before notes; about 1 week later in another topic or format;
  about 3 weeks later inside a communicative task. Add a day-3 check only after a failed or hint-dependent
  next-day check. A failed immediate check: explain the contrast, no near-identical items, and an easier cold
  attempt next day. Spontaneous correct use elsewhere can replace a scheduled check. Cold retrieval takes about 5 min per session.
  Record outcomes as independent / after hint (repair, not a pass) / looked up (assisted) / target not observed.
- **Drills run on a page, not in chat** (owner, 2026-11-08). The language drill-book artifact
  (source `topics/<slug>/drill-page/`)
  keeps items in its db collection `items` (id `<date>-b<batch>-<nn>`; fields `session`, `batch`, `n`, `en`,
  `answer`, `lookedUp`, `lookedUpWhat` (the owner's note of what they looked up; copy it into `unknowns.md`), `fb{corrected, alt[], why[], tags[{t,k:ok|bad|warn}]}`, `thread[{q,a}]`). The tutor
  adds a batch with `ArtifactData batch` (no answer field, no pattern tags on open items, since a tag would reveal the target).
  Each open answer has its own **Submit to tutor** (shared `assets/submit-to-tutor.js`, 2026-11-09): it saves the answer
  to the db and posts it to the item's comment thread, which notifies the watching tutor; Ask, Submit fix and Answer
  notify the same way. Its label is the item's `review` id, else a `label` field (set `label: "complaint"` etc. on
  non-review items), else the doc id. The batch "Submit answers" + "ready" still works. The tutor reads, then writes
  `fb` and answers each open `thread` question. Publish with `files` + `capabilities: {db: <its rules>, comments: {}}`.
  `**x**` marks changed words, `*x*` marks Dutch in running text.
  The page shows only open work (owner, 2026-11-08). When a session's items are graded, or an open repair is
  covered by a scheduled review, export them to `topics/<slug>/sessions/<date>-drill-page.json` and delete them
  from the db; the errors log and review items keep the patterns.
- **Task instructions sit below the task's level** (owner, 2026-11-08: the dense stairwell prompt was not understood).
  Write situation and task prompts in short sentences, one fact each, plus 2–3 frame phrases (greeting, a proposal
  opener). Don't translate or gloss the whole prompt (owner, 2026-11-08): the owner asks about what they don't know
  through the page's question box, which every open item has. Each unknown word, phrase or structure goes into
  `topics/<slug>/unknowns.md` and comes back in a later task: what they don't know yet is material, not a failure.
- **Don't correct acceptable Dutch.** Before calling something an error, check that it isn't an acceptable
  alternative or a style preference. Mark optional improvements as optional; never log them as errors (Sol,
  `tutor-reviews/2026-11-08-sol-dutch.md`).
- A free answer that doesn't use the target is "no diagnostic opportunity" unless the task really called for it.
  Only count avoidance when the construction was the natural choice.
- Grade the target pattern separately from unrelated slips. A response that avoids the target is "not
  observed", not a pass (Astra, `tutor-reviews/2026-11-08-astra-dutch.md`).

**Delivery.** Delivery needs audio. Until it's validated, judge content and structure from text,
and judge delivery only from metrics (pace, pauses, filler words) if a transcript with timestamps
exists.
