"""Keep project-unit diagnostics and discard absolute runner-host unit diagnostics."""

import argparse
import re
import sys
from pathlib import Path

_HOST_FILE_DIAGNOSTIC = re.compile(r"^/[^:]+:[0-9]+:")


def project_diagnostics(output: str, units: Path) -> str:
    """Filter systemd output, keeping project, relative and unattributed diagnostics."""
    project_prefix = f"{units}/"
    kept = []
    for line in output.splitlines():
        if line.startswith(project_prefix) or _HOST_FILE_DIAGNOSTIC.match(line) is None:
            kept.append(line)
    return "".join(f"{line}\n" for line in kept)


def main() -> None:
    """Read systemd diagnostics on stdin and write those owned by the project units."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.write(project_diagnostics(sys.stdin.read(), args.units))


if __name__ == "__main__":
    main()
