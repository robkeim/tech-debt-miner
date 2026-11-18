# Reproducibility means replay, not identical output

Claude's API has no seed or system fingerprint, so output can't be bit-reproducible. We define reproducible as: every Run logs raw responses, a pinned dated model snapshot, the resolved `model`, request ID, `stop_reason` and `usage`, so results can be re-scored by Replay with no API calls. Raw Run output lives in gitignored `runs/<UTC-timestamp>-<hash>/`; only small curated summaries referencing the Run ID and Manifest hash are committed.
