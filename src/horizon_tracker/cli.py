"""Command-line entry point: ``horizon``."""

from __future__ import annotations

import click

from horizon_tracker import __version__


@click.group()
@click.version_option(__version__, prog_name="horizon")
def main() -> None:
    """Scheduled check-in and check-out of a VMware Horizon VDI session."""
