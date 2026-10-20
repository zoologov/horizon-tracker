"""Tests for the deploy workflow: what reaches the VPS, and what never reaches the log.

The step that builds ``.env`` is the one piece of the deploy that runs on the runner
alone, so it is executed here with stand-in secrets and its file is read back with
systemd's own parsing rules: every value must arrive literally, quotes, backslashes and
dollars included. The rest is a contract with the VPS that only a real deploy proves
(PLAN BEAD-13); here it is held to the commands BEAD-08 published.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from horizon_tracker.infrastructure.config import Settings
from tests.support.systemd_env import parse_env_file
from tests.support.workflows import (
    ROOT,
    RUNBOOK,
    WORKFLOWS_DIR,
    Mapping,
    all_strings,
    load_workflow,
    run_scripts,
    step_named,
    steps,
)

HOME = "/opt/horizon-tracker"
SECRETS = {
    "VPS_HOST",
    "VPS_USER",
    "VPS_SSH_KEY",
    "VPS_KNOWN_HOSTS",
    "HORIZON_USERNAME",
    "HORIZON_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}
# Read when the environment defines it, and absent from .env when it does not: an
# undefined secret evaluates to the empty string, and Settings then seeds the draw
# from HORIZON_USERNAME (RFC HT-003, "API Changes").
OPTIONAL_SECRETS = {"HT_JITTER_SEED"}
# The schedule values of RFC HT-003 "API Changes", pinned here rather than read back
# from the workflow or the RUNBOOK, which the contract test only holds equal.
SCHEDULE = {
    "HT_CHECKIN_RANGE": "07:30-08:10",
    "HT_CHECKOUT_RANGE": "16:30-17:10",
    "HT_SESSION_LENGTH_MINUTES": "540",
    "HT_SESSION_EXTRA_MAX_MINUTES": "10",
    "HT_WINDOW_GRACE_MINUTES": "5",
}
RETIRED = ("HT_CHECKIN_WINDOW", "HT_CHECKOUT_WINDOW")
SEED_STAND_IN = ' seed "q" $X `id` \\ é '
UNITS = sorted(p.name for p in (ROOT / "deploy").iterdir() if p.suffix in {".service", ".timer"})
TIMERS = "horizon-checkin.timer horizon-checkout.timer"
BUILD_ENV = "Build .env"
STEP_ORDER = [
    "Set up SSH",
    "Update the code",
    BUILD_ENV,
    "Write .env",
    "Install the units",
    "Smoke: horizon probe",
]
# Stand-ins chosen to break a naive writer: quotes of both kinds, a backslash, `$`,
# a backtick, `#`, `=`, outer spaces and non-ASCII.
STAND_INS = {
    "HORIZON_USERNAME": "ETALON\\j.doe",
    "HORIZON_PASSWORD": " p@ss \"w0rd\" 'q' $HOME ${X} `id` \\n # ; = end ",
    "TELEGRAM_BOT_TOKEN": "123456:AA-bb_cc$dd",
    "TELEGRAM_CHAT_ID": "-1001234567890",
}
SECRET_EXPRESSION = re.compile(r"^\$\{\{\s*secrets\.([A-Z_]+)\s*\}\}$")
BASH = shutil.which("bash")


def deploy() -> Mapping:
    return load_workflow("deploy.yml")


def script(name: str) -> str:
    return str(step_named(deploy(), "deploy", name)["run"])


def runbook_contract() -> dict[str, str]:
    """The ``.env`` RUNBOOK §2.2 shows, read with systemd's rules."""
    text = RUNBOOK.read_text(encoding="utf-8")
    block = re.search(r"```ini\n(.*?)```", text, re.DOTALL)
    assert block, "RUNBOOK has no ```ini block for .env"
    return parse_env_file(block.group(1))


def build_env(
    tmp_path: Path, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the build step as the runner would: its env, stand-ins in place of secrets.

    An optional secret is left undefined, as in the horizon-vps environment today, so it
    reaches the step as the empty string; ``overrides`` defines it.
    """
    assert BASH is not None
    env = {"PATH": os.environ["PATH"], "RUNNER_TEMP": str(tmp_path)}
    for key, value in step_named(deploy(), "deploy", BUILD_ENV)["env"].items():
        secret = SECRET_EXPRESSION.match(str(value))
        if secret is None:
            env[key] = str(value)
        elif secret.group(1) in OPTIONAL_SECRETS:
            env[key] = ""
        else:
            env[key] = STAND_INS[secret.group(1)]
    env.update(overrides or {})
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", script(BUILD_ENV)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


# --- triggers and jobs ------------------------------------------------------------------


def test_deploy_runs_on_push_to_main_and_by_hand_only() -> None:
    on = deploy()["on"]
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"branches": ["main"]}


def test_deploy_waits_for_the_full_ci_gate() -> None:
    jobs = deploy()["jobs"]
    assert jobs["gate"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["deploy"]["needs"] in ("gate", ["gate"])


def test_deploy_job_uses_the_horizon_vps_environment() -> None:
    environment = deploy()["jobs"]["deploy"]["environment"]
    name = environment["name"] if isinstance(environment, dict) else environment
    assert name == "horizon-vps"


def test_only_main_reaches_the_vps() -> None:
    assert deploy()["jobs"]["deploy"]["if"] == "github.ref == 'refs/heads/main'"


def test_deploys_never_overlap_and_never_cancel_each_other() -> None:
    concurrency = deploy()["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_deploy_steps_run_in_the_runbook_order() -> None:
    names = [s["name"] for s in steps(deploy(), "deploy") if s.get("name") in STEP_ORDER]
    assert names == STEP_ORDER


# --- secrets ----------------------------------------------------------------------------


def test_every_secret_of_the_environment_is_used_and_no_other() -> None:
    named = {
        m.group(1) for s in all_strings(deploy()) for m in re.finditer(r"secrets\.([A-Z_]+)", s)
    }
    assert named == SECRETS | OPTIONAL_SECRETS


@pytest.mark.parametrize("workflow", ["ci.yml", "deploy.yml"])
def test_run_scripts_carry_no_expressions(workflow: str) -> None:
    """Secrets and contexts enter a script through env:, never pasted into its text."""
    for text in run_scripts(load_workflow(workflow)):
        assert "${{" not in text, f"{workflow}: an expression is pasted into a run script"


def test_no_secret_is_echoed_to_the_log() -> None:
    secret_ref = re.compile(r"\$\{?(" + "|".join(sorted(SECRETS | OPTIONAL_SECRETS)) + r")\b")
    for text in run_scripts(deploy()):
        for line in text.splitlines():
            if not secret_ref.search(line):
                continue
            if re.search(r"\b(echo|printf)\b", line):
                # Only into a file: not to a descriptor (>&2 is the log too), not via tee.
                into_file = re.search(r">>?\s*[^&\s]", line) and "tee" not in line
                assert into_file, f"a secret is printed to the log: {line!r}"


def test_no_script_traces_its_commands() -> None:
    for text in run_scripts(deploy()):
        assert not re.search(r"set\s+-[a-z]*x|bash\s+-[a-z]*x", text), text


# --- .env -------------------------------------------------------------------------------


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_gives_systemd_every_value_literally(tmp_path: Path) -> None:
    result = build_env(tmp_path)
    assert result.returncode == 0, result.stderr
    env_file = tmp_path / "horizon.env"
    values = parse_env_file(env_file.read_text(encoding="utf-8"))
    for name, stand_in in STAND_INS.items():
        assert values[name] == stand_in, name


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_is_the_runbook_contract(tmp_path: Path) -> None:
    contract = runbook_contract()
    assert build_env(tmp_path).returncode == 0
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert set(values) == set(contract)
    for name, shown in contract.items():
        expected = STAND_INS[name] if shown.startswith("<") else shown
        assert values[name] == expected, name


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_carries_the_schedule_of_the_rfc(tmp_path: Path) -> None:
    assert build_env(tmp_path).returncode == 0
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert {name: values.get(name) for name in SCHEDULE} == SCHEDULE


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_names_no_retired_window(tmp_path: Path) -> None:
    # Settings refuses either name, even blank: the smoke probe and every run would exit 1.
    assert build_env(tmp_path).returncode == 0
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert not set(RETIRED) & set(values)
    assert not set(RETIRED) & set(step_named(deploy(), "deploy", BUILD_ENV)["env"])


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_is_accepted_by_the_settings_the_cli_loads(tmp_path: Path) -> None:
    assert build_env(tmp_path).returncode == 0
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    settings = Settings.from_env(values)
    assert settings.jitter_seed == STAND_INS["HORIZON_USERNAME"].encode("utf-8")


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_an_undefined_seed_secret_leaves_the_seed_unset(tmp_path: Path) -> None:
    result = build_env(tmp_path)
    assert result.returncode == 0, result.stderr
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert "HT_JITTER_SEED" not in values


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_defined_seed_secret_arrives_literally_and_unprinted(tmp_path: Path) -> None:
    result = build_env(tmp_path, {"HT_JITTER_SEED": SEED_STAND_IN})
    assert result.returncode == 0, result.stderr
    assert SEED_STAND_IN.strip() not in result.stdout + result.stderr
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert values["HT_JITTER_SEED"] == SEED_STAND_IN
    assert Settings.from_env(values).jitter_seed == SEED_STAND_IN.encode("utf-8")


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_is_private_to_its_owner(tmp_path: Path) -> None:
    assert build_env(tmp_path).returncode == 0
    assert (tmp_path / "horizon.env").stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_missing_secret_stops_the_deploy_by_name_only(tmp_path: Path) -> None:
    result = build_env(tmp_path, {"HORIZON_PASSWORD": ""})
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "HORIZON_PASSWORD" in output
    for stand_in in STAND_INS.values():
        assert stand_in.strip() not in output
    assert not (tmp_path / "horizon.env").exists()


def test_env_file_reaches_the_vps_as_horizon_0600_over_stdin() -> None:
    text = script("Write .env")
    assert f"install -m 600 -o horizon -g horizon /dev/stdin {HOME}/.env.new" in text
    assert f"mv -f {HOME}/.env.new {HOME}/.env" in text
    assert '< "$RUNNER_TEMP/horizon.env"' in text


def test_the_runner_copy_of_the_secrets_is_removed_whatever_happened() -> None:
    cleanup = [s for s in steps(deploy(), "deploy") if "rm -f" in str(s.get("run", ""))]
    assert len(cleanup) == 1
    assert cleanup[0]["if"] == "always()"
    assert '"$RUNNER_TEMP/horizon.env"' in cleanup[0]["run"]
    assert "~/.ssh/deploy_key" in cleanup[0]["run"]


# --- the VPS ----------------------------------------------------------------------------


def test_code_is_updated_by_horizon_to_the_pushed_commit() -> None:
    text = script("Update the code")
    assert f"sudo -u horizon git -C {HOME} fetch --prune origin" in text
    assert f"sudo -u horizon git -C {HOME} checkout --detach" in text
    assert "DEPLOY_SHA" in text
    assert f"sudo -u horizon bash -lc 'cd {HOME} && /usr/local/bin/uv sync --locked'" in text


def test_the_four_units_are_installed_and_reloaded() -> None:
    text = script("Install the units")
    for unit in UNITS:
        assert unit in text, unit
    assert "install -m 0644" in text
    assert "systemctl daemon-reload" in text


def test_only_timers_already_enabled_are_restarted() -> None:
    assert f"systemctl try-restart {TIMERS}" in script("Install the units")
    text = (WORKFLOWS_DIR / "deploy.yml").read_text(encoding="utf-8")
    assert not re.search(r"systemctl\s+(restart|start|enable|reenable)\b", text)


def test_smoke_probe_runs_as_horizon_with_the_units_environment() -> None:
    text = " ".join(script("Smoke: horizon probe").split())
    assert "systemd-run" in text
    for flag in (
        "--wait",
        "--pipe",
        "--uid=horizon",
        "--gid=horizon",
        f"--working-directory={HOME}",
        f"-p EnvironmentFile={HOME}/.env",
    ):
        assert flag in text, flag
    assert f"{HOME}/.venv/bin/horizon probe" in text
