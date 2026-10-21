"""Tests for the release workflow: what a tag must be, what reaches the VPS, what is published.

A release is a tag on main. ``verify`` decides whether a tag is one, so its steps are run
here in a throwaway git repository - a tag off main, a version pyproject.toml does not
declare, a CHANGELOG without the section: each must be refused by the check that names
it. ``gate`` is the full CI on the tag's commit, and every later job starts only when the
one before it passed.

The step that builds ``.env`` is the one piece of the deploy that runs on the runner
alone, so it is executed here with stand-in secrets and variables, and its file is read
back with systemd's own parsing rules: every value must arrive literally, quotes,
backslashes and dollars included. The preflight and the time-zone check run here too,
against a fake ``ssh``; the publishing step runs against a fake ``gh``. The rest is a
contract with the VPS and with GitHub that only a real release proves; here it is held to
the commands the deployment guide publishes and the steps the portal generator writes.
"""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs; the dict is narrowed below

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


def release() -> Mapping:
    return load_workflow("release.yml")


def script(name: str) -> str:
    return str(step_named(release(), "deploy", name)["run"])


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
    declared = step_named(release(), "deploy", name)["env"]
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

RELEASE_TAG_FILTER = "v[0-9]+.[0-9]+.[0-9]+"
VERIFIED = "${{ needs.verify.outputs.%s }}"
# Each job starts only when every job it names passed: no job carries an `if:` that would
# let it run after a failure (always(), failure()) or skip a check.
CHAIN = {
    "verify": set(),
    "gate": {"verify"},
    "deploy": {"verify", "gate"},
    "publish": {"verify", "deploy"},
    "portal-build": {"verify", "publish"},
    "portal-deploy": {"portal-build"},
}


def needs(name: str) -> set[str]:
    value = release()["jobs"][name].get("needs", [])
    return {value} if isinstance(value, str) else set(value)


def test_a_release_starts_from_a_release_tag_or_by_hand_only() -> None:
    # A push to main is CI's event; nothing it starts reaches the VPS. The filter takes
    # MAJOR.MINOR.PATCH only, so a pre-release tag starts nothing.
    on = release()["on"]
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": [RELEASE_TAG_FILTER]}


def test_a_release_by_hand_names_the_tag_it_deploys_again() -> None:
    inputs = release()["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"tag"}
    assert inputs["tag"]["required"] is True
    assert inputs["tag"]["type"] == "string"


def test_the_jobs_run_in_the_release_order() -> None:
    assert list(release()["jobs"]) == list(CHAIN)


@pytest.mark.parametrize("name", list(CHAIN))
def test_each_job_starts_only_when_the_one_before_it_passed(name: str) -> None:
    assert needs(name) == CHAIN[name]
    assert "if" not in release()["jobs"][name]


def test_the_gate_is_the_full_ci_on_the_tags_commit() -> None:
    # The full CI, not a reduced copy of it, and on the commit the release deploys: on a
    # redeploy by hand the run's own commit is main's head, not the tag's.
    gate = release()["jobs"]["gate"]
    assert gate["uses"] == "./.github/workflows/ci.yml"
    assert gate["with"] == {"ref": VERIFIED % "sha"}


def test_deploy_job_uses_the_horizon_vps_environment() -> None:
    environment = release()["jobs"]["deploy"]["environment"]
    name = environment["name"] if isinstance(environment, dict) else environment
    assert name == "horizon-vps"


def test_deploys_never_overlap_and_never_cancel_each_other() -> None:
    concurrency = release()["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_deploy_steps_run_in_the_order_the_guide_describes() -> None:
    names = [s["name"] for s in steps(release(), "deploy") if s.get("name") in STEP_ORDER]
    assert names == STEP_ORDER


# --- secrets ----------------------------------------------------------------------------


def test_every_secret_of_the_environment_is_used_and_no_other() -> None:
    named = {
        m.group(1) for s in all_strings(release()) for m in re.finditer(r"secrets\.([A-Z_]+)", s)
    }
    assert named == SECRETS | OPTIONAL_SECRETS


def test_every_variable_of_the_environment_is_used_and_no_other() -> None:
    named = {m.group(1) for s in all_strings(release()) for m in re.finditer(r"vars\.([A-Z_]+)", s)}
    assert named == VARIABLES


def test_the_portal_the_desktop_and_the_zone_are_read_from_the_environment() -> None:
    # Per-host values: a workflow literal would put one host's portal on every fork.
    env = step_named(release(), "deploy", BUILD_ENV)["env"]
    assert env["HORIZON_URL"] == "${{ vars.HORIZON_URL }}"
    assert env["HORIZON_DESKTOP"] == "${{ vars.HORIZON_DESKTOP }}"
    assert env["HT_TIMEZONE"] == "${{ vars.HT_TIMEZONE || 'UTC' }}"


def test_the_steps_that_read_a_variable_read_it_the_same_way() -> None:
    # The preflight refuses on the value the build writes; the zone check compares the
    # timers with the zone the build writes. One expression each, or they could diverge.
    build = step_named(release(), "deploy", BUILD_ENV)["env"]
    for step in (PREFLIGHT, ZONE_CHECK):
        for name, expression in step_named(release(), "deploy", step)["env"].items():
            assert build[name] == expression, (step, name)


def test_no_secret_is_echoed_to_the_log() -> None:
    secret_ref = re.compile(r"\$\{?(" + "|".join(sorted(SECRETS | OPTIONAL_SECRETS)) + r")\b")
    for text in run_scripts(release()):
        for line in text.splitlines():
            if not secret_ref.search(line):
                continue
            if re.search(r"\b(echo|printf)\b", line):
                # Only into a file: not to a descriptor (>&2 is the log too), not via tee.
                into_file = re.search(r">>?\s*[^&\s]", line) and "tee" not in line
                assert into_file, f"a secret is printed to the log: {line!r}"


def test_no_script_traces_its_commands() -> None:
    for text in run_scripts(release()):
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
    assert not set(RETIRED) & set(step_named(release(), "deploy", BUILD_ENV)["env"])


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
    cleanup = [s for s in steps(release(), "deploy") if "rm -f" in str(s.get("run", ""))]
    assert len(cleanup) == 1
    assert cleanup[0]["if"] == "always()"
    assert '"$RUNNER_TEMP/horizon.env"' in cleanup[0]["run"]
    assert "~/.ssh/deploy_key" in cleanup[0]["run"]


# --- the VPS ----------------------------------------------------------------------------


def test_code_is_updated_by_horizon_to_the_tags_commit() -> None:
    assert step_named(release(), "deploy", "Update the code")["env"] == {
        "DEPLOY_SHA": VERIFIED % "sha"
    }
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
    text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
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
    env = step_named(release(), "deploy", PREFLIGHT)["env"]
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
    step = step_named(release(), "deploy", SUMMARY)
    assert step["env"] == {
        "DEPLOY_SHA": VERIFIED % "sha",
        "RELEASE_TAG": VERIFIED % "tag",
        "RELEASE_VERSION": VERIFIED % "version",
    }
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "example-owner/horizon-tracker",
        "DEPLOY_SHA": "0123456789abcdef0123456789abcdef01234567",
        "RELEASE_TAG": "v1.2.3",
        "RELEASE_VERSION": "1.2.3",
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
def test_the_summary_names_the_tag_the_version_the_commit_the_probe_and_the_timers(
    tmp_path: Path,
) -> None:
    result, summary = run_summary(tmp_path, "settings: ok\nportal: ok\n")
    assert result.returncode == 0, result.stderr
    assert "Tag: `v1.2.3`, version 1.2.3" in summary
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
    assert step_named(release(), "deploy", SUMMARY)["if"] == "${{ !cancelled() }}"


# --- verify -----------------------------------------------------------------------------

VERIFY = "verify"
RESOLVE = "Resolve the tag"
ON_MAIN = "The tag is on main"
VERSION_CHECK = "pyproject.toml declares the tag's version"
CHANGELOG_CHECK = "CHANGELOG.md holds the tag's section"
KEEP_NOTES = "Keep the release notes"
NOTES_ARTIFACT = "release-notes"
NOTES_DIR = "${{ runner.temp }}/release-notes"
GIT = shutil.which("git")
EXPRESSION = re.compile(r"^\$\{\{\s*([\w.-]+)\s*\}\}$")
# The fixtures release 3.1.4, a version this project has never had: a fixture that named
# the project's own version would be read by `beadloom version-surface` as a check of it.
RELEASED_SECTION = """The first release: the service has run in production since HT-001.

### Added

- Check-in and check-out on the working days of the production calendar."""
LINK_REFERENCES = """[Unreleased]: https://github.com/example-owner/horizon-tracker/compare/v3.1.4...HEAD
[3.1.4]: https://github.com/example-owner/horizon-tracker/releases/tag/v3.1.4
"""


def changelog(*sections: tuple[str, str]) -> str:
    """A Keep a Changelog file: the given ``(heading, body)`` sections, then the links."""
    parts = ["# Changelog\n\n## [Unreleased]\n\n- Nothing yet.\n"]
    parts += [f"\n{heading}\n\n{body}\n" for heading, body in sections]
    return "".join(parts) + "\n" + LINK_REFERENCES


RELEASED = changelog(("## [3.1.4] - 2026-10-21", RELEASED_SECTION))


def git(repo: Path, *args: str) -> str:
    assert GIT is not None
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(repo.parent),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Release Test",
        "GIT_AUTHOR_EMAIL": "release@example.com",
        "GIT_COMMITTER_NAME": "Release Test",
        "GIT_COMMITTER_EMAIL": "release@example.com",
    }
    done = subprocess.run(
        [GIT, "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def commit(repo: Path, files: dict[str, str | None], message: str) -> str:
    for name, text in files.items():
        if text is None:
            (repo / name).unlink(missing_ok=True)
        else:
            (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def pyproject(version: str) -> str:
    return f'[project]\nname = "horizon-tracker"\nversion = "{version}"\n'


def release_repo(
    tmp_path: Path,
    *,
    version: str = "3.1.4",
    log: str | None = RELEASED,
    on_main: bool = True,
    tag: str = "v3.1.4",
) -> Path:
    """A clone as verify's checkout leaves it: main fetched as origin/main, the tag present."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    base = commit(repo, {"README.md": "horizon-tracker\n"}, "base")
    released = commit(repo, {"pyproject.toml": pyproject(version), "CHANGELOG.md": log}, "release")
    git(repo, "update-ref", "refs/remotes/origin/main", released if on_main else base)
    git(repo, "tag", "-a", tag, "-m", tag, released)
    return repo


def evaluate_expression(value: object, context: dict[str, str]) -> str:
    match = EXPRESSION.match(str(value))
    if match is None:
        return str(value)
    assert match.group(1) in context, f"verify reads {match.group(1)}, which no test supplies"
    return context[match.group(1)]


def read_outputs(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    return {key: value for key, _, value in (line.partition("=") for line in lines if line)}


@dataclass
class VerifyRun:
    """What a run of the verify job left: the step that failed, its log, outputs, notes."""

    failed: str | None = None
    output: str = ""
    outputs: dict[str, str] = field(default_factory=dict)
    notes: str | None = None


def run_verify(
    repo: Path, tmp_path: Path, *, event: str = "push", tag: str = "v3.1.4"
) -> VerifyRun:
    """Every run step of verify in order, stopping at the first that fails.

    A push names the tag as the run's ref; a dispatch runs on main and names the tag as
    its input. Step outputs reach the later steps through their env, as on a runner.
    """
    assert BASH is not None
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    context = {
        "github.event_name": event,
        "github.ref_name": tag if event == "push" else "main",
        "inputs.tag": "" if event == "push" else tag,
        "runner.temp": str(runner_temp),
    }
    python_first = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    run = VerifyRun()
    for index, step in enumerate(steps(release(), VERIFY)):
        if "run" not in step:
            continue
        output_file = runner_temp / f"output-{index}"
        env = {
            "PATH": python_first,
            "HOME": str(tmp_path),
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_OUTPUT": str(output_file),
            **{k: evaluate_expression(v, context) for k, v in step.get("env", {}).items()},
        }
        done = subprocess.run(
            [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", str(step["run"])],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        run.output += done.stdout + done.stderr
        if done.returncode != 0:
            run.failed = str(step["name"])
            return run
        for key, value in read_outputs(output_file).items():
            context[f"steps.{step['id']}.outputs.{key}"] = value
    resolve_id = step_named(release(), VERIFY, RESOLVE)["id"]
    prefix = f"steps.{resolve_id}.outputs."
    run.outputs = {k.removeprefix(prefix): v for k, v in context.items() if k.startswith(prefix)}
    notes = runner_temp / "release-notes" / "notes.md"
    run.notes = notes.read_text(encoding="utf-8") if notes.exists() else None
    return run


needs_git = pytest.mark.skipif(BASH is None or GIT is None, reason="bash or git absent")


def test_verify_reads_the_whole_history_without_keeping_the_token() -> None:
    # The ancestry check needs main's history and every tag, not the tag's commit alone.
    checkout = steps(release(), VERIFY)[0]
    assert str(checkout["uses"]).startswith("actions/checkout@")
    assert checkout["with"] == {"fetch-depth": 0, "persist-credentials": False}


def test_verify_checks_in_the_order_a_refusal_is_cheapest_to_read() -> None:
    names = [s["name"] for s in steps(release(), VERIFY) if "run" in s]
    assert names == [RESOLVE, ON_MAIN, VERSION_CHECK, CHANGELOG_CHECK]


def test_verify_hands_the_tag_the_version_and_the_commit_to_the_later_jobs() -> None:
    resolve_id = step_named(release(), VERIFY, RESOLVE)["id"]
    assert release()["jobs"][VERIFY]["outputs"] == {
        key: f"${{{{ steps.{resolve_id}.outputs.{key} }}}}" for key in ("tag", "version", "sha")
    }


def test_the_notes_are_kept_for_publish() -> None:
    keep = step_named(release(), VERIFY, KEEP_NOTES)
    assert str(keep["uses"]).startswith("actions/upload-artifact@")
    assert keep["with"]["name"] == NOTES_ARTIFACT
    assert keep["with"]["path"] == f"{NOTES_DIR}/notes.md"
    assert keep["with"]["if-no-files-found"] == "error"


@needs_git
def test_a_release_tag_on_main_with_its_version_and_section_passes(tmp_path: Path) -> None:
    repo = release_repo(tmp_path)
    run = run_verify(repo, tmp_path)
    assert run.failed is None, run.output
    assert run.outputs == {
        "tag": "v3.1.4",
        "version": "3.1.4",
        "sha": git(repo, "rev-parse", "v3.1.4^{commit}"),
    }


@needs_git
def test_the_release_notes_are_the_tags_section_alone(tmp_path: Path) -> None:
    # Neither the [Unreleased] section above it nor the link references below it.
    run = run_verify(release_repo(tmp_path), tmp_path)
    assert run.failed is None, run.output
    assert run.notes == RELEASED_SECTION + "\n"


@needs_git
def test_the_release_notes_stop_at_the_next_section(tmp_path: Path) -> None:
    log = changelog(
        ("## [3.2.0] - 2026-11-02", "### Added\n\n- A second command."),
        ("## [3.1.4] - 2026-10-21", RELEASED_SECTION),
    )
    repo = release_repo(tmp_path, version="3.2.0", log=log, tag="v3.2.0")
    run = run_verify(repo, tmp_path, tag="v3.2.0")
    assert run.failed is None, run.output
    assert run.notes == "### Added\n\n- A second command.\n"


@needs_git
def test_a_redeploy_by_hand_releases_the_commit_of_the_named_tag(tmp_path: Path) -> None:
    # The run's own commit is main's head, which has moved past the tag since.
    repo = release_repo(tmp_path)
    head = commit(repo, {"README.md": "moved on\n"}, "after the release")
    git(repo, "update-ref", "refs/remotes/origin/main", head)
    run = run_verify(repo, tmp_path, event="workflow_dispatch")
    assert run.failed is None, run.output
    assert run.outputs["sha"] == git(repo, "rev-parse", "v3.1.4^{commit}")
    assert run.outputs["sha"] != head


@needs_git
@pytest.mark.parametrize(
    "tag", ["v1.0", "3.1.4", "v3.1.4-rc.1", "v03.1.4", "v3.1.4.1", "main", "v3.1.4 ", ""]
)
def test_a_name_that_is_no_release_tag_is_refused(tmp_path: Path, tag: str) -> None:
    run = run_verify(release_repo(tmp_path), tmp_path, event="workflow_dispatch", tag=tag)
    assert run.failed == RESOLVE
    assert "::error title=verify: tag::" in run.output
    assert "vMAJOR.MINOR.PATCH" in run.output


@needs_git
def test_a_redeploy_of_a_tag_that_does_not_exist_is_refused(tmp_path: Path) -> None:
    run = run_verify(release_repo(tmp_path), tmp_path, event="workflow_dispatch", tag="v2.0.0")
    assert run.failed == RESOLVE
    assert "::error title=verify: tag::there is no tag v2.0.0" in run.output


@needs_git
def test_a_tag_off_main_is_refused(tmp_path: Path) -> None:
    run = run_verify(release_repo(tmp_path, on_main=False), tmp_path)
    assert run.failed == ON_MAIN
    assert "::error title=verify: main::v3.1.4" in run.output
    assert "is not on main" in run.output


@needs_git
def test_a_tag_whose_pyproject_declares_another_version_is_refused(tmp_path: Path) -> None:
    run = run_verify(release_repo(tmp_path, version="0.9.0"), tmp_path)
    assert run.failed == VERSION_CHECK
    assert "::error title=verify: version::" in run.output
    assert "declares 0.9.0" in run.output
    assert "3.1.4" in run.output


@needs_git
@pytest.mark.parametrize(
    ("log", "said"),
    [
        (None, "there is no CHANGELOG.md"),
        (changelog(("## [0.9.0] - 2026-01-01", "- Earlier.")), "has no section ## [3.1.4]"),
        (changelog(("## [3.1.4]", RELEASED_SECTION)), "has no section ## [3.1.4]"),
        (changelog(("## [3.1.4] - 21.10.2026", RELEASED_SECTION)), "carries no date"),
        (changelog(("## [3.1.4] - 2026-10-21", "")), "is empty"),
    ],
    ids=["no-changelog", "no-section", "no-date", "not-iso-date", "empty-section"],
)
def test_a_tag_without_a_dated_changelog_section_is_refused(
    tmp_path: Path, log: str | None, said: str
) -> None:
    run = run_verify(release_repo(tmp_path, log=log), tmp_path)
    assert run.failed == CHANGELOG_CHECK
    assert "::error title=verify: changelog::" in run.output
    assert said in run.output


# --- publish ----------------------------------------------------------------------------

PUBLISH = "publish"
PUBLISH_STEP = "Publish the GitHub Release"
ASSETS = ("horizon_tracker-3.1.4-py3-none-any.whl", "horizon_tracker-3.1.4.tar.gz")


def test_publish_builds_from_the_tags_commit_without_keeping_the_token() -> None:
    checkout = steps(release(), PUBLISH)[0]
    assert str(checkout["uses"]).startswith("actions/checkout@")
    assert checkout["with"] == {"ref": VERIFIED % "sha", "persist-credentials": False}


def test_publish_builds_the_wheel_and_the_sdist_then_reads_the_notes_verify_kept() -> None:
    signatures = [
        str(s.get("uses", s.get("run", ""))).split("@")[0] for s in steps(release(), PUBLISH)
    ]
    assert signatures[1:] == [
        "astral-sh/setup-uv",
        "uv build",
        "actions/download-artifact",
        signatures[-1],
    ]
    download = steps(release(), PUBLISH)[3]
    assert download["with"] == {"name": NOTES_ARTIFACT, "path": NOTES_DIR}


def test_publish_reaches_github_with_the_runs_own_token_only() -> None:
    assert step_named(release(), PUBLISH, PUBLISH_STEP)["env"] == {
        "GH_TOKEN": "${{ github.token }}",
        "GH_REPO": "${{ github.repository }}",
        "TAG": VERIFIED % "tag",
    }


def recording_gh(bin_dir: Path, *, release_exists: bool) -> Path:
    """A ``gh`` that logs its arguments; ``release view`` answers whether the release exists."""
    bin_dir.mkdir()
    log = bin_dir.parent / "gh.log"
    log.touch()
    view_exit = 0 if release_exists else 1
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        f'if [ "$1 $2" = "release view" ]; then exit {view_exit}; fi\n',
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return log


def run_publish(
    tmp_path: Path, *, release_exists: bool, assets: tuple[str, ...] = ASSETS
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    assert BASH is not None
    work = tmp_path / "work"
    (work / "dist").mkdir(parents=True)
    for asset in assets:
        (work / "dist" / asset).write_text("", encoding="utf-8")
    notes = tmp_path / "release-notes"
    notes.mkdir()
    (notes / "notes.md").write_text(RELEASED_SECTION + "\n", encoding="utf-8")
    log = recording_gh(tmp_path / "bin", release_exists=release_exists)
    env = {
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "GH_TOKEN": "stand-in-token",
        "GH_REPO": "example-owner/horizon-tracker",
        "TAG": "v3.1.4",
    }
    script_text = str(step_named(release(), PUBLISH, PUBLISH_STEP)["run"])
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", script_text],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_new_release_is_created_with_the_notes_and_both_assets(tmp_path: Path) -> None:
    result, calls = run_publish(tmp_path, release_exists=False)
    assert result.returncode == 0, result.stdout + result.stderr
    (create,) = [c for c in calls if c.startswith("release create")]
    notes = f"--notes-file {tmp_path / 'release-notes' / 'notes.md'}"
    assert create == (
        f"release create v3.1.4 dist/{ASSETS[1]} dist/{ASSETS[0]} "
        f"--title v3.1.4 {notes} --verify-tag"
    )
    assert not [c for c in calls if c.startswith(("release edit", "release upload"))]


@pytest.mark.skipif(BASH is None, reason="bash absent")
def test_a_release_that_exists_is_edited_and_its_assets_replaced(tmp_path: Path) -> None:
    # A tag cut through the Releases page, and a redeploy by hand, both find the release.
    result, calls = run_publish(tmp_path, release_exists=True)
    assert result.returncode == 0, result.stdout + result.stderr
    notes = f"--notes-file {tmp_path / 'release-notes' / 'notes.md'}"
    assert f"release edit v3.1.4 --title v3.1.4 {notes}" in calls
    assert f"release upload v3.1.4 dist/{ASSETS[1]} dist/{ASSETS[0]} --clobber" in calls
    assert not [c for c in calls if c.startswith("release create")]


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize(
    "assets", [(), ASSETS[:1], ASSETS[1:]], ids=["none", "no-sdist", "no-wheel"]
)
def test_a_build_without_the_wheel_and_the_sdist_publishes_nothing(
    tmp_path: Path, assets: tuple[str, ...]
) -> None:
    result, calls = run_publish(tmp_path, release_exists=False, assets=assets)
    assert result.returncode != 0
    assert "::error title=publish::" in result.stdout
    assert calls == []


# --- the portal -------------------------------------------------------------------------

PORTAL_BUILD = "portal-build"
PORTAL_DEPLOY = "portal-deploy"
BASE_CHECK = "Check the portal's base against the Pages address"
CONFIG = ROOT / ".beadloom" / "config.yml"
# The steps of the workflow `beadloom docs site --pages-workflow` writes (beadloom 9.0.0),
# in its order: an action by name, a one-line script by its text, the base check by name.
PORTAL_STEPS = [
    "actions/checkout",
    "actions/configure-pages",
    BASE_CHECK,
    "actions/setup-python",
    'python -m pip install "beadloom[languages]==9.0.0"',
    "beadloom reindex",
    "beadloom docs site --out site",
    "actions/setup-node",
    "npm ci",
    "npm run docs:build",
    "actions/upload-pages-artifact",
]


def portal_job(name: str) -> Mapping:
    found = release()["jobs"][name]
    assert isinstance(found, dict)
    return found


def signature(step: Mapping) -> str:
    if "uses" in step:
        return str(step["uses"]).split("@")[0]
    text = str(step["run"]).strip()
    return text if "\n" not in text else str(step["name"])


def site_config() -> Mapping:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    site = data["site"]
    assert isinstance(site, dict)
    return site


def test_the_portal_identity_is_declared_for_the_project_pages_address() -> None:
    site = site_config()
    assert site["title"] == "horizon-tracker"
    assert site["description"]
    assert site["base"] == "/horizon-tracker/"
    assert site["repo_url"] == "https://github.com/zoologov/horizon-tracker"


def test_the_portal_is_built_with_the_steps_the_generator_writes() -> None:
    assert [signature(s) for s in steps(release(), PORTAL_BUILD)] == PORTAL_STEPS


def test_the_portal_names_the_generator_its_steps_come_from() -> None:
    text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
    assert "beadloom 9.0.0" in text
    assert "docs site --pages-workflow" in text


def test_the_portal_is_built_from_the_released_commits_whole_history() -> None:
    # Each node's activity is measured on the history checked out.
    checkout = steps(release(), PORTAL_BUILD)[0]
    assert checkout["with"] == {
        "ref": VERIFIED % "sha",
        "fetch-depth": 0,
        "persist-credentials": False,
    }


def test_the_portal_is_built_for_the_base_the_config_declares() -> None:
    assert portal_job(PORTAL_BUILD)["env"]["PORTAL_BASE"] == site_config()["base"]
    base_check = step_named(release(), PORTAL_BUILD, BASE_CHECK)
    configure = steps(release(), PORTAL_BUILD)[1]
    assert base_check["env"] == {
        "PAGES_BASE_PATH": f"${{{{ steps.{configure['id']}.outputs.base_path }}}}"
    }


def run_base_check(served: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    step = step_named(release(), PORTAL_BUILD, BASE_CHECK)
    env = {
        "PATH": os.environ["PATH"],
        "PORTAL_BASE": portal_job(PORTAL_BUILD)["env"]["PORTAL_BASE"],
        "PAGES_BASE_PATH": served,
    }
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-eo", "pipefail", "-c", str(step["run"])],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize("served", ["/horizon-tracker", "/horizon-tracker/"])
def test_the_base_check_passes_when_pages_serves_the_declared_base(served: str) -> None:
    result = run_base_check(served)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="bash absent")
@pytest.mark.parametrize("served", ["", "/", "/other"])
def test_the_base_check_refuses_a_portal_built_for_another_address(served: str) -> None:
    # A portal built for one base and served under another loads none of its assets.
    result = run_base_check(served)
    assert result.returncode == 1
    assert "::error::" in result.stdout
    assert "site.base" in result.stdout


def test_the_portal_tools_are_the_ones_the_generator_names() -> None:
    by_action = {signature(s): s for s in steps(release(), PORTAL_BUILD) if "uses" in s}
    assert str(by_action["actions/setup-python"]["with"]["python-version"]) == "3.12"
    assert str(by_action["actions/setup-node"]["with"]["node-version"]) == "22"
    assert by_action["actions/upload-pages-artifact"]["with"] == {"path": "site/.vitepress/dist"}
    for step in steps(release(), PORTAL_BUILD):
        if str(step.get("run", "")).startswith("npm "):
            assert step["working-directory"] == "site", step["run"]


def test_the_portal_and_ci_install_one_beadloom() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    (ci_pin,) = set(re.findall(r"uv tool install beadloom==(\S+)", ci_text))
    portal = [s for s in PORTAL_STEPS if "pip install" in s]
    assert portal == [f'python -m pip install "beadloom[languages]=={ci_pin}"']


def test_the_portal_is_deployed_by_a_job_of_its_own_to_github_pages() -> None:
    deploy_job = portal_job(PORTAL_DEPLOY)
    assert deploy_job["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }
    assert deploy_job["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    (step,) = steps(release(), PORTAL_DEPLOY)
    assert str(step["uses"]).startswith("actions/deploy-pages@")
    assert step["id"] == "deployment"


@pytest.mark.parametrize("name", [PORTAL_BUILD, PORTAL_DEPLOY])
def test_the_pages_actions_run_on_node_24(name: str) -> None:
    # The Pages actions still ship Node 20 entry points (the generator's own note).
    assert portal_job(name)["env"]["FORCE_JAVASCRIPT_ACTIONS_TO_NODE24"] is True
