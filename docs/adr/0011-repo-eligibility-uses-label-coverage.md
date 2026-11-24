# Target repo eligibility is gated on Label coverage, not a Fix commit count

Accepted. Decided in #60 while freezing the Target repos. Amends the size-and-history row of [ADR 0006](0006-target-repos-and-cutoff-dates.md); everything else in ADR 0006 stands.

## Decision

The rule "at least 25 candidate Fix commits per 6-month window" is replaced by the rule ADR 0005 already uses for scoring:

- A Target repo is eligible if, in the primary window (2026-07-01 to 2026-12-31), at least 10 files have a Label of 1 or more under the primary, tracker-confirmed Label ([ADR 0004](0004-label-is-future-fix-proneness.md)).
- The count is taken after the window closes, with the full Label rules (path filtering, exclusions, rename following, the fix-size cap N). Before then, the approximate count in the ADR 0006 frozen table stands in for it.
- The other ADR 0006 criteria are unchanged: 100 to 1,500 Python source files, at least 12 months of history before the earliest Cutoff date, the ADR 0004 hygiene filters, the star bands, and selection blind to any LLM or baseline result.
- Exploratory windows are not gated. A repo below 10 files in an exploratory window is reported as excluded there, as ADR 0005 already says.

## Why

- **One definition of "enough data".** ADR 0005 drops a repo and window with fewer than 10 files with a Label of 1 or more. A separate Fix commit count only approximates that, and it can disagree with it in either direction: `pandera` has 20 tracker-confirmed Fix commits but 49 files with a Label, while a repo whose fixes all touch the same few files could pass a commit count and still be not scoreable.
- **The old rule excluded almost everything.** In the scan for #60, about 10 of roughly 85 repos reached 25 tracker-confirmed Fix commits, because most fixes cite only their PR number. The ADR 0004 Label ignores bare numbers, so a commit count that counts only tracker-confirmed fixes is much harder to meet than the 10-file rule.
- **It widens the replacement pool without touching the Label.** `xarray` (13 files so far), `PennyLane` (24) and `zarr-python` (9, borderline) become eligible. The frozen list of 8 is unchanged, since every repo on it already clears the 10-file rule.

## Alternatives rejected

- **Keep 25 and replace `pandera` and `pymc-marketing`.** Two repos were already projected rather than measured, and the replacements were weaker on label coverage. It would also keep a rule that does not measure what scoring needs.
- **Count keyword-matched fixes toward the 25.** Many more repos pass, but the count then measures the sensitivity set, not the primary Label.
- **Resolve each PR to the issues it closes, so more fixes become tracker-confirmed.** It changes the Label and adds the PR expansion ADR 0004 rejected. It stays open as a possible reported sensitivity check, not as the primary Label.

## Known limits

- **The threshold is a convention.** 10 files is ADR 0005's minimum, not a statistical power calculation. A repo that barely clears it contributes a noisy score, and the bootstrap over repos treats it like any other.
- **The check is circular in time.** Eligibility is confirmed only after the window closes, so a repo can drop out after being frozen. The replacement rule is: recount on 2026-12-31, replace any repo below 10 files with another chosen blind and recorded in an amendment, and do this before the first scored Run.
- **Pre-close counts are approximate.** The frozen table's numbers have no N cap and no rename following, so the final count can differ.
