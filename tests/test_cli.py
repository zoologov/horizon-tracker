from click.testing import CliRunner

from horizon_tracker import __version__
from horizon_tracker.cli import main


def test_version_is_reported() -> None:
    result = CliRunner().invoke(main, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output
