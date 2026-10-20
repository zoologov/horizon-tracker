"""Loads the GitHub Actions workflows as data, so tests read jobs and steps, not text.

PyYAML is a direct dev dependency, so ``yaml`` is importable wherever
``uv sync --extra dev`` ran; without it the tests fail at import by name instead of
skipping, because a skipped guard over the deploy reads as a green one.
"""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; the dict is narrowed below

from tests.support.repository_root import repository_root

ROOT: Path = repository_root()
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
RUNBOOK = ROOT / "deploy" / "RUNBOOK.md"

# A workflow is untyped YAML; the tests narrow each value as they read it.
Mapping = dict[str, Any]


def load_workflow(file_name: str) -> Mapping:
    """The workflow as a mapping; YAML 1.1 reads the bare key ``on`` as True, undone here."""
    data = yaml.safe_load((WORKFLOWS_DIR / file_name).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{file_name}: not a mapping"
    if True in data:
        data["on"] = data.pop(True)
    return data


def steps(workflow: Mapping, job: str) -> list[Mapping]:
    """The steps of ``job`` in order."""
    found = workflow["jobs"][job].get("steps", [])
    assert isinstance(found, list)
    return found


def step_named(workflow: Mapping, job: str, name: str) -> Mapping:
    """The one step of ``job`` whose name is ``name``."""
    matches = [step for step in steps(workflow, job) if step.get("name") == name]
    assert len(matches) == 1, f"{job}: expected one step named {name!r}, got {len(matches)}"
    return matches[0]


def run_scripts(workflow: Mapping) -> list[str]:
    """Every ``run:`` script of every job."""
    return [
        str(step["run"])
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "run" in step
    ]


def all_strings(node: object) -> list[str]:
    """Every string anywhere in a YAML tree, keys included."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in (*all_strings(k), *all_strings(v))]
    if isinstance(node, list):
        return [s for item in node for s in all_strings(item)]
    return []
