# Target repos and Cutoff dates are chosen to sit after the model's training cutoff

Accepted. Decided in #36 from the research in #35. Supplements the pre-registration in [ADR 0005](0005-scoring-pre-registration.md); the Label is [ADR 0004](0004-label-is-future-fix-proneness.md).

## Decisions

| Item | Decision |
| --- | --- |
| Model | Claude Sonnet 5.5 (`claude-sonnet-5-5`). Training data cutoff K = Jun 2026, per Anthropic's Models overview. The Manifest records K and `C - K` for every Run. |
| Language | Python only. |
| Number of Target repos | 8, so that at least 5 stay scoreable after ADR 0005's minimum-data rule. |
| Size and history | 100 to 1,500 Python source files at the Pinned SHA after path filtering (provisional until #38 fixes the prompt design), at least 12 months of history before the earliest Cutoff date, and at least 25 candidate Fix commits per 6-month window. |
| Hygiene | The ADR 0004 filters: tracker-typed bugs, no title-only squash commits, an active default branch. A repo that tracks bugs elsewhere (for example in a non-GitHub tracker) is not forced in. |
| Popularity mix | 4 well-known repos (more than 10k stars) and 4 less-known repos (1k to 5k stars). No private repos. Stars at the Pinned SHA are reported. |
| Selection | By the criteria above, chosen blind to any LLM or baseline result. The frozen list is added to this ADR before the first scored Run. |
| Primary Cutoff date | 2026-07-01 for every repo, the first day after K. The window is 2026-07-01 to 2026-12-31. |
| Exploratory Cutoff dates | 2026-01-01, 2025-07-01 and 2025-01-01. Labeled "possibly memorized", they never feed the verdict and support the pre/post-K comparison. |
| Scoring date | The first scoring, on or after 2027-01-31, is primary. A later re-score over the same window is a sensitivity check, and if it flips the direction the report says so first. |
| Label lag | The window is fixed. Issue state is read at scoring time, and the scoring date is recorded in the Manifest. A fix counts if its commit is in the window, whenever its issue closed. |
| Behavioral probe | Once per repo, the model names the buggy file from a post-Cutoff fix commit message with no repo context. Reported alongside results, never in the verdict. |
| Obfuscation | Not used, not even as a robustness check. |
| Membership inference | Not used. |
| Reporting | Every Run reports `C - K`, repo popularity and probe results, including a null result. |

## Why

- **After K, labels cannot be memorized.** A window that starts after the training cutoff contains no fixes the model could have seen. Everything it knows about the repo predates the Cutoff date, which is legitimate input. Research: #35.
- **Obfuscation adds nothing for the headline.** It only helps on windows before K, where the pre/post-K comparison and the probe already measure memorization. File paths are the ranked unit, so hiding them removes real signal.
- **Membership inference is weak evidence here.** It is near random on comparable setups, and Claude may not expose log probabilities.
- **Fixed windows, later re-scoring.** Late issue closures can miss fixes at the end of a window. Re-reading issue state later fixes that without moving the window, and naming one primary scoring date prevents picking the flattering one.
- **Popularity as a dose.** Memorization scales with duplication, so a mix of well-known and less-known repos lets the report show the LLM's lead against popularity.

## Known limits

- **One clean window per repo.** The headline rests on a single Cutoff date, so it has 8 data points at best. Fewer than 5 scoreable repos means no verdict.
- **Sonnet 5.5 only.** Results say nothing about other models.
- **Generalization.** Python only, and well-maintained repos only (ADR 0004).
- **K has month granularity.** The primary Cutoff date sits on the first day after it, and content near the boundary is sparse in training data.
- **Size range is provisional.** The 100 to 1,500 file bounds depend on the ranker's prompt design (#38) and are re-checked there.
- **ADR 0005 is already merged.** The label-lag rule is recorded here as a supplement, since no scored Run exists yet.
