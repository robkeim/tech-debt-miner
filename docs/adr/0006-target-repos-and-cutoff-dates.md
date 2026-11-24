# Target repos and Cutoff dates are chosen to sit after the model's training cutoff

Accepted. Decided in #36 from the research in #35. Supplements the pre-registration in [ADR 0005](0005-scoring-pre-registration.md); the Label is [ADR 0004](0004-label-is-future-fix-proneness.md). The "at least 25 candidate Fix commits" criterion is replaced by [ADR 0011](0011-repo-eligibility-uses-label-coverage.md).

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

## Frozen Target repos

Added 2026-11-24 from #60, as ADR 0006's Selection row requires. The choice used only repo metadata and git and issue history up to that date; no LLM or baseline result existed or was consulted.

| Repo | Stars | Pinned SHA (last default-branch commit before 2026-07-01) | Python source files | Squash share | Fix messages with only a PR number | Tracker-confirmed Fix commits | Files with Label of 1 or more |
| --- | --- | --- | --- | --- | --- | --- | --- |
| yt-dlp/yt-dlp | 210,391 | `e584a65f2a0feee0c6c363b3309e9ebd6065f6b4` | 1,070 | 0.96 | 0.40 | 30 | 25 |
| celery/celery | 29,258 | `3afde800618741a9e5352d84f3741f3c9b448c2f` | 202 | 0.91 | 0.56 | 49 | 30 |
| python/mypy | 20,734 | `47f0df577f42c726f847163f9c0a15df681a8479` | 347 | 1.00 | 0.30 | 49 | 51 |
| statsmodels/statsmodels | 11,764 | `f6e07836022dcbc995bda925c50983e52f060303` | 488 | 0.01 | 0.81 | 73 | 50 |
| napari/napari | 2,813 | `f97c9aea2555a9462fa403e948fcb07c30a07103` | 480 | 1.00 | 0.31 | 32 | 26 |
| getsentry/sentry-python | 2,220 | `171aa1646187b79e2a85ce1177a65e509333a8aa` | 191 | 0.93 | 0.41 | 32 | 25 |
| unionai-oss/pandera | 4,536 | `e649b0d76e3ecb3b6ca916bdd5807c64eddd7603` | 213 | 0.97 | 0.58 | 20 | 49 |
| pymc-labs/pymc-marketing | 1,314 | `3c5cbd993aa96b735f41ea1a08ea2c35a899b935` | 107 | 0.99 | 0.47 | 24 | 20 |

Window-dependent columns cover 2026-07-01 to 2026-11-24 (79% of the primary window), not the full window. Each Pinned SHA is the primary Cutoff date's; Runs at the exploratory Cutoff dates pin the last commit before that date.

### How the numbers were measured

- **Candidates:** about 85 Python repos with recent pushes in the two star bands, scanned from partial clones. Stars are current counts, not stars at the Pinned SHA; every pick sits well inside its band.
- **Source files:** `.py` files at the Pinned SHA, excluding test, docs, example, script, vendored, build and migration paths, `conftest.py`, `setup.py` and generated files. This is an approximation until #38 fixes the path filter.
- **Tracker-confirmed Fix commit:** a non-merge, non-bot commit on the default branch whose message matches the keyword rule, avoids the exclusion words, and references an issue (not the trailing `(#N)` PR number) that is closed and typed or labeled as a bug. No N cap and no rename following, so these counts are approximations of the ADR 0004 Label.
- **Squash share:** commits whose subject ends in `(#N)`. A low share (`statsmodels`) means commits land without squashing, not that messages are title-only.

### Selection notes

- **Strict reading is rare.** Of the repos scanned, only about 10 reached 25 tracker-confirmed Fix commits so far, because most fixes name only their PR. Repos failing that were dropped, even when well known (`pytest`, `requests`, `flask`, `pydantic`, `scikit-learn`, `sympy`).
- **Two repos are below 25 today.** `pandera` (20) and `pymc-marketing` (24) are projected at about 25 and 30 over the full window by linear extrapolation. Both already clear ADR 0005's 10-file minimum.
- **Skipped despite passing:** `kornia` (a 1,117-commit keyword spike looks like bulk or automated activity) and `sktime` (10,101 stars, too near the 10k edge).
- **Exploratory windows are thin for some repos.** `pymc-marketing` and `mypy` (and others) have uneven earlier windows. Only the primary window feeds the verdict.

### Re-check before the first scored Run

- Recount at 2026-12-31 and replace any repo below 25 tracker-confirmed Fix commits or 10 files with a Label of 1 or more. A replacement is a new amendment, chosen blind.
- Re-verify the source file range once #38 fixes the path filter.
