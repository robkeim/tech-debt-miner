# A file named twice keeps its later slot and scores 0 there

Accepted 2026-11-24. Decided in #75. Clarifies the "What is scored" paragraph of [ADR 0005](0005-scoring-pre-registration.md); everything else in ADR 0005 stands. Like ADR 0005, it is frozen when merged to `main`, which must happen before the first scored Run.

## Decision

- A file named more than once counts once, at its first position. Each later occurrence keeps its slot and scores 0 there, so the files after it do not move up.
- This is the same rule ADR 0005 already gives a file that does not exist at the Pinned SHA: it scores 0 and still uses its slot.
- The rule applies to both rankers, so a ranker gains nothing from repeating a file.
- Each scored Run's Manifest records this ADR's commit SHA beside ADR 0005's.

## Why

- ADR 0005 says a duplicate "counts once, at its first position" but does not say whether the later slot closes the gap. Without a rule, two implementations would score the same ranking differently.
- Keeping the slot makes a duplicate the same as any other wasted slot (a file with a Label of 0), so the metric has one rule for waste instead of two.
- Closing the gap would let a ranker pad its list with repeats at no cost, and would make the score depend on whether the ranker's output was deduplicated before scoring.

## Alternatives rejected

- **Drop the later occurrence and shift the rest up.** It treats an LLM's repeated file as free, and it makes position depend on a cleanup step outside the scorer.
- **Reject a ranking that contains duplicates.** One malformed line would discard a whole Run.
