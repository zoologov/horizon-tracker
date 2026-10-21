"""horizon-tracker: scheduled check-in and check-out of a VMware Horizon VDI session.

The version is read from the installed distribution, whose metadata is built from
pyproject.toml ``[project] version`` - the one place a release sets it - so the package
carries no copy that could disagree with what was installed.
"""

from importlib.metadata import version

__version__ = version("horizon-tracker")
