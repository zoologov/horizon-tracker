"""Tests for the deploy workflow: what reaches the VPS, and what never reaches the log.

The step that builds ``.env`` is the one piece of the deploy that runs on the runner
alone, so it is executed here with stand-in secrets and variables, and its file is read
back with systemd's own parsing rules: every value must arrive literally, quotes,
backslashes and dollars included. The preflight and the time-zone check run here too,
against a fake ``ssh``. The rest is a contract with the VPS that only a real deploy
proves; here it is held to the commands the deployment guide publishes.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from horizon_tracker.domain.messages import Language
from horizon_tracker.infrastructure.config import Settings
from tests.support.systemd_env import parse_env_file
from tests.support.workflows import (
    DEPLOYMENT_GUIDE,
    ROOT,
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
# Not secret, so an environment variable rather than a secret, and optional the same way:
# undefined, it is left out of .env and the service speaks English (RFC HT-007). A hand
# edit of .env would not survive a deploy, so a host's language is set in horizon-vps.
OPTIONAL_VARIABLES = {"HT_LANGUAGE"}
# Per-host values, not secret, that no workflow literal may carry: the portal and the
# desktop have no default, so the preflight refuses a run without them.
REQUIRED_VARIABLES = {"HORIZON_URL", "HORIZON_DESKTOP"}
# Per-host as well, with the default the workflow states when the variable is undefined.
DEFAULTED_VARIABLES = {"HT_TIMEZONE": "UTC"}
VARIABLES = REQUIRED_VARIABLES | set(DEFAULTED_VARIABLES) | OPTIONAL_VARIABLES
# The schedule values of RFC HT-003 "API Changes", pinned here rather than read back
# from the workflow or the guide, which the contract test only holds equal.
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
PREFLIGHT = "Preflight: reach the VPS"
ZONE_CHECK = "Check the timers' time zone"
SUMMARY = "Deploy summary"
STEP_ORDER = [
    "Set up SSH",
    PREFLIGHT,
    "Update the code",
    ZONE_CHECK,
    BUILD_ENV,
    "Write .env",
    "Install the units",
    "Smoke: horizon probe",
    SUMMARY,
]
# Stand-ins chosen to break a naive writer: quotes of both kinds, a backslash, `$`,
# a backtick, `#`, `=`, outer spaces and non-ASCII.
STAND_INS = {
    "HORIZON_USERNAME": "EXAMPLE\\j.doe",
    "HORIZON_PASSWORD": " p@ss \"w0rd\" 'q' $HOME ${X} `id` \\n # ; = end ",
    "TELEGRAM_BOT_TOKEN": "123456:AA-bb_cc$dd",
    "TELEGRAM_CHAT_ID": "-1001234567890",
}
# What the horizon-vps environment of a test defines: a portal and a desktop name with a
# space in it, as a real launch item's title has.
VARIABLE_STAND_INS = {
    "HORIZON_URL": "https://horizon.example.com/portal/webclient/",
    "HORIZON_DESKTOP": "DEV desktop",
}
SECRET_EXPRESSION = re.compile(r"^\$\{\{\s*secrets\.([A-Z_]+)\s*\}\}$")
# ``vars.NAME``, or ``vars.NAME || 'default'``: GitHub's || yields the default for an
# undefined variable, which evaluates to the empty string.
VARIABLE_EXPRESSION = re.compile(r"^\$\{\{\s*vars\.([A-Z_]+)(?:\s*\|\|\s*'([^']*)')?\s*\}\}$")
BASH = shutil.which("bash")


def deploy() -> Mapping:
    return load_workflow("deploy.yml")


def script(name: str) -> str:
    return str(step_named(deploy(), "deploy", name)["run"])


def guide_contract() -> dict[str, str]:
    """The ``.env`` the deployment guide shows, read with systemd's rules."""
    text = DEPLOYMENT_GUIDE.read_text(encoding="utf-8")
    block = re.search(r"```ini\n(.*?)```", text, re.DOTALL)
    assert block, "the deployment guide has no ```ini block for .env"
    return parse_env_file(block.group(1))


def evaluate(value: object) -> str:
    """A step's env value as the runner sees it: stand-ins for what horizon-vps defines.

    Required secrets and variables are defined; an optional secret or variable is left
    undefined, as a fresh environment has it, so it evaluates to the empty string - or to
    the default its expression names.
    """
    secret = SECRET_EXPRESSION.match(str(value))
    variable = VARIABLE_EXPRESSION.match(str(value))
    if variable is not None:
        name, default = variable.group(1), variable.group(2)
        assert name in VARIABLES, name
        return VARIABLE_STAND_INS.get(name, default or "")
    if secret is None:
        return str(value)
    if secret.group(1) in OPTIONAL_SECRETS:
        return ""
    return STAND_INS[secret.group(1)]


def step_inputs(name: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """The environment step ``name`` runs with; ``overrides`` replace evaluated values."""
    declared = step_named(deploy(), "deploy", name)["env"]
    env = {key: evaluate(value) for key, value in declared.items()}
    env.update(overrides or {})
    return env


def run_step(
    name: str, tmp_path: Path, env: dict[str, str], path: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run step ``name``'s script under bash -eo pipefail, as the runner does."""
    assert BASH is not None
    base = {"PATH": path or os.environ["PATH"], "RUNNER_TEMP": str(tmp_path)}
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", script(name)],
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )


def build_env(
    tmp_path: Path, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the build step as the runner would: its env, stand-ins in place of secrets."""
    return run_step(BUILD_ENV, tmp_path, step_inputs(BUILD_ENV, overrides))


def built_values(tmp_path: Path) -> dict[str, str]:
    return parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))


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


def test_deploy_steps_run_in_the_order_the_guide_describes() -> None:
    names = [s["name"] for s in steps(deploy(), "deploy") if s.get("name") in STEP_ORDER]
    assert names == STEP_ORDER


# --- secrets ----------------------------------------------------------------------------


def test_every_secret_of_the_environment_is_used_and_no_other() -> None:
    named = {
        m.group(1) for s in all_strings(deploy()) for m in re.finditer(r"secrets\.([A-Z_]+)", s)
    }
    assert named == SECRETS | OPTIONAL_SECRETS


def test_every_variable_of_the_environment_is_used_and_no_other() -> None:
    named = {m.group(1) for s in all_strings(deploy()) for m in re.finditer(r"vars\.([A-Z_]+)", s)}
    assert named == VARIABLES


def test_the_portal_the_desktop_and_the_zone_are_read_from_the_environment() -> None:
    # Per-host values: a workflow literal would put one host's portal on every fork.
    env = step_named(deploy(), "deploy", BUILD_ENV)["env"]
    assert env["HORIZON_URL"] == "${{ vars.HORIZON_URL }}"
    assert env["HORIZON_DESKTOP"] == "${{ vars.HORIZON_DESKTOP }}"
    assert env["HT_TIMEZONE"] == "${{ vars.HT_TIMEZONE || 'UTC' }}"


def test_the_steps_that_read_a_variable_read_it_the_same_way() -> None:
    # The preflight refuses on the value the build writes; the zone check compares the
    # timers with the zone the build writes. One expression each, or they could diverge.
    build = step_named(deploy(), "deploy", BUILD_ENV)["env"]
    for step in (PREFLIGHT, ZONE_CHECK):
        for name, expression in step_named(deploy(), "deploy", step)["env"].items():
            assert build[name] == expression, (step, name)


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
def test_env_file_is_the_contract_the_guide_shows(tmp_path: Path) -> None:
    # A value the guide shows as <secret ...> or <variable ...> is the one the
    # environment supplied; every other value is shown as the workflow writes it.
    contract = guide_contract()
    inputs = step_inputs(BUILD_ENV)
    assert build_env(tmp_path).returncode == 0
    values = built_values(tmp_path)
    assert set(values) == set(contract)
    for name, shown in contract.items():
        expected = inputs[name] if shown.startswith("<") else shown
        assert values[name] == expected, name


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_env_file_carries_the_portal_and_the_desktop_the_environment_names(
    tmp_path: Path,
) -> None:
    assert build_env(tmp_path).returncode == 0
    values = built_values(tmp_path)
    for name, stand_in in VARIABLE_STAND_INS.items():
        assert values[name] == stand_in, name
    assert Settings.from_env(values).desktop == VARIABLE_STAND_INS["HORIZON_DESKTOP"]


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_an_undefined_time_zone_variable_writes_utc(tmp_path: Path) -> None:
    assert build_env(tmp_path).returncode == 0
    values = built_values(tmp_path)
    assert values["HT_TIMEZONE"] == "UTC"
    assert Settings.from_env(values).timezone.key == "UTC"


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_defined_time_zone_variable_reaches_the_settings(tmp_path: Path) -> None:
    assert build_env(tmp_path, {"HT_TIMEZONE": "Europe/Berlin"}).returncode == 0
    values = built_values(tmp_path)
    assert values["HT_TIMEZONE"] == "Europe/Berlin"
    assert Settings.from_env(values).timezone.key == "Europe/Berlin"


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
def test_an_undefined_language_variable_leaves_the_service_in_english(tmp_path: Path) -> None:
    result = build_env(tmp_path)
    assert result.returncode == 0, result.stderr
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert "HT_LANGUAGE" not in values
    assert Settings.from_env(values).language is Language.EN


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_defined_language_variable_reaches_the_settings(tmp_path: Path) -> None:
    result = build_env(tmp_path, {"HT_LANGUAGE": "ru"})
    assert result.returncode == 0, result.stderr
    values = parse_env_file((tmp_path / "horizon.env").read_text(encoding="utf-8"))
    assert values["HT_LANGUAGE"] == "ru"
    assert Settings.from_env(values).language is Language.RU


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


# --- preflight and summary --------------------------------------------------------------

CHANGES = re.compile(r"\b(install|mv|rm|git|uv|systemctl|systemd-run|chown|chmod)\b")


def test_the_preflight_reaches_the_vps_and_changes_nothing() -> None:
    text = script(PREFLIGHT)
    assert text.strip().startswith("set -euo pipefail")
    assert 'ssh vps "' in text
    assert "true" in text
    assert f"test -d {HOME}/.git" in text
    assert "sudo -n -u horizon true" in text
    assert not CHANGES.search(text.replace(f"{HOME}/.git", "")), text


def recording_ssh(bin_dir: Path, answer: str = "") -> Path:
    """An ``ssh`` that logs its arguments, prints ``answer`` and succeeds; returns the log."""
    bin_dir.mkdir()
    log = bin_dir.parent / "ssh.log"
    (bin_dir / "answer").write_text(answer, encoding="utf-8")
    ssh = bin_dir / "ssh"
    ssh.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> '{log}'\ncat '{bin_dir / 'answer'}'\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    log.touch()
    return log


def with_fake_ssh(tmp_path: Path, answer: str = "") -> tuple[str, Path]:
    log = recording_ssh(tmp_path / "bin", answer)
    return f"{tmp_path / 'bin'}:{os.environ['PATH']}", log


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize("name", sorted(REQUIRED_VARIABLES))
def test_the_preflight_refuses_a_run_without_the_portal_or_the_desktop(
    tmp_path: Path, name: str
) -> None:
    path, log = with_fake_ssh(tmp_path)
    result = run_step(PREFLIGHT, tmp_path, step_inputs(PREFLIGHT, {name: ""}), path)
    assert result.returncode == 1
    assert f"::error title=horizon-vps::{name} is not set" in result.stdout
    assert "docs/guides/deployment.md" in result.stdout
    assert log.read_text(encoding="utf-8") == "", "the VPS was reached"


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_preflight_with_the_portal_and_the_desktop_reaches_the_vps(tmp_path: Path) -> None:
    path, log = with_fake_ssh(tmp_path)
    result = run_step(PREFLIGHT, tmp_path, step_inputs(PREFLIGHT), path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"test -d {HOME}/.git" in log.read_text(encoding="utf-8")


def test_the_preflight_reads_the_portal_and_the_desktop_variables() -> None:
    env = step_named(deploy(), "deploy", PREFLIGHT)["env"]
    assert {name: env[name] for name in REQUIRED_VARIABLES} == {
        name: f"${{{{ vars.{name} }}}}" for name in REQUIRED_VARIABLES
    }


# --- the timers' time zone --------------------------------------------------------------


def shipped_calendars() -> str:
    """The ``OnCalendar=`` lines of the timers this commit ships, as grep -h prints them."""
    lines = [
        line
        for name in ("horizon-checkin.timer", "horizon-checkout.timer")
        for line in (ROOT / "deploy" / name).read_text(encoding="utf-8").splitlines()
        if line.startswith("OnCalendar=")
    ]
    assert len(lines) == 2, lines
    return "\n".join(lines) + "\n"


def shipped_zone() -> str:
    zones = {line.rsplit(" ", 1)[-1] for line in shipped_calendars().splitlines()}
    assert len(zones) == 1, zones
    return zones.pop()


def test_the_zone_check_reads_the_timers_the_deploy_installs() -> None:
    text = " ".join(script(ZONE_CHECK).split())
    assert text.startswith("set -euo pipefail")
    assert f"{HOME}/deploy/horizon-checkin.timer" in text
    assert f"{HOME}/deploy/horizon-checkout.timer" in text
    assert not CHANGES.search(text), text


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_zone_check_passes_when_the_timers_fire_in_ht_timezone(tmp_path: Path) -> None:
    path, _ = with_fake_ssh(tmp_path, shipped_calendars())
    env = step_inputs(ZONE_CHECK, {"HT_TIMEZONE": shipped_zone()})
    result = run_step(ZONE_CHECK, tmp_path, env, path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_zone_check_refuses_timers_in_another_zone(tmp_path: Path) -> None:
    # Timers firing in one zone while the service draws its moments in another start
    # every run before or after its range: no check-in would ever happen, silently.
    path, _ = with_fake_ssh(tmp_path, shipped_calendars())
    env = step_inputs(ZONE_CHECK, {"HT_TIMEZONE": "America/New_York"})
    result = run_step(ZONE_CHECK, tmp_path, env, path)
    assert result.returncode == 1
    assert "::error title=HT_TIMEZONE::" in result.stdout
    assert shipped_zone() in result.stdout
    assert "America/New_York" in result.stdout


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_an_undefined_zone_is_refused_against_timers_in_another_zone(tmp_path: Path) -> None:
    # The default is UTC; timers shipped in any other zone must not deploy unnoticed.
    path, _ = with_fake_ssh(tmp_path, "OnCalendar=*-*-* 07:30:00 Europe/Berlin\n")
    result = run_step(ZONE_CHECK, tmp_path, step_inputs(ZONE_CHECK), path)
    assert result.returncode == 1
    assert "HT_TIMEZONE is UTC" in result.stdout


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_zone_check_reads_both_timers(tmp_path: Path) -> None:
    # Only the check-out timer is in another zone: a check of the first line alone passes.
    calendars = "OnCalendar=*-*-* 07:30:00 UTC\nOnCalendar=*-*-* 16:30:00 Europe/Berlin\n"
    path, _ = with_fake_ssh(tmp_path, calendars)
    env = step_inputs(ZONE_CHECK, {"HT_TIMEZONE": "UTC"})
    result = run_step(ZONE_CHECK, tmp_path, env, path)
    assert result.returncode == 1
    assert "Europe/Berlin" in result.stdout


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_timer_without_a_zone_is_refused(tmp_path: Path) -> None:
    # Without a zone a timer fires in the host's local time, which no setting names.
    path, _ = with_fake_ssh(tmp_path, "OnCalendar=*-*-* 07:30:00\n")
    env = step_inputs(ZONE_CHECK, {"HT_TIMEZONE": "UTC"})
    result = run_step(ZONE_CHECK, tmp_path, env, path)
    assert result.returncode == 1


def test_the_probe_output_is_kept_for_the_summary() -> None:
    text = script("Smoke: horizon probe")
    assert '| tee "$RUNNER_TEMP/probe.txt"' in text
    assert text.strip().startswith("set -euo pipefail"), "without pipefail tee hides the probe"


def fake_ssh(bin_dir: Path) -> None:
    """An ``ssh`` that answers list-timers and refuses anything else."""
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        "  *\"list-timers 'horizon-*'\"*) echo 'NEXT LEFT UNIT horizon-checkin.timer' ;;\n"
        '  *) echo "unexpected: $*" >&2; exit 9 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)


def run_summary(tmp_path: Path, probe: str | None) -> tuple[subprocess.CompletedProcess[str], str]:
    assert BASH is not None
    fake_ssh(tmp_path / "bin")
    summary = tmp_path / "summary.md"
    if probe is not None:
        (tmp_path / "probe.txt").write_text(probe, encoding="utf-8")
    step = step_named(deploy(), "deploy", SUMMARY)
    assert step["env"] == {"DEPLOY_SHA": "${{ github.sha }}"}
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "example-owner/horizon-tracker",
        "DEPLOY_SHA": "0123456789abcdef0123456789abcdef01234567",
    }
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", str(step["run"])],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, summary.read_text(encoding="utf-8") if summary.exists() else ""


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_summary_names_the_commit_the_probe_and_the_timers(tmp_path: Path) -> None:
    result, summary = run_summary(tmp_path, "settings: ok\nportal: ok\n")
    assert result.returncode == 0, result.stderr
    assert "0123456789abcdef0123456789abcdef01234567" in summary
    assert "https://github.com/example-owner/horizon-tracker/commit/0123456789abcdef" in summary
    assert "settings: ok\nportal: ok" in summary
    assert "horizon-checkin.timer" in summary


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_the_summary_says_when_the_probe_never_ran(tmp_path: Path) -> None:
    result, summary = run_summary(tmp_path, None)
    assert result.returncode == 0, result.stderr
    assert "probe did not run" in summary


def test_the_summary_is_written_whatever_the_deploy_did_but_not_when_cancelled() -> None:
    assert step_named(deploy(), "deploy", SUMMARY)["if"] == "${{ !cancelled() }}"
