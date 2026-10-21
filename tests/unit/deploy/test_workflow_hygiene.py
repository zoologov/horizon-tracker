"""Tests for what every workflow holds: pinned actions, bounded jobs, nothing excused.

Each property is checked over every file in ``.github/workflows`` rather than a named
list, so a workflow added later is held to it without anyone remembering to add it here.
"""

import re

import pytest

from tests.support.workflows import WORKFLOWS_DIR, Mapping, all_strings, load_workflow, run_scripts

WORKFLOWS = sorted(p.name for p in WORKFLOWS_DIR.glob("*.yml"))
# owner/repo[/path]@<40 hex> - a tag or a branch can be moved, a commit cannot.
PINNED = re.compile(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$")
VERSION_COMMENT = re.compile(r"#\s*v\d+\.\d+\.\d+\s*$")
UV_SYNC = re.compile(r"\buv sync\b(.*)$")
LOCKED = re.compile(r"(?<!\S)--locked(?![\w-])")
READ_ONLY = {"contents": "read"}
# The only jobs whose token may do more than read the repository, each with what it needs:
# publishing a release writes the repository's releases, and GitHub Pages is built from a
# token that reads the Pages site and deployed by one that writes it and presents an OIDC
# token. Anything else that asks for more is a finding.
WIDER_PERMISSIONS = {
    ("release.yml", "publish"): {"contents": "write"},
    ("release.yml", "portal-build"): {"contents": "read", "pages": "read"},
    ("release.yml", "portal-deploy"): {"pages": "write", "id-token": "write"},
}


def uses_lines(name: str) -> list[tuple[str, str]]:
    """Every ``uses:`` of a workflow as text: the reference and the rest of its line."""
    text = (WORKFLOWS_DIR / name).read_text(encoding="utf-8")
    found = [USES_LINE.match(line) for line in text.splitlines()]
    return [(m.group(1), m.group(2)) for m in found if m]


def test_the_workflows_are_the_three_this_repository_runs() -> None:
    # One workflow per event: CI for a pull request and a merge, Release for a tag, the
    # mutation sample for the weekly schedule.
    assert WORKFLOWS == ["ci.yml", "mutation.yml", "release.yml"]


@pytest.mark.parametrize("name", WORKFLOWS)
def test_every_action_is_pinned_to_a_commit_with_its_version_named(name: str) -> None:
    for reference, rest in uses_lines(name):
        if reference.startswith("./"):
            continue
        assert PINNED.match(reference), f"{name}: {reference} is not pinned to a full commit SHA"
        assert VERSION_COMMENT.search(rest), f"{name}: {reference} names no # vX.Y.Z"


def test_one_action_is_pinned_to_one_commit_across_the_workflows() -> None:
    # Dependabot moves every pin of an action in one pull request; two pins of one action
    # mean one of them was edited by hand and is now out of its view.
    pins: dict[str, set[str]] = {}
    for name in WORKFLOWS:
        for reference, _ in uses_lines(name):
            action, at, sha = reference.partition("@")
            if at:
                pins.setdefault(action, set()).add(sha)
    assert pins, "no workflow uses an action"
    assert {action: shas for action, shas in pins.items() if len(shas) > 1} == {}


@pytest.mark.parametrize("name", WORKFLOWS)
def test_no_check_is_excused_from_failing_the_run(name: str) -> None:
    workflow = load_workflow(name)
    assert "continue-on-error" not in all_strings(workflow), name
    for script in run_scripts(workflow):
        assert not re.search(r"\|\|\s*(true|:)", script), f"{name}: a failure is swallowed"


@pytest.mark.parametrize("name", WORKFLOWS)
def test_every_install_refuses_a_stale_lock(name: str) -> None:
    # `uv sync` without --locked re-resolves a lock that disagrees with pyproject.toml, so
    # a bump without `uv lock` would pass CI and stop the deploy, whose sync is --locked.
    syncs = [
        found.group(1)
        for script in run_scripts(load_workflow(name))
        for line in script.splitlines()
        if (found := UV_SYNC.search(line))
    ]
    assert all(LOCKED.search(arguments) for arguments in syncs), f"{name}: {syncs}"


@pytest.mark.parametrize("name", WORKFLOWS)
def test_run_scripts_carry_no_expressions(name: str) -> None:
    """Secrets and contexts enter a script through env:, never pasted into its text."""
    for text in run_scripts(load_workflow(name)):
        assert "${{" not in text, f"{name}: an expression is pasted into a run script"


@pytest.mark.parametrize("name", WORKFLOWS)
def test_the_token_reads_contents_only_unless_a_job_says_otherwise(name: str) -> None:
    assert load_workflow(name)["permissions"] == {"contents": "read"}


def runner_jobs(name: str) -> list[tuple[str, Mapping]]:
    """The jobs that run on a runner; a job that calls a workflow has no steps of its own."""
    jobs = load_workflow(name)["jobs"]
    return [(job_id, job) for job_id, job in jobs.items() if "uses" not in job]


@pytest.mark.parametrize("name", WORKFLOWS)
def test_every_job_is_bounded_in_time(name: str) -> None:
    for job_id, job in runner_jobs(name):
        minutes = job.get("timeout-minutes")
        assert isinstance(minutes, int), f"{name}: {job_id} has no timeout-minutes"
        assert 0 < minutes <= 90, f"{name}: {job_id} timeout {minutes}"


@pytest.mark.parametrize("name", WORKFLOWS)
def test_every_job_states_its_permissions(name: str) -> None:
    for job_id, job in runner_jobs(name):
        expected = WIDER_PERMISSIONS.get((name, job_id), READ_ONLY)
        assert job.get("permissions") == expected, f"{name}: {job_id}"


def test_every_wider_permission_names_a_job_that_exists() -> None:
    # An exception for a job that was renamed or removed would excuse nothing and hide
    # that the permission it was written for moved.
    for name, job_id in WIDER_PERMISSIONS:
        assert job_id in load_workflow(name)["jobs"], f"{name}: {job_id}"
