#!/usr/bin/env bash
# Runs the mutation gate over the pure domain (src/horizon_tracker/domain/, scoped in
# [tool.mutmut] of pyproject.toml and declared as mutation.targets in .beadloom/flow.yml).
#
# Three modes:
#
#   scripts/mutation.sh [--min-score PERCENT]
#       Every mutant of the domain, judged here: prints the counters and the score.
#       Run it once per slice that touches the domain; paste the counters into the bead.
#
#   scripts/mutation.sh --changed-since REF --out DIR [--min-score PERCENT]
#       Only the domain functions changed since the merge base with REF, as
#       `beadloom mutation --changed-since` names them; judged by beadloom. A change that
#       touches no domain function writes `nothing-to-mutate` to DIR/outcome and runs
#       nothing. CI runs this on every pull request (.github/workflows/mutation.yml).
#
#   scripts/mutation.sh --sample SIZE --seed SEED --out DIR [--min-score PERCENT]
#       A seeded random sample of SIZE mutants of the whole domain, judged by beadloom
#       with the interval the sample supports (--sample-of). CI runs it weekly.
#
# In the DIR modes, DIR receives the population and the score (report.md), the names run
# (names.txt), the counters and survivors beadloom read (stats.json, survivors.json) and
# one word in DIR/outcome: `scored` or `nothing-to-mutate`. No outcome file means the run
# reached no verdict. They need `beadloom` on PATH (uv tool install beadloom==9.0.0).
# The glue between beadloom's plan and mutmut is .github/scripts/mutmut_adapter.py.
#
# Not in pre-commit: a whole run takes about 15 s on 4 cores today, and grows with the domain.
#
# mutmut compiles its trampolined copies into __pycache__ directories, and a later test
# run can import that stale bytecode and pass on code that no longer exists. Every
# __pycache__ under src/ and tests/ is removed on exit, whether the run passed or not.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

usage() {
    cat >&2 <<'USAGE'
Usage: scripts/mutation.sh [--min-score PERCENT]
       scripts/mutation.sh --changed-since REF --out DIR [--min-score PERCENT]
       scripts/mutation.sh --sample SIZE --seed SEED --out DIR [--min-score PERCENT]
USAGE
    exit 2
}

min_score=85
changed_since=""
sample_size=""
seed=""
out=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --min-score) [[ $# -ge 2 ]] || usage; min_score="$2"; shift 2 ;;
        --changed-since) [[ $# -ge 2 ]] || usage; changed_since="$2"; shift 2 ;;
        --sample) [[ $# -ge 2 ]] || usage; sample_size="$2"; shift 2 ;;
        --seed) [[ $# -ge 2 ]] || usage; seed="$2"; shift 2 ;;
        --out) [[ $# -ge 2 ]] || usage; out="$2"; shift 2 ;;
        *) usage ;;
    esac
done

mode=full
if [[ -n "$changed_since" && -n "$sample_size" ]]; then
    usage
elif [[ -n "$changed_since" ]]; then
    mode=change
    [[ -n "$out" && -z "$seed" ]] || usage
elif [[ -n "$sample_size" ]]; then
    mode=sample
    [[ -n "$out" && -n "$seed" && "$sample_size" =~ ^[1-9][0-9]*$ ]] || usage
elif [[ -n "$out" || -n "$seed" ]]; then
    usage
fi
[[ "$min_score" =~ ^[0-9]+([.][0-9]+)?$ ]] || usage

# shellcheck disable=SC2317 # reached through the EXIT trap, not a call
clean_bytecode() {
    find "$root/src" "$root/tests" -name __pycache__ -type d -prune -exec rm -rf {} +
}
trap clean_bytecode EXIT

# A previous run's mutants/ holds cached verdicts for code that may have changed.
rm -rf "$root/mutants"

if [[ "$mode" == full ]]; then
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
    exit 0
fi

# --- the DIR modes: beadloom names the population and judges, mutmut runs the mutants -----

command -v beadloom >/dev/null || { echo "mutation: beadloom is not on PATH" >&2; exit 1; }
adapter=(uv run python "$root/.github/scripts/mutmut_adapter.py")
mkdir -p "$out"
out="$(cd "$out" && pwd)"
rm -f "$out/outcome" "$out/report.md" "$out/names.txt" "$out/stats.json" "$out/survivors.json"
floor="$(awk -v percent="$min_score" 'BEGIN { printf "%.4g", percent / 100 }')"
tool="mutmut $(uv run python -c 'import importlib.metadata as m; print(m.version("mutmut"))')"
report() { tee -a "$out/report.md"; }

nothing_to_mutate() {
    printf '\nNothing to mutate: %s\n' "$1" | report
    echo nothing-to-mutate > "$out/outcome"
    exit 0
}

# mutmut has no command that only generates. `mutmut run` given a name no mutant has
# generates the mutants, runs and saves the stats pass, then refuses the filter; the
# refusal is the expected answer and is checked by its words, so any other failure stops.
prepare_mutants() {
    local log="$out/prepare.log"
    if uv run mutmut run "horizon_tracker.no_such_function__mutmut_0" > "$log" 2>&1; then
        echo "mutation: mutmut accepted a name no mutant has - its CLI changed" >&2
        exit 1
    fi
    if ! grep -q "nothing matches" "$log"; then
        tail -n 20 "$log" >&2
        echo "mutation: generating the mutants failed (above, the end of $log)" >&2
        exit 1
    fi
}

if [[ "$mode" == change ]]; then
    beadloom mutation --changed-since "$changed_since" | report
    beadloom mutation --changed-since "$changed_since" --json > "$out/plan.json"
    if [[ "$(jq -r '.change.empty' "$out/plan.json")" == true ]]; then
        nothing_to_mutate "the change touches no function of the declared scope"
    fi
    prepare_mutants
    "${adapter[@]}" select --plan "$out/plan.json" --names-out "$out/names.txt" | report
    if [[ ! -s "$out/names.txt" ]]; then
        nothing_to_mutate "the changed functions generate no mutant"
    fi
else
    prepare_mutants
    "${adapter[@]}" sample --size "$sample_size" --seed "$seed" \
        --names-out "$out/names.txt" --population-out "$out/population" | report
fi

mapfile -t names < "$out/names.txt"
uv run mutmut run "${names[@]}"
"${adapter[@]}" count --names "$out/names.txt" \
    --stats-out "$out/stats.json" --survivors-out "$out/survivors.json" | report

score=(beadloom mutation --stats "$out/stats.json" --survivors "$out/survivors.json"
       --tool "$tool" --min-score "$floor")
if [[ "$mode" == change ]]; then
    score+=(--changed-since "$changed_since")
else
    declared="$("${adapter[@]}" targets)"
    while read -r target; do
        score+=(--target "$target")
    done <<< "$declared"
    score+=(--sample-of "$(cat "$out/population")")
fi

echo | report
if "${score[@]}" > "$out/score.txt"; then
    verdict=0
else
    verdict=$?
fi
report < "$out/score.txt"
echo scored > "$out/outcome"
exit "$verdict"
