"""Tests for the graph annotations: every module names its layer, the absence module its feature."""

from pathlib import Path

import pytest

from tests.support.repository_root import repository_root

PACKAGE = repository_root() / "src" / "horizon_tracker"
LAYERS = ("domain", "application", "infrastructure")


def _modules(layer: str) -> list[Path]:
    return sorted(path for path in (PACKAGE / layer).glob("*.py") if path.name != "__init__.py")


@pytest.mark.parametrize(
    "module",
    [module for layer in LAYERS for module in _modules(layer)],
    ids=lambda module: f"{module.parent.name}/{module.name}",
)
def test_every_layer_module_names_its_layer(module: Path) -> None:
    lines = module.read_text(encoding="utf-8").splitlines()

    assert f"# beadloom:domain={module.parent.name}" in lines


def test_the_absence_module_names_its_feature() -> None:
    lines = (PACKAGE / "domain" / "absence.py").read_text(encoding="utf-8").splitlines()

    assert "# beadloom:feature=absence" in lines
