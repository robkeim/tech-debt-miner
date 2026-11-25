#!/usr/bin/env bash
# Walk one Run through every Milestone 1 stage (no LLM) and show each artifact.
#
# Uses an exploratory Cutoff date (2026-01-01) because its 6-month Label window has
# already closed; the primary window (2026-07-01) closes 2026-12-31 and `label` refuses
# until then. Needs network and an authenticated `gh`. Output goes to a scratch dir, so
# your real runs/ and repos/ are untouched.
#
# Usage: scripts/m1_demo.sh [owner/name] [YYYY-MM-DD]
#   OUT=/some/dir  override the scratch dir (default: .demo/m1 under the repo root)
set -euo pipefail

REPO="${1:-getsentry/sentry-python}"
CUTOFF="${2:-2026-01-01}"
cd "$(dirname "$0")/.."
OUT="${OUT:-.demo/m1}"
mkdir -p "$OUT"
FLAGS=(--repos-dir "$OUT/repos" --runs-dir "$OUT/runs")
RUNS=(--runs-dir "$OUT/runs")
tdm() { uv run --quiet tdm "$@"; }

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$1"; }
show() { # show a JSON artifact, truncated
  local file="$1" lines="${2:-40}"
  printf '\033[2m-- %s\033[0m\n' "$file"
  { python3 -m json.tool "$file" | head -n "$lines"; } || true
  printf '\033[2m   (first %s lines)\033[0m\n' "$lines"
}

step "1. resolve: clone, pin the SHA at the Cutoff, write manifest.json"
RUN_ID="$(tdm resolve --repo "$REPO" --cutoff "$CUTOFF" "${FLAGS[@]}" | tail -n 1)"
RUN="$OUT/runs/$RUN_ID"
echo "run id: $RUN_ID"
show "$RUN/manifest.json" 30
echo "state: $(tdm status "$RUN_ID" "${RUNS[@]}")"

step "2. snapshot: churn, complexity, LOC and issues as of the Cutoff"
tdm snapshot "$RUN_ID" "${FLAGS[@]}"
python3 - "$RUN/snapshot.json" <<'PY'
import json, sys
snap = json.load(open(sys.argv[1]))
print(f"top-level keys: {list(snap)}")
for key, value in snap.items():
    if isinstance(value, (list, dict)):
        print(f"  {key}: {len(value)} entries")
files = snap.get("files")
if isinstance(files, list):
    print("first 3 files:")
    for f in files[:3]:
        print("  ", json.dumps(f)[:160])
PY

step "3. rank: Baseline (churn x complexity) with tie groups"
tdm rank "$RUN_ID" "${RUNS[@]}"
ls "$RUN/rankings"
python3 - "$RUN/rankings/baseline.json" <<'PY'
import json, sys
print(json.dumps(json.load(open(sys.argv[1])))[:900], "...")
PY
echo "state: $(tdm status "$RUN_ID" "${RUNS[@]}")"

step "4. validate: fix-size cap N, Label at several caps, 30-commit review sheet"
tdm validate "$RUN_ID" "${FLAGS[@]}" > "$OUT/review-sheet.md"
head -n 22 "$OUT/review-sheet.md"
echo "... full review sheet: $OUT/review-sheet.md"

step "5. label: Fix commits in the window, tracker-confirmed (uses gh)"
CAP_N="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cap_n"])' "$RUN/validation.json")"
echo "using N=$CAP_N from validation.json"
tdm label "$RUN_ID" "${FLAGS[@]}" --max-files "$CAP_N"
show "$RUN/labels.json" 30

step "6. score: nDCG@20 and recall at 20% of LOC"
tdm score "$RUN_ID" "${RUNS[@]}"
for f in "$RUN"/scores-*.json; do show "$f" 40; done
echo "state: $(tdm status "$RUN_ID" "${RUNS[@]}")"

step "7. report: verdict (Baseline vs itself; no LLM ranker until M2)"
tdm report --treatment baseline "${RUNS[@]}"

step "8. probe: Dry-run only (no API call, no spend)"
tdm probe "$RUN_ID" "${FLAGS[@]}"

step "9. resume: a fresh Run replays the stages itself and stops at the Dry-run"
RUN2="$(tdm resolve --repo "$REPO" --cutoff 2026-02-01 "${FLAGS[@]}" | tail -n 1)"
tdm resume "$RUN2" "${FLAGS[@]}" --no-fetch
tdm resume "$RUN2" "${FLAGS[@]}" --no-fetch   # second call: everything done, runs nothing

printf '\nArtifacts are under %s\n' "$OUT"
