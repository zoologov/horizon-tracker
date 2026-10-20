"""Finds the repository root: the nearest directory above this file holding ``pyproject.toml``.

Every test that reads a file of the project itself (the deploy units, the workflows, the
HTML Access fixture) asks this module, so no test counts its own parent directories.
"""

from functools import cache
from pathlib import Path

_MANIFEST = "pyproject.toml"


@cache
def repository_root() -> Path:
    """The directory holding the project's ``pyproject.toml``, walking up from this file."""
    here = Path(__file__).resolve()
    for directory in here.parents:
        if (directory / _MANIFEST).is_file():
            return directory
    raise FileNotFoundError(f"no {_MANIFEST} above {here}")
