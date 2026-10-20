"""One ``horizon`` invocation over the fakes, in an interpreter of its own.

``python -m tests.support.cli_process <now> <args...>`` builds a fresh ``World`` at the
ISO wall time ``now`` and runs the command with the environment it was started with,
then prints the command's output and exits with its exit code. A test that starts two of
these runs the command twice with nothing shared but the environment: no module state,
no file, and a different string-hash salt in each process if the caller sets
``PYTHONHASHSEED`` differently.
"""

import sys
from datetime import datetime
from os import environ

from tests.support.cli_world import World


def main(argv: list[str]) -> int:
    """Run ``argv[1:]`` at the wall time ``argv[0]``; print the output, return the exit code."""
    now = datetime.fromisoformat(argv[0])
    if now.tzinfo is None:
        raise SystemExit(f"the wall time needs its zone, got {argv[0]!r}")
    world = World(now, desktop=environ.get("HORIZON_DESKTOP", "DEV desktop"))
    result = world.invoke(argv[1:], dict(environ))
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
