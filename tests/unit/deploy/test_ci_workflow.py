"""Tests for the CI workflow: three stages, early refusal, and one status that sums them.

CI is the gate a pull request is read by and the gate the release reuses. Stage 1 holds
the cheap static checks; stage 2 - the suite with its browser, the Beadloom Gate and, on
a pull request, the mutation of the domain functions it touched - starts only when all of
stage 1 passed, so a linter error never pays for Chromium; stage 3 is ``ci-ok``, the one
status branch protection can require, and the mutation verdict is not part of it. The
scripts whose outcome is the gate's (``ci-ok``, the unit verification, the Playwright
version, the mutation summary) are executed here with the inputs a runner would give them,
not only read.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.support.repository_root import repository_root
from tests.support.workflows import ROOT, Mapping, load_workflow, step_named, steps

COVERAGE_FLOOR = 80
COVERAGE_SUMMARY = "Coverage in the job summary"
STAGE_1 = {"lint", "types", "workflow-lint"}
STAGE_2 = {"tests", "beadloom-gate"}
# Stage 2 as well, and informative: outside ci-ok by the owner's decision of HT-005.
MUTATION = "mutation-per-change"
AGGREGATE = "ci-ok"
FLOOR_PERCENT = "85"
PYTHONS = ["3.12", "3.13"]
BASH = shutil.which("bash")
JQ = shutil.which("jq")


def ci() -> Mapping:
    return load_workflow("ci.yml")


def job(name: str) -> Mapping:
    found = ci()["jobs"][name]
    assert isinstance(found, dict)
    return found


def needs(name: str) -> set[str]:
    value = job(name).get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def command_lines(job_name: str) -> list[str]:
    """The shell lines of every run script of a job, in order, comments and blanks dropped."""
    return [
        line.strip()
        for step in steps(ci(), job_name)
        for line in str(step.get("run", "")).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def assert_in_order(job_name: str, commands: list[str]) -> None:
    lines = command_lines(job_name)
    positions = []
    for command in commands:
        found = [i for i, line in enumerate(lines) if line.startswith(command)]
        assert found, f"{job_name} never runs {command!r}: {lines}"
        positions.append(found[0])
    assert positions == sorted(positions), f"{job_name} runs out of order: {lines}"


def run_step(
    script: str, env: dict[str, str], cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    """A step's script under bash as the runner starts it, with only the given env."""
    assert BASH is not None
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env={"PATH": os.environ["PATH"], **env},
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


# --- triggers and concurrency ---------------------------------------------------------------


def test_ci_runs_on_pull_requests_pushes_to_main_by_hand_and_for_the_release() -> None:
    on = ci()["on"]
    assert set(on) == {"pull_request", "push", "workflow_dispatch", "workflow_call"}
    assert on["pull_request"]["branches"] == ["main"]
    assert on["push"] == {"branches": ["main"]}


def test_a_caller_names_the_commit_ci_checks() -> None:
    # A redeploy by hand runs on main's head while it deploys an older tag: the release
    # passes the tag's commit, so the gate checks what reaches the host.
    ref = ci()["on"]["workflow_call"]["inputs"]["ref"]
    assert ref["type"] == "string"
    assert ref["required"] is False
    assert ref["default"] == ""


@pytest.mark.parametrize("name", sorted(STAGE_1 | STAGE_2 | {MUTATION}))
def test_every_job_checks_out_the_commit_its_caller_names(name: str) -> None:
    # Empty on a pull request, a push or a dispatch, where checkout takes the event's own
    # commit; the release's commit under workflow_call.
    assert steps(ci(), name)[0]["with"]["ref"] == "${{ inputs.ref }}"


def test_only_a_pull_requests_superseded_run_is_cancelled() -> None:
    concurrency = ci()["concurrency"]
    assert "github.workflow" in concurrency["group"]
    assert concurrency["cancel-in-progress"] == "${{ github.event_name == 'pull_request' }}"


# --- stages ---------------------------------------------------------------------------------


def test_the_jobs_are_the_three_stages() -> None:
    assert set(ci()["jobs"]) == STAGE_1 | STAGE_2 | {MUTATION, AGGREGATE}


@pytest.mark.parametrize("name", sorted(STAGE_1))
def test_stage_one_waits_for_nothing(name: str) -> None:
    assert needs(name) == set()


@pytest.mark.parametrize("name", sorted(STAGE_2 | {MUTATION}))
def test_stage_two_starts_only_after_all_of_stage_one(name: str) -> None:
    assert needs(name) == STAGE_1


def test_ci_ok_waits_for_every_blocking_job_and_runs_whatever_they_did() -> None:
    # The mutation verdict is informative (HT-005): it is seen on the pull request and
    # never decides ci-ok, and on a push or a release it does not run at all.
    assert needs(AGGREGATE) == STAGE_1 | STAGE_2
    # Without always() a failed need SKIPS ci-ok, and a skipped required check reads as
    # passed in branch protection.
    assert job(AGGREGATE)["if"] == "always()"


def ci_ok(results: dict[str, str]) -> subprocess.CompletedProcess[str]:
    step = steps(ci(), AGGREGATE)[-1]
    needs_json = json.dumps({name: {"result": r, "outputs": {}} for name, r in results.items()})
    assert step["env"]["NEEDS"] == "${{ toJSON(needs) }}"
    return run_step(str(step["run"]), {"NEEDS": needs_json})


@pytest.mark.skipif(BASH is None or JQ is None, reason="bash or jq absent")
def test_ci_ok_is_green_when_every_needed_job_succeeded() -> None:
    result = ci_ok(dict.fromkeys(STAGE_1 | STAGE_2, "success"))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None or JQ is None, reason="bash or jq absent")
@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped"])
def test_ci_ok_is_red_and_names_the_job_that_did_not_succeed(outcome: str) -> None:
    results = dict.fromkeys(STAGE_1 | STAGE_2, "success")
    results["tests"] = outcome
    result = ci_ok(results)
    assert result.returncode != 0
    assert "tests" in result.stdout


@pytest.mark.skipif(BASH is None or JQ is None, reason="bash or jq absent")
def test_ci_ok_is_red_when_it_was_given_no_job_to_sum() -> None:
    assert ci_ok({}).returncode != 0


# --- stage 1 --------------------------------------------------------------------------------


ADAPTER = ".github/scripts/mutmut_adapter.py"
RUFF_CHECK = "uv run ruff check"
RUFF_FORMAT = "uv run ruff format --check"
MYPY = "uv run mypy"


def test_lint_checks_the_rules_and_the_format() -> None:
    assert_in_order("lint", ["uv sync --extra dev", RUFF_CHECK, RUFF_FORMAT])


def test_types_checks_the_code_the_tests_and_the_ci_glue() -> None:
    assert_in_order("types", ["uv sync --extra dev", MYPY])


def test_the_static_checks_take_their_scope_from_pyproject() -> None:
    # A path on the command line overrides the configured scope: CI and a local bare run
    # check the same files only when CI names none and pyproject.toml holds the scope.
    lines = command_lines("lint") + command_lines("types")
    tools = [line for line in lines if line.startswith(("uv run ruff", "uv run mypy"))]
    assert tools == [RUFF_CHECK, RUFF_FORMAT, MYPY]


def test_mypy_is_configured_over_the_code_the_tests_and_the_ci_glue() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["mypy"]["files"] == ["src", "tests", ".github/scripts"]
    assert (ROOT / ADAPTER).is_file()


def test_ruff_discovers_the_mutmut_adapter() -> None:
    # The adapter decides which mutants are counted; a scope that misses it lints the
    # code it judges and not the judge. Asked of ruff itself, not of its configuration.
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--show-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    shown = {Path(line.strip()) for line in result.stdout.splitlines() if line.strip()}
    assert ROOT / ADAPTER in shown
    assert ROOT / "src" / "horizon_tracker" / "cli.py" in shown


def test_workflow_lint_checks_workflows_scripts_and_units() -> None:
    assert_in_order(
        "workflow-lint",
        [
            "go install github.com/rhysd/actionlint/cmd/actionlint@v",
            "actionlint",
            "shellcheck deploy/*.sh scripts/*.sh",
        ],
    )


VERIFY_UNITS = "systemd: verify the units"


def write_units(deploy_dir: Path, *, break_timer: bool = False) -> None:
    deploy_dir.mkdir()
    for unit in (ROOT / "deploy").iterdir():
        if unit.suffix in {".service", ".timer"}:
            text = unit.read_text(encoding="utf-8")
            if break_timer and unit.suffix == ".timer":
                text = text.replace("[Timer]", "[Timer]\nOnCalendr=daily")
            (deploy_dir / unit.name).write_text(text, encoding="utf-8")


@pytest.mark.skipif(BASH is None or shutil.which("systemd-analyze") is None, reason="no systemd")
def test_the_unit_verification_passes_the_shipped_units(tmp_path: Path) -> None:
    write_units(tmp_path / "deploy")
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    script = str(step_named(ci(), "workflow-lint", VERIFY_UNITS)["run"])
    result = run_step(script, {"RUNNER_TEMP": str(runner_temp)}, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None or shutil.which("systemd-analyze") is None, reason="no systemd")
def test_the_unit_verification_refuses_a_key_systemd_only_warns_about(tmp_path: Path) -> None:
    # verify exits 0 on an unknown key and only prints a warning: the step must read the
    # output, not the exit code alone.
    write_units(tmp_path / "deploy", break_timer=True)
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    script = str(step_named(ci(), "workflow-lint", VERIFY_UNITS)["run"])
    result = run_step(script, {"RUNNER_TEMP": str(runner_temp)}, cwd=tmp_path)
    assert result.returncode != 0
    assert "OnCalendr" in result.stdout + result.stderr


# --- stage 2: tests -------------------------------------------------------------------------


def test_tests_run_on_the_python_of_the_vps_and_of_development() -> None:
    strategy = job("tests")["strategy"]
    assert [str(v) for v in strategy["matrix"]["python"]] == PYTHONS
    # Every leg reports: one red leg must not hide what the other would have said.
    assert strategy["fail-fast"] is False
    setup = [s for s in steps(ci(), "tests") if str(s.get("uses", "")).startswith("astral-sh/")]
    assert len(setup) == 1
    assert setup[0]["with"]["python-version"] == "${{ matrix.python }}"


def test_tests_install_the_browser_after_restoring_its_cache() -> None:
    names = [s.get("name") for s in steps(ci(), "tests")]
    cache = step_named(ci(), "tests", "Cache the Playwright browser")
    assert cache["with"]["path"] == "~/.cache/ms-playwright"
    assert "${{ steps.playwright.outputs.version }}" in cache["with"]["key"]
    assert names.index("Cache the Playwright browser") < names.index("Chromium for the adapters")
    assert_in_order(
        "tests",
        ["uv sync --extra dev", "uv run playwright install --with-deps chromium", "uv run pytest"],
    )


def locked_playwright() -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == "playwright"]
    assert len(versions) == 1
    return str(versions[0])


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_browser_cache_is_keyed_by_the_locked_playwright(tmp_path: Path) -> None:
    step = step_named(ci(), "tests", "Playwright version from uv.lock")
    assert step["id"] == "playwright"
    output = tmp_path / "output"
    result = run_step(str(step["run"]), {"GITHUB_OUTPUT": str(output)})
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == f"version={locked_playwright()}\n"


def pytest_command() -> list[str]:
    """The one pytest line of ci.yml, split into words."""
    found = [line for line in command_lines("tests") if line.startswith("uv run pytest")]
    assert len(found) == 1, f"ci.yml runs pytest {len(found)} times: {found}"
    return found[0].split()


def coverage_settings() -> Mapping:
    manifest = (repository_root() / "pyproject.toml").read_text(encoding="utf-8")
    coverage = tomllib.loads(manifest)["tool"]["coverage"]
    assert isinstance(coverage, dict)
    return coverage


def test_ci_measures_coverage_so_the_floor_can_fail_the_run() -> None:
    # fail_under is read only by a pytest run that measures coverage: without --cov the
    # floor is declared and nothing ever evaluates it.
    words = pytest_command()
    assert {"-rs", "--cov", "--cov-report=term-missing", "--cov-report=xml"} <= set(words)
    assert not [w for w in words if w.startswith(("--no-cov", "--cov-fail-under"))], words


def test_coverage_is_kept_and_summarised_per_python() -> None:
    upload = step_named(ci(), "tests", "Keep coverage.xml")
    assert upload["with"]["path"] == "coverage.xml"
    assert "${{ matrix.python }}" in upload["with"]["name"]
    summary = step_named(ci(), "tests", COVERAGE_SUMMARY)
    assert "coverage report --format=total" in summary["run"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in summary["run"]
    # A red pytest still reports its figure (executed below); a cancelled run does not
    # pretend to.
    assert summary["if"] == "${{ !cancelled() }}"
    assert upload["if"] == "${{ !cancelled() }}"


HALF_COVERED = """def used():
    return 1


def unused():
    first = 1
    second = 2
    return first + second


used()
"""


def coverage_summary(tmp_path: Path, *, measured: bool) -> str:
    """The summary step run in a project whose coverage is under the floor.

    ``uv run coverage`` reaches the interpreter running these tests, which carries
    coverage through pytest-cov; nothing else of the step is stood in for.
    """
    work = tmp_path / "work"
    work.mkdir()
    floor = f"[tool.coverage.report]\nfail_under = {COVERAGE_FLOOR}\n"
    (work / "pyproject.toml").write_text(floor, encoding="utf-8")
    (work / "half.py").write_text(HALF_COVERED, encoding="utf-8")
    clean = {"PATH": os.environ["PATH"]}
    if measured:
        run = [sys.executable, "-m", "coverage", "run", "half.py"]
        subprocess.run(run, cwd=work, env=clean, check=True, capture_output=True)
        below = subprocess.run(
            [sys.executable, "-m", "coverage", "report"], cwd=work, env=clean, check=False
        )
        assert below.returncode == 2, "the fixture is not under the floor"
    stubs = tmp_path / "bin"
    stubs.mkdir()
    uv = stubs / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "assert sys.argv[1:3] == ['run', 'coverage'], sys.argv\n"
        "os.execv(sys.executable, [sys.executable, '-m', 'coverage', *sys.argv[3:]])\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    summary = tmp_path / "summary.md"
    step = step_named(ci(), "tests", COVERAGE_SUMMARY)
    env = {
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "PYTHON": "3.12",
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    result = run_step(str(step["run"]), env, cwd=work)
    assert result.returncode == 0, result.stdout + result.stderr
    return summary.read_text(encoding="utf-8") if summary.exists() else ""


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_coverage_line_reaches_the_summary_when_coverage_is_under_the_floor(
    tmp_path: Path,
) -> None:
    # The run where the figure matters most: pytest is red on the floor, and the summary
    # still says by how much. The floor is pytest's to judge, not this step's.
    summary = coverage_summary(tmp_path, measured=True)
    assert re.fullmatch(
        r"Coverage on Python 3\.12: (\d+)% \(floor: fail_under in pyproject\.toml\)\n", summary
    ), summary
    assert int(summary.split(": ")[1].split("%")[0]) < COVERAGE_FLOOR


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_summary_says_so_when_pytest_left_no_coverage_data(tmp_path: Path) -> None:
    summary = coverage_summary(tmp_path, measured=False)
    assert summary == "Coverage on Python 3.12: no data - pytest did not reach the end\n"


def test_the_floor_ci_enforces_is_the_one_the_plan_names() -> None:
    assert coverage_settings()["report"]["fail_under"] == COVERAGE_FLOOR


def test_coverage_follows_the_greenlets_the_browser_adapter_runs_on() -> None:
    # Playwright's sync API runs on greenlets; without this, the lines it executes are
    # counted as missed and the figure the floor is held against is wrong.
    assert set(coverage_settings()["run"].get("concurrency", [])) == {"greenlet", "thread"}


# --- stage 2: Beadloom Gate -----------------------------------------------------------------


def test_the_gate_installs_the_pinned_beadloom_without_a_workaround() -> None:
    installs = [line for line in command_lines("beadloom-gate") if "uv tool install" in line]
    assert installs == ["uv tool install beadloom==9.0.0"]


def test_the_gate_runs_on_a_clean_index_in_one_step() -> None:
    gate = [s for s in steps(ci(), "beadloom-gate") if "beadloom ci" in str(s.get("run", ""))]
    assert len(gate) == 1
    script = [line.strip() for line in str(gate[0]["run"]).splitlines() if line.strip()]
    assert script[-3:] == ["rm -f .beadloom/beadloom.db", "beadloom reindex", "beadloom ci"]


def test_the_gate_holds_the_epics_against_the_as_is_space() -> None:
    assert_in_order("beadloom-gate", ["beadloom ci", "beadloom docs spaces --strict"])


def test_no_job_runs_without_the_code_it_checks() -> None:
    for name in STAGE_1 | STAGE_2 | {MUTATION}:
        first = steps(ci(), name)[0]
        assert str(first.get("uses", "")).startswith("actions/checkout@"), name
        assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", first["uses"]), name


def test_no_job_keeps_the_token_in_its_checkout() -> None:
    # No job pushes; a token left in .git/config is one a later step could read.
    for name in STAGE_1 | STAGE_2 | {MUTATION}:
        assert steps(ci(), name)[0].get("with", {}).get("persist-credentials") is False, name


# --- stage 2: mutation per change -----------------------------------------------------------


def test_the_mutation_of_a_change_runs_on_pull_requests_only() -> None:
    # A push to main and the release's gate have no base to take a change from.
    assert job(MUTATION)["if"] == "github.event_name == 'pull_request'"


def test_the_mutation_job_reads_the_whole_history_for_the_merge_base() -> None:
    checkout = steps(ci(), MUTATION)[0]
    assert checkout["with"]["fetch-depth"] == 0
    assert job(MUTATION)["env"]["BASE"] == "origin/${{ github.base_ref }}"


def test_the_mutation_job_installs_the_suite_and_the_pinned_beadloom() -> None:
    lines = command_lines(MUTATION)
    assert "uv sync --extra dev" in lines
    assert "uv tool install beadloom==9.0.0" in lines
    setup = [s for s in steps(ci(), MUTATION) if str(s.get("uses", "")).startswith("astral-sh/")]
    assert len(setup) == 1
    assert str(setup[0]["with"]["python-version"]) == "3.12"


def test_the_mutation_job_runs_the_script_over_the_change() -> None:
    expected = (
        f'scripts/mutation.sh --changed-since "$BASE" --out "$RUNNER_TEMP/mutation" '
        f"--min-score {FLOOR_PERCENT}"
    )
    assert expected in [" ".join(line.split()) for line in command_lines(MUTATION)]


def test_the_mutation_report_and_counters_outlive_a_red_run() -> None:
    upload = step_named(ci(), MUTATION, "Keep the plan, the counters and the survivors")
    assert upload["if"] == "${{ !cancelled() }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/mutation"
    assert step_named(ci(), MUTATION, "Summary")["if"] == "${{ !cancelled() }}"


def mutation_summary(
    tmp_path: Path, outcome: str | None
) -> tuple[subprocess.CompletedProcess[str], str]:
    out = tmp_path / "mutation"
    out.mkdir()
    (out / "report.md").write_text("Population: empty\n", encoding="utf-8")
    if outcome is not None:
        (out / "outcome").write_text(f"{outcome}\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    script = str(step_named(ci(), MUTATION, "Summary")["run"])
    env = {"RUNNER_TEMP": str(tmp_path), "GITHUB_STEP_SUMMARY": str(summary)}
    result = run_step(script, env)
    return result, summary.read_text(encoding="utf-8") if summary.exists() else ""


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_an_empty_change_is_announced_as_nothing_to_mutate(tmp_path: Path) -> None:
    result, summary = mutation_summary(tmp_path, "nothing-to-mutate")
    assert result.returncode == 0, result.stderr
    assert "::notice title=Mutation::Nothing to mutate" in result.stdout
    assert "Nothing to mutate" in summary
    assert "Population: empty" in summary


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_scored_change_is_summarised_without_a_notice(tmp_path: Path) -> None:
    result, summary = mutation_summary(tmp_path, "scored")
    assert result.returncode == 0, result.stderr
    assert "::notice" not in result.stdout
    assert "Population: empty" in summary


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_mutation_run_that_reached_no_outcome_is_red_in_the_summary_too(
    tmp_path: Path,
) -> None:
    result, summary = mutation_summary(tmp_path, None)
    assert result.returncode != 0
    assert "no verdict" in summary
