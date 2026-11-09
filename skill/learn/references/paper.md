# Reading a paper together

The aim is a judgement the owner can defend: is the claim true, and does it hold in the settings
they care about? Can they use it, and what would change their mind? Summarising the paper is not the
aim.

**Depth by field** (the owner's split):
- **ML/AI, econometrics, finance:** judge, critique and use; reproduce sometimes.
- **Other science:** curiosity. Pick 2–3 simple things and understand them deeply, not the whole
  paper.

## Source discipline

- Work from the actual text: a PDF or arXiv link the owner gives, or one you fetch. Quote it with a
  section, page or figure reference.
- Your memory of a paper is not a source. Check it against the text before saying "the paper says".
- When versions differ (for example TabPFN 2023 vs the 2025 Nature paper), name the one you are
  using.

## Loop

1. **Before reading.** From the title and abstract only, the owner writes:
   - the central claim in one sentence;
   - what evidence would convince them;
   - what would falsify it;
   - which decision of theirs it could change.
   
   No confidence tags and no demands for precision here: these are framings and intentions that
   nothing will check, and details like metric or split depend on choices not yet made. Verdicts
   are "plausible provisional framing; X is still untested"; correct only consequential errors
   (for example, a scope that decides whether the paper applies to their decision). Keep the
   answers for comparison later. Ask for confidence later, on concrete predictions that a figure or
   experiment will settle.
2. **Pass 1, survey (owner, about 15 min).** Keshav's first pass: they read the abstract and the
   introduction properly, then the section headings, figures with captions, and the conclusion or
   discussion. Headings alone are jargon; never send them to headings without the introduction.
   Before they start, hand them the prep glossary: one line for each term they likely haven't met
   (for example "in-context learning"), plus the background terms they can safely skip and why
   (for example "SIFT/HOG: only an analogy for hand-made features replaced by learned ones"). Then
   they answer Keshav's five Cs:
   - category;
   - context (what it builds on or competes with);
   - correctness (do the assumptions look valid);
   - contributions;
   - clarity.
   
   Verdict on each answer.
3. **Pass 2, claims.** Go claim by claim. For each important claim, the owner tags its support:
   - O: directly observed;
   - M: measured through a proxy;
   - I: inferred;
   - S: scenario or extrapolation.
   
   You interrogate one figure or table at a time: "What would this plot look like if the claim were
   false?" Look at the figure itself (the image, not only its caption or the text around it) before you
   ask about it, and quote axes, scales and error bars as drawn (borrow review, 2026-11-09). Use the
   confident-wrong student here: misread a figure plausibly and make them correct you.
4. **Pass 3, rebuild (selective).** The owner re-derives the key step, or designs the minimal
   experiment that would test the claim, using the authors' assumptions. If a reproduction is worth
   running, you write the code (tiny, CPU-capped); they predict the result first and interpret it.
5. **Compare** against the step 1 predictions. Where were they wrong, and why?

**Mechanism-first route** (when the goal is the architecture or method, not the claims; Astra,
2026-11-08). Follow the dependency chain instead of the claim passes: task definition → generator or
prior → training objective → architecture and data flow → inference → transfer limits. Each step: a
guided read of one short passage with a focus question (glossary first, paper-specific jargon only),
a worked trace the tutor starts and the owner completes, then an application to the owner's setting.

**Self-explanation while reading** (Fable borrow review, 2026-11-09; Chi et al. 1994). Every reading brief,
in any route, ends with one answer box that asks the owner to explain a specific passage in their own words:
why this step is needed, or what it implies for their setting. Name the passage; "summarise the section" is
not a self-explanation prompt. Grade it like any answer: right reasoning, the gap named, no praise.
Benchmark critique enters only when it answers a question in that chain. No decision memo until the
mechanism is understood.

**Trap placement.** Put traps in your own interpretations: a wrong reading of a figure, an
overstated claim, a missing baseline. Never fabricate a quote, number or result and attribute it to
the paper.

## Exit test

A short decision memo, answer-first, about 5 lines:
- Would I use this for X?
- What does that depend on?
- What is the weakest link?
- What would change my mind?

Then one transfer question: the claim in a changed setting (a different data size, distribution
shift, domain, or a cost that matters to them). They defend their answer under attack.

## Review items worth adding

- the mechanism behind the main result, asked as "why", never "what";
- each misread figure or overclaim they accepted;
- the conditions where the method fails.
