#!/usr/bin/env bash
# Runs the mutation gate over the pure domain (src/horizon_tracker/domain/, scoped in
# [tool.mutmut] of pyproject.toml) and prints the counters and the score.
#
# Deliberately not in pre-commit and not in CI: a run takes minutes. Run it once per
# slice that touches the domain, and paste the printed counters into the bead comment.
#
# mutmut compiles its trampolined copies into __pycache__ directories, and a later test
# run can import that stale bytecode and pass on code that no longer exists. Every
# __pycache__ under src/ and tests/ is removed on exit, whether the run passed or not.
#
# Usage: scripts/mutation.sh [--min-score PERCENT]   (default 85)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

min_score=85
if [[ "${1:-}" == "--min-score" ]]; then
    min_score="${2:?--min-score needs a percentage}"
fi

clean_bytecode() {
    find "$root/src" "$root/tests" -name __pycache__ -type d -prune -exec rm -rf {} +
}
trap clean_bytecode EXIT

# A previous run's mutants/ holds cached verdicts for code that may have changed.
rm -rf "$root/mutants"

uv run mutmut run
uv run mutmut export-cicd-stats

uv run python - "$min_score" <<'PY'
import json
import sys
from pathlib import Path

stats = json.loads(Path("mutants/mutmut-cicd-stats.json").read_text(encoding="utf-8"))
minimum = float(sys.argv[1])
total = stats["total"]
killed = stats["killed"] + stats.get("timeout", 0)
survived = stats["survived"]
not_checked = stats.get("not_checked", 0) + stats.get("skipped", 0)
for key in sorted(stats):
    print(f"{key}: {stats[key]}")
if total == 0:
    sys.exit("mutation: zero mutants generated - the gate checked nothing")
if not_checked:
    sys.exit(f"mutation: {not_checked} mutants were not checked - the score would be a guess")
score = 100.0 * killed / (killed + survived)
print(f"mutation score: {score:.1f}% ({killed} killed of {killed + survived} checked)")
if score < minimum:
    sys.exit(f"mutation: score {score:.1f}% is below {minimum:g}%")
PY
