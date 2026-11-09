# Concepts and mechanisms

The aim is a causal model the owner can run in their head. They should be able to predict what
happens in a case they have not seen, and say why.

## Loop: predict, observe, explain

1. **Elicit their model first.** Before you teach anything, the owner sketches how they think it
   works: a causal chain or diagram in words, plus one prediction with confidence. Misconceptions
   surface here; that's the point.
2. **Contrasting cases.** Give two situations that differ in one factor and have them predict both
   outcomes. Contrasts expose which variables their model actually uses.
3. **Observe.** Show the outcome in the cheapest form that is still honest:
   - a Fermi estimate they compute;
   - a real data series;
   - a toy simulation that you write and run.
   
   They predict before they see it.
4. **Explain the gap.** If the prediction failed, name the misconception and the correct idea in the
   same breath, side by side. Revision needs both active at once. Then they repair their model in
   their own words.
5. **Fresh case.** They predict a new situation without help. Getting it right means the repair
   held.

## Building things

- **You write the code.** The owner chooses what varies, what stays fixed, what counts as evidence,
  and what result would surprise them.
- **Keep it toy-sized:** about 30–80 lines, fast to run, with thread caps set, and the guard check
  before anything long (see SKILL.md, Machine).
- **Real data.** Name the source and its measurement clock: when a value was known versus when it was
  published. For markets in particular:
  - look-ahead bias;
  - survivorship bias;
  - treating price action as evidence of a particular flow.
  
  Those three are the classic self-deceptions.
- **Pitfall experiments are worth more than tutorials.** "Where does this method break, and how
  would I notice?" For example: where does TabPFN degrade, or how does leakage inflate a score?

**Trap placement.** Put traps in your explanations, or in a plausible but wrong causal story you
offer. Never put them in data or simulation output presented as real.

## Exit test

Pick one of these:
- **Transfer:** apply the mechanism to a system the material didn't cover.
- **Teach-back under attack:** the owner explains it; you attack the weakest link until it holds or
  breaks.

## Review items worth adding

- the misconception, phrased as a prediction question whose naive answer is wrong;
- the conditions under which the mechanism reverses or stops mattering.
