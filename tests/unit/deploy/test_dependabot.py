"""Tests for Dependabot: the pinned actions and the locked dependencies are both watched.

A commit SHA cannot be moved by its owner, which is why the workflows pin to one - and
also why nothing moves it forward on its own. Dependabot is what does, weekly, with the
minor and patch bumps of an ecosystem in one pull request so they arrive as one review.
"""

from typing import Any

import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; the dict is narrowed below

from tests.support.workflows import ROOT

ECOSYSTEMS = {"github-actions", "uv"}


def updates() -> list[dict[str, Any]]:
    data = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["version"] == 2
    found = data["updates"]
    assert isinstance(found, list)
    return found


def test_the_actions_and_the_lock_are_both_watched() -> None:
    assert sorted(u["package-ecosystem"] for u in updates()) == sorted(ECOSYSTEMS)


def test_each_ecosystem_is_read_from_the_root_weekly() -> None:
    for update in updates():
        assert update["directory"] == "/", update["package-ecosystem"]
        assert update["schedule"]["interval"] == "weekly", update["package-ecosystem"]


def test_minor_and_patch_bumps_arrive_as_one_pull_request() -> None:
    for update in updates():
        groups = update["groups"]
        assert len(groups) == 1, update["package-ecosystem"]
        (group,) = groups.values()
        assert sorted(group["update-types"]) == ["minor", "patch"]
        assert group["patterns"] == ["*"]
