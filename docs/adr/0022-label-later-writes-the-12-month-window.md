# `label-later` writes the 12-month window to its own create-once file

Accepted 2026-11-25. Decided in #135. Amends [ADR 0021](0021-sensitivity-checks-in-report.md) and [ADR 0008](0008-pipeline-stages-artifacts-and-resume.md); [ADR 0004](0004-label-is-future-fix-proneness.md)'s rule that `labels.json` is written once and N is fixed before any scored Run stands.

## Decision

- **A separate stage.** `label-later <run-id>` writes `labels-12m.json`, a create-once artifact, once the 12-month window `(Cutoff date, Cutoff date + 12 months]` has closed. It never reads or rewrites `labels.json`.
- **Contents.** The tracker-confirmed counts over the 12-month window at the primary N, plus `max_files`, `issues_read_at`, the clone's HEAD and newest commit, and whether the clone was fast-forwarded.
- **Same N.** `--max-files` must equal the N in `validation.json` when that file exists, as for `label`. Without `validation.json` the caller must pass the same N; `max_files` is recorded so a mismatch is visible.
- **Refusals.** No `labels.json`; the 12-month window still open; `labels.json` already holds `window-12m` (a Run labeled late); `labels-12m.json` already exists.
- **`score` stays a pure function of Run files.** When `labels-12m.json` exists, `score` reads it as the `window-12m` variant. Without it, that check is n/a as before. A Run scored before `label-later` gets the check by a re-score on a later day, which writes a new `scores-*.json` and never overwrites the earlier one.

## Why

- `labels.json` stays write-once, so labels cannot be tuned after seeing results. The new file adds one report-only variant and changes no primary count.
- Git and the tracker stay in the label stages. The alternative, `score` computing the counts from the clone, would make scores depend on clone state and the tracker at scoring time, and on a second Run the same inputs could give different scores (ADR 0001, ADR 0020).

## Known limits

- The tracker is read again, so a Fix commit whose issue closed or was retyped since the primary read can count in the 12-month window and not in the 6-month one. The 12-month check mixes window length with tracker drift; `issues_read_at` records both reads.
- Nothing proves the N used equals the one for `labels.json` when `validation.json` is absent.
- Until `label-later` runs and the Run is re-scored, the report shows the 12-month check as n/a.

## Amendments

None yet.
