"""Tests for the mutation workflow, the script it runs and the adapter that meets mutmut.

The workflow mutates the domain functions a pull request touched and, weekly, a seeded
sample of the whole declared scope (the scheme of beadloom's own mutation.yml). Its
verdicts come from ``beadloom mutation``; what the repository owns is the glue: the
adapter that turns a plan into mutmut's exact mutant names and counts exactly those, and
``scripts/mutation.sh``, which orders the steps. The adapter is executed here on a
``mutants/`` tree in mutmut 3.8's shape; the run against the real mutmut is the script's.
"""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; the dict is narrowed below

from tests.support.workflows import ROOT, Mapping, load_workflow, step_named, steps

DOMAIN = "src/horizon_tracker/domain/"
ADAPTER = ROOT / ".github" / "scripts" / "mutmut_adapter.py"
SCRIPT = ROOT / "scripts" / "mutation.sh"
PER_CHANGE = "mutation-per-change"
SAMPLE = "mutation-sample"
FLOOR_PERCENT = "85"
BASH = shutil.which("bash")
MODULE = "horizon_tracker.domain.schedule"
SCHEDULE = "src/horizon_tracker/domain/schedule.py"
REPORT = "src/horizon_tracker/domain/report.py"


def mutation() -> Mapping:
    return load_workflow("mutation.yml")


def job(name: str) -> Mapping:
    found = mutation()["jobs"][name]
    assert isinstance(found, dict)
    return found


def script_lines(job_name: str) -> list[str]:
    return [
        " ".join(line.split())
        for step in steps(mutation(), job_name)
        for line in str(step.get("run", "")).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# --- the declared scope -----------------------------------------------------------------


def test_the_declared_scope_is_the_pure_domain() -> None:
    flow = yaml.safe_load((ROOT / ".beadloom" / "flow.yml").read_text(encoding="utf-8"))
    assert flow["mutation"] == {"targets": [DOMAIN]}


def test_the_declared_scope_is_the_one_mutmut_mutates() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["mutmut"]["only_mutate"] == [f"{DOMAIN}*"]


# --- triggers and jobs ------------------------------------------------------------------


def test_mutation_runs_per_pull_request_weekly_and_by_hand() -> None:
    on = mutation()["on"]
    assert on["pull_request"] == {"branches": ["main"]}
    (cron,) = on["schedule"]
    _, _, day, month, weekday = cron["cron"].split()
    assert (day, month) == ("*", "*") and weekday.isdigit(), "not once a week"
    assert set(on["workflow_dispatch"]["inputs"]) == {"size", "seed"}


def test_the_per_change_job_runs_on_pull_requests_and_the_sample_otherwise() -> None:
    assert set(mutation()["jobs"]) == {PER_CHANGE, SAMPLE}
    assert job(PER_CHANGE)["if"] == "github.event_name == 'pull_request'"
    assert job(SAMPLE)["if"] == "github.event_name != 'pull_request'"


@pytest.mark.parametrize("name", [PER_CHANGE, SAMPLE])
def test_no_job_keeps_the_token_in_its_checkout(name: str) -> None:
    # Neither job pushes, and the merge base comes from the history fetched at checkout.
    checkout = steps(mutation(), name)[0]
    assert str(checkout["uses"]).startswith("actions/checkout@")
    assert checkout["with"]["persist-credentials"] is False


def test_the_per_change_job_reads_the_whole_history_for_the_merge_base() -> None:
    checkout = steps(mutation(), PER_CHANGE)[0]
    assert checkout["with"]["fetch-depth"] == 0
    assert job(PER_CHANGE)["env"]["BASE"] == "origin/${{ github.base_ref }}"


@pytest.mark.parametrize("name", [PER_CHANGE, SAMPLE])
def test_both_jobs_install_the_suite_and_the_pinned_beadloom(name: str) -> None:
    lines = script_lines(name)
    assert "uv sync --extra dev" in lines
    assert "uv tool install beadloom==9.0.0" in lines
    setup = [s for s in steps(mutation(), name) if str(s.get("uses", "")).startswith("astral-sh/")]
    assert len(setup) == 1
    assert str(setup[0]["with"]["python-version"]) == "3.12"


def test_the_per_change_job_runs_the_script_over_the_change() -> None:
    lines = script_lines(PER_CHANGE)
    expected = (
        f'scripts/mutation.sh --changed-since "$BASE" --out "$RUNNER_TEMP/mutation" '
        f"--min-score {FLOOR_PERCENT}"
    )
    assert expected in lines


def test_the_sample_job_runs_the_script_over_a_seeded_sample() -> None:
    lines = script_lines(SAMPLE)
    assert 'seed="${SAMPLE_SEED:-$(date -u +%G-W%V)}"' in lines
    expected = (
        f'scripts/mutation.sh --sample "$SAMPLE_SIZE" --seed "$seed" '
        f'--out "$RUNNER_TEMP/mutation" --min-score {FLOOR_PERCENT}'
    )
    assert expected in lines
    assert job(SAMPLE)["env"]["SAMPLE_SIZE"] == "${{ inputs.size || '150' }}"


@pytest.mark.parametrize("name", [PER_CHANGE, SAMPLE])
def test_the_report_and_the_counters_outlive_a_red_run(name: str) -> None:
    upload = step_named(mutation(), name, "Keep the plan, the counters and the survivors")
    assert upload["if"] == "${{ !cancelled() }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/mutation"
    summary = step_named(mutation(), name, "Summary")
    assert summary["if"] == "${{ !cancelled() }}"


def run_summary(
    tmp_path: Path, outcome: str | None
) -> tuple[subprocess.CompletedProcess[str], str]:
    assert BASH is not None
    out = tmp_path / "mutation"
    out.mkdir()
    (out / "report.md").write_text("Population: empty\n", encoding="utf-8")
    if outcome is not None:
        (out / "outcome").write_text(f"{outcome}\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    step = step_named(mutation(), PER_CHANGE, "Summary")
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", str(step["run"])],
        env={
            "PATH": os.environ["PATH"],
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, summary.read_text(encoding="utf-8") if summary.exists() else ""


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_an_empty_change_is_announced_as_nothing_to_mutate(tmp_path: Path) -> None:
    result, summary = run_summary(tmp_path, "nothing-to-mutate")
    assert result.returncode == 0, result.stderr
    assert "::notice title=Mutation::Nothing to mutate" in result.stdout
    assert "Nothing to mutate" in summary
    assert "Population: empty" in summary


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_scored_change_is_summarised_without_a_notice(tmp_path: Path) -> None:
    result, summary = run_summary(tmp_path, "scored")
    assert result.returncode == 0, result.stderr
    assert "::notice" not in result.stdout
    assert "Population: empty" in summary


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_run_that_reached_no_outcome_is_red_in_the_summary_too(tmp_path: Path) -> None:
    result, summary = run_summary(tmp_path, None)
    assert result.returncode != 0
    assert "no verdict" in summary


# --- scripts/mutation.sh ------------------------------------------------------------------


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, str(SCRIPT), *args], capture_output=True, text=True, check=False, cwd=ROOT
    )


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize(
    "args",
    [
        ["--bogus"],
        ["--changed-since", "origin/main"],
        ["--sample", "10", "--out", "x"],
        ["--sample", "ten", "--seed", "s", "--out", "x"],
        ["--changed-since", "origin/main", "--sample", "5", "--seed", "s", "--out", "x"],
        ["--min-score"],
    ],
)
def test_the_script_refuses_an_incomplete_request_before_it_changes_anything(
    args: list[str],
) -> None:
    result = run_script(*args)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Usage:" in result.stderr


def test_the_script_keeps_its_full_domain_default() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "uv run mutmut run\n" in text, "the default mode must run every mutant"
    assert "export-cicd-stats" in text


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck absent")
def test_the_script_passes_shellcheck() -> None:
    result = subprocess.run(
        ["shellcheck", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout


# --- the adapter --------------------------------------------------------------------------

KILLED, SURVIVED, NO_TESTS = 1, 0, 33


def write_metas(root: Path, codes: dict[str, dict[str, int | None]]) -> None:
    """``mutants/<source>.meta`` as mutmut 3.8 writes it: exit codes by mutant name."""
    for source, by_name in codes.items():
        meta = root / "mutants" / f"{source}.meta"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({"exit_code_by_key": by_name}), encoding="utf-8")


def mutants_of(function: str, count: int, module: str = MODULE) -> list[str]:
    return [f"{module}.{function}__mutmut_{i}" for i in range(1, count + 1)]


def adapter(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ADAPTER), *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def domain_tree(root: Path) -> None:
    write_metas(
        root,
        {
            SCHEDULE: {
                **dict.fromkeys(mutants_of("x_draw_moments", 3), KILLED),
                **dict.fromkeys(mutants_of("xǁTimeRangeǁ__post_init__", 2), SURVIVED),
                **dict.fromkeys(mutants_of("x__pick", 4), KILLED),
            },
            REPORT: dict.fromkeys(mutants_of("x_render", 2, "horizon_tracker.domain.report"), 1),
        },
    )


def write_plan(root: Path, functions: list[tuple[str, str]]) -> Path:
    plan = root / "plan.json"
    change = {"functions": [{"path": p, "name": n, "node": "n"} for p, n in functions]}
    plan.write_text(json.dumps({"change": change}), encoding="utf-8")
    return plan


def read_names(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_select_takes_exactly_the_mutants_of_the_changed_functions(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    plan = write_plan(tmp_path, [(SCHEDULE, "draw_moments"), (SCHEDULE, "TimeRange.__post_init__")])
    result = adapter(tmp_path, "select", "--plan", str(plan), "--names-out", "names.txt")
    assert result.returncode == 0, result.stderr
    names = read_names(tmp_path / "names.txt")
    expected = mutants_of("x_draw_moments", 3) + mutants_of("xǁTimeRangeǁ__post_init__", 2)
    assert sorted(names) == sorted(expected)
    assert "5 mutant(s)" in result.stdout


def test_select_matches_a_function_in_its_own_file_only(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    plan = write_plan(tmp_path, [(SCHEDULE, "render")])
    result = adapter(tmp_path, "select", "--plan", str(plan), "--names-out", "names.txt")
    assert result.returncode == 0, result.stderr
    assert read_names(tmp_path / "names.txt") == []
    assert "render: 0 mutant(s)" in result.stdout


def test_select_refuses_a_run_that_generated_no_mutant(tmp_path: Path) -> None:
    plan = write_plan(tmp_path, [(SCHEDULE, "draw_moments")])
    result = adapter(tmp_path, "select", "--plan", str(plan), "--names-out", "names.txt")
    assert result.returncode != 0
    assert "mutants" in result.stderr


def test_sample_is_seeded_and_names_its_population(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    args = ["sample", "--size", "4", "--seed", "2026-W43", "--population-out", "population"]
    first = adapter(tmp_path, *args, "--names-out", "a.txt")
    second = adapter(tmp_path, *args, "--names-out", "b.txt")
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert read_names(tmp_path / "a.txt") == read_names(tmp_path / "b.txt")
    assert len(read_names(tmp_path / "a.txt")) == 4
    assert (tmp_path / "population").read_text(encoding="utf-8").strip() == "11"


def test_a_sample_larger_than_the_scope_is_the_whole_scope(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    args = ["sample", "--size", "150", "--seed", "s", "--population-out", "population"]
    result = adapter(tmp_path, *args, "--names-out", "names.txt")
    assert result.returncode == 0, result.stderr
    assert len(read_names(tmp_path / "names.txt")) == 11


def count(tmp_path: Path, names: list[str]) -> subprocess.CompletedProcess[str]:
    (tmp_path / "names.txt").write_text("".join(f"{n}\n" for n in names), encoding="utf-8")
    return adapter(
        tmp_path,
        "count",
        "--names",
        "names.txt",
        "--stats-out",
        "stats.json",
        "--survivors-out",
        "survivors.json",
    )


def test_count_classifies_exactly_the_selected_names(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    selected = mutants_of("x_draw_moments", 3) + mutants_of("xǁTimeRangeǁ__post_init__", 2)
    result = count(tmp_path, selected)
    assert result.returncode == 0, result.stderr
    stats = json.loads((tmp_path / "stats.json").read_text(encoding="utf-8"))
    assert stats["killed"] == 3
    assert stats["survived"] == 2
    assert stats["not_checked"] == 0
    survivors = json.loads((tmp_path / "survivors.json").read_text(encoding="utf-8"))
    assert {s["path"] for s in survivors} == {SCHEDULE}
    assert sorted(s["mutant"] for s in survivors) == mutants_of("xǁTimeRangeǁ__post_init__", 2)


def test_count_refuses_a_run_that_left_a_selected_mutant_unchecked(tmp_path: Path) -> None:
    # Every step can exit 0 while the runner never reached a mutant: that run is silent,
    # and a score over the mutants it did reach would be a green it did not earn.
    write_metas(tmp_path, {SCHEDULE: {mutants_of("x_f", 1)[0]: KILLED, "m.x_g__mutmut_1": None}})
    result = count(tmp_path, [mutants_of("x_f", 1)[0], "m.x_g__mutmut_1"])
    assert result.returncode != 0
    assert "1 of 2" in result.stderr


def test_count_refuses_a_name_no_meta_holds(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    result = count(tmp_path, ["horizon_tracker.domain.schedule.x_gone__mutmut_1"])
    assert result.returncode != 0
    assert "x_gone" in result.stderr


def test_count_refuses_an_empty_selection(tmp_path: Path) -> None:
    domain_tree(tmp_path)
    assert count(tmp_path, []).returncode != 0


def test_count_keeps_mutmuts_own_classes(tmp_path: Path) -> None:
    write_metas(tmp_path, {SCHEDULE: {"m.x_f__mutmut_1": NO_TESTS, "m.x_f__mutmut_2": 36}})
    result = count(tmp_path, ["m.x_f__mutmut_1", "m.x_f__mutmut_2"])
    assert result.returncode == 0, result.stderr
    stats = json.loads((tmp_path / "stats.json").read_text(encoding="utf-8"))
    assert (stats["no_tests"], stats["timeout"]) == (1, 1)


def test_targets_are_read_from_the_flow() -> None:
    result = adapter(ROOT, "targets")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [DOMAIN]
