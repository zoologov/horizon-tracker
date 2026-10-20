"""Loads the GitHub Actions workflows as data, so tests read jobs and steps, not text.

PyYAML is not a direct dependency: it arrives with ``libcst`` (through ``mutmut`` in the
dev extra) as ``yaml`` on CPython 3.12 and as its free-threading fork ``yaml_ft`` on
3.13, with the same API. Either is taken; with neither the tests fail by name instead
of skipping, because a skipped guard over the deploy reads as a green one.
"""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
RUNBOOK = ROOT / "deploy" / "RUNBOOK.md"

# A workflow is untyped YAML; the tests narrow each value as they read it.
Mapping = dict[str, Any]


def _yaml() -> ModuleType:
    for name in ("yaml", "yaml_ft"):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError:
            continue
    pytest.fail("neither yaml nor yaml_ft is importable: `uv sync --extra dev` brings one")


def load_workflow(file_name: str) -> Mapping:
    """The workflow as a mapping; YAML 1.1 reads the bare key ``on`` as True, undone here."""
    data = _yaml().safe_load((WORKFLOWS_DIR / file_name).read_text(encoding="utf-8"))
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
