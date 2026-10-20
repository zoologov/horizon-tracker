"""Tests for bootstrap.sh: what it changes on the VPS, and what it must leave to the owner.

The script runs under bash with a PATH holding only recording stubs, so every external
command it calls is logged and none is executed; a command without a stub is "not
found" and fails the run instead of reaching the host. The assertions read that log:
the units are installed and reloaded, the timers are never enabled or started, and
the secrets file is never named.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

DEPLOY_DIR = Path(__file__).resolve().parents[3] / "deploy"
BOOTSTRAP = DEPLOY_DIR / "bootstrap.sh"
HOME = "/opt/horizon-tracker"
UNIT_DIR = "/etc/systemd/system"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent")

RECORD = """#!{bash}
{{ printf '%s' "${{0##*/}}"; for arg in "$@"; do printf '\\t%s' "$arg"; done; printf '\\n'; }} \\
  >> "$STUB_LOG"
"""
BEHAVIOUR = {
    "id": 'echo "${STUB_UID:-0}"\n',
    "getent": 'exit "${STUB_GETENT_EXIT:-0}"\n',
}
STUBS = [
    "id",
    "getent",
    "useradd",
    "apt-get",
    "git",
    "cp",
    "rm",
    "chown",
    "curl",
    "env",
    "sudo",
    "install",
    "systemctl",
]
REAL = ["dirname"]


@dataclass(frozen=True)
class Run:
    returncode: int
    stdout: str
    stderr: str
    calls: list[list[str]]

    def called(self, command: str) -> list[list[str]]:
        return [call[1:] for call in self.calls if call[0] == command]


@pytest.fixture
def chrome(tmp_path: Path) -> Path:
    binary = tmp_path / "google-chrome"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def bootstrap(tmp_path: Path, chrome: Path, **env: str) -> Run:
    """Run bootstrap.sh against recording stubs and return what it called."""
    assert BASH is not None
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    for name in STUBS:
        stub = stubs / name
        stub.write_text(RECORD.format(bash=BASH) + BEHAVIOUR.get(name, ""), encoding="utf-8")
        stub.chmod(0o755)
    for name in REAL:
        real = shutil.which(name)
        assert real is not None, name
        (stubs / name).symlink_to(real)
    log = tmp_path / "calls.log"
    log.touch()
    result = subprocess.run(
        [BASH, str(BOOTSTRAP)],
        env={"PATH": str(stubs), "STUB_LOG": str(log), "HT_CHROME_PATH": str(chrome), **env},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    calls = [line.split("\t") for line in log.read_text(encoding="utf-8").splitlines()]
    return Run(result.returncode, result.stdout, result.stderr, calls)


def test_a_full_run_succeeds(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    assert run.returncode == 0, run.stderr


def test_refuses_to_run_without_root(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome, STUB_UID="1000")
    assert run.returncode == 1
    assert "root" in run.stderr
    assert {call[0] for call in run.calls} <= {"id"}


def test_missing_chrome_is_named_before_anything_changes(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-chrome"
    run = bootstrap(tmp_path, missing, STUB_GETENT_EXIT="2")
    assert run.returncode == 1
    assert str(missing) in run.stderr
    assert {call[0] for call in run.calls} <= {"id"}


def test_creates_a_nologin_system_user_homed_in_opt(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome, STUB_GETENT_EXIT="2")
    [useradd] = run.called("useradd")
    assert useradd[-1] == "horizon"
    assert "-r" in useradd
    assert useradd[useradd.index("-d") + 1] == HOME
    assert useradd[useradd.index("-s") + 1] == "/usr/sbin/nologin"


def test_an_existing_user_is_left_alone(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome, STUB_GETENT_EXIT="0")
    assert run.called("useradd") == []


def test_installs_the_runtime_packages(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    installs = [call for call in run.called("apt-get") if "install" in call]
    packages = {arg for call in installs for arg in call if not arg.startswith("-")}
    assert {"python3.12", "python3.12-venv", "git", "curl", "ca-certificates"} <= packages


def test_syncs_the_locked_environment_as_horizon(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    syncs = [call for call in run.called("sudo") if any("uv sync" in arg for arg in call)]
    assert syncs, run.calls
    for call in syncs:
        assert call[:2] == ["-u", "horizon"]
        assert any(f"cd '{HOME}'" in arg and "--locked" in arg for arg in call)


def test_creates_the_artifacts_directory_for_horizon(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    dirs = [call for call in run.called("install") if "-d" in call]
    assert any(
        call[-1] == f"{HOME}/artifacts" and "horizon" in call[call.index("-o") + 1] for call in dirs
    ), dirs


def test_installs_every_unit_and_reloads_systemd(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    shipped = {p.name for p in DEPLOY_DIR.iterdir() if p.suffix in {".service", ".timer"}}
    installed = {
        Path(call[-1]).name for call in run.called("install") if call[-1].startswith(f"{UNIT_DIR}/")
    }
    assert installed == shipped
    assert ["daemon-reload"] in run.called("systemctl")


def test_never_enables_or_starts_a_unit(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    assert run.called("systemctl") == [["daemon-reload"]]


def test_never_names_the_secrets_file(tmp_path: Path, chrome: Path) -> None:
    run = bootstrap(tmp_path, chrome)
    assert not [call for call in run.calls if any(".env" in arg for arg in call)]


def test_closing_lines_hand_the_env_and_the_timers_to_the_owner(
    tmp_path: Path, chrome: Path
) -> None:
    run = bootstrap(tmp_path, chrome)
    closing = run.stdout.strip().splitlines()[-4:]
    text = "\n".join(closing)
    assert ".env" in text
    assert "systemctl enable --now horizon-checkin.timer horizon-checkout.timer" in text
