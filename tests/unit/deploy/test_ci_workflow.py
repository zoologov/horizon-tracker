"""Tests for the CI workflow: every check of the completion checklist runs, and none is excused.

CI is the gate a pull request is read by and the gate the deploy reuses, so its steps are
asserted in order: dependencies with the dev extra, ruff, mypy, a browser for the adapter
tests, pytest, then the Beadloom Gate on an index rebuilt from nothing.
"""

import re

from tests.support.workflows import Mapping, all_strings, load_workflow, run_scripts, steps

ORDERED_COMMANDS = [
    "uv sync --extra dev",
    "uv run ruff check src/ tests/",
    "uv run mypy src/",
    "uv run playwright install --with-deps chromium",
    "uv run pytest -q -rs",
    "uv tool install beadloom==9.0.0",
    "rm -f .beadloom/beadloom.db",
    "beadloom reindex",
    "beadloom ci",
]


def ci() -> Mapping:
    return load_workflow("ci.yml")


def command_lines(workflow: Mapping) -> list[str]:
    """The shell lines of every run script, in order, comments and blanks dropped."""
    return [
        line.strip()
        for script in run_scripts(workflow)
        for line in script.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_ci_runs_on_pull_requests_and_pushes_to_main_and_for_the_deploy() -> None:
    on = ci()["on"]
    assert on["pull_request"]["branches"] == ["main"]
    assert on["push"]["branches"] == ["main"]
    assert "workflow_call" in on


def test_ci_runs_the_checklist_in_order() -> None:
    lines = command_lines(ci())
    positions = []
    for command in ORDERED_COMMANDS:
        found = [i for i, line in enumerate(lines) if line == command or line.startswith(command)]
        assert found, f"ci.yml never runs {command!r}"
        positions.append(found[0])
    assert positions == sorted(positions), f"ci.yml runs the checklist out of order: {lines}"


def test_ci_installs_the_pinned_beadloom_without_a_workaround() -> None:
    installs = [line for line in command_lines(ci()) if "uv tool install" in line]
    assert installs == ["uv tool install beadloom==9.0.0"]


def test_ci_gate_runs_on_a_clean_index_in_one_step() -> None:
    gate = [s for s in steps(ci(), "ci") if "beadloom ci" in str(s.get("run", ""))]
    assert len(gate) == 1
    script = [line.strip() for line in str(gate[0]["run"]).splitlines() if line.strip()]
    assert script[-3:] == ["rm -f .beadloom/beadloom.db", "beadloom reindex", "beadloom ci"]


def test_ci_builds_with_the_python_of_the_vps() -> None:
    setup = [s for s in steps(ci(), "ci") if str(s.get("uses", "")).startswith("astral-sh/")]
    assert len(setup) == 1
    assert str(setup[0]["with"]["python-version"]) == "3.12"


def test_no_check_is_excused_from_failing_the_run() -> None:
    for name in ("ci.yml", "deploy.yml"):
        workflow = load_workflow(name)
        assert "continue-on-error" not in all_strings(workflow), name
        for script in run_scripts(workflow):
            assert not re.search(r"\|\|\s*(true|:)", script), f"{name}: a failure is swallowed"
