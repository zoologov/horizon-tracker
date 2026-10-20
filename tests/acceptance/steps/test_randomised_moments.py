"""Randomised moments: each day draws its own pair, the runs agree on it and wait for it.

The scenarios read the drawn moments only where an owner could: the success message
("назначено на HH:MM" beside the time the run acted), the probe's and the dry run's
"schedule: today HH:MM / HH:MM" line, and the dry run's "would wait until". The wait is
read off the fake clock, which only moves when the service sleeps, and the Horizon fake
records the clock's time of every portal call. "Two separate runs" are two interpreter
processes started with different string-hash salts, so agreement cannot come from any
state the two share.
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from pytest_bdd import given, parsers, scenarios, then, when

from tests.acceptance.steps.conftest import COMMANDS, Scene, moment
from tests.support.repository_root import repository_root

scenarios("../features/randomised_moments.feature")

_MESSAGE_TIME = re.compile(
    r"^Время: (?P<day>\d\d\.\d\d\.\d{4}) (?P<acted>\d\d:\d\d:\d\d) MSK, "
    r"назначено на (?P<planned>\d\d:\d\d)$",
    re.MULTILINE,
)
_SCHEDULE = re.compile(r"^schedule: today (?P<check_in>\d\d:\d\d) / (?P<check_out>\d\d:\d\d)$")
_PROCESS_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Planned:
    """What one success message says: the day, when the run acted, what it was planned for."""

    day: date
    acted: time
    planned: time


@dataclass(frozen=True)
class DaySchedule:
    """One day's moments as the probe names them."""

    day: date
    check_in: time
    check_out: time

    @property
    def length(self) -> timedelta:
        return _on(self.day, self.check_out) - _on(self.day, self.check_in)


def _on(day: date, at: time) -> datetime:
    return datetime.combine(day, at)


def _hm(text: str) -> time:
    return time.fromisoformat(text)


def _days(first: str, last: str, *, weekdays_only: bool) -> list[date]:
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    assert start <= end, f"{first} is after {last}"
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    return [day for day in days if day.weekday() < 5] if weekdays_only else days


def _planned(scene: Scene) -> list[Planned]:
    """Every message's time line, in the order the messages reached the chat."""
    found: list[Planned] = []
    for message in scene.bot.messages:
        match = _MESSAGE_TIME.search(message.text)
        assert match is not None, f"no planned moment in the message:\n{message.text}"
        found.append(
            Planned(
                day=datetime.strptime(match["day"], "%d.%m.%Y").date(),
                acted=_hm(match["acted"]),
                planned=_hm(match["planned"]),
            )
        )
    return found


def _checkout_range_end(scene: Scene) -> time:
    configured = scene.env()["HT_CHECKOUT_RANGE"]
    assert configured is not None, "the scene names no check-out range"
    return _hm(configured.split("-")[1])


def _schedule_in(output: str) -> tuple[time, time]:
    for line in output.splitlines():
        match = _SCHEDULE.match(line)
        if match is not None:
            return _hm(match["check_in"]), _hm(match["check_out"])
    raise AssertionError(f"no schedule line in:\n{output}")


def _schedules(scene: Scene) -> list[DaySchedule]:
    """The schedule line of every probe the scenario ran, with the day the probe ran on."""
    schedules: list[DaySchedule] = []
    for world, result in zip(scene.worlds, scene.results, strict=True):
        assert result.exit_code == 0, result.output
        check_in, check_out = _schedule_in(result.stdout)
        schedules.append(DaySchedule(world.clock.now().date(), check_in, check_out))
    assert schedules, "no probe ran in this scenario"
    return schedules


# --- Given ----------------------------------------------------------------------------


@given(
    parsers.parse(
        "the check-in range is {checkin_range} and the check-out range is {checkout_range}"
    )
)
def ranges(scene: Scene, checkin_range: str, checkout_range: str) -> None:
    scene.env_overrides["HT_CHECKIN_RANGE"] = checkin_range
    scene.env_overrides["HT_CHECKOUT_RANGE"] = checkout_range


@given(parsers.parse("a working day lasts {length:d} minutes plus up to {extra:d} minutes"))
def day_length(scene: Scene, length: int, extra: int) -> None:
    scene.env_overrides["HT_SESSION_LENGTH_MINUTES"] = str(length)
    scene.env_overrides["HT_SESSION_EXTRA_MAX_MINUTES"] = str(extra)


@given(parsers.parse('the moments are drawn with the seed "{seed}"'))
def drawn_with(scene: Scene, seed: str) -> None:
    scene.env_overrides["HT_JITTER_SEED"] = seed


# --- When -----------------------------------------------------------------------------


@when(
    parsers.parse(
        "the {run} runs at {clock} on every weekday from {first_weekday} {first} "
        "to {last_weekday} {last}"
    )
)
def run_every_weekday(
    scene: Scene, run: str, clock: str, first_weekday: str, first: str, last_weekday: str, last: str
) -> None:
    moment(clock, first_weekday, first)  # the named weekdays must agree with their dates
    moment(clock, last_weekday, last)
    for day in _days(first, last, weekdays_only=True):
        scene.run([COMMANDS[run]], moment(clock, f"{day:%A}", day.isoformat()))


@when(
    parsers.parse(
        'the owner runs "horizon {args}" at {clock} on every day from {first_weekday} {first} '
        "to {last_weekday} {last}"
    )
)
def owner_runs_every_day(
    scene: Scene,
    args: str,
    clock: str,
    first_weekday: str,
    first: str,
    last_weekday: str,
    last: str,
) -> None:
    moment(clock, first_weekday, first)
    moment(clock, last_weekday, last)
    for day in _days(first, last, weekdays_only=False):
        scene.run(args.split(), moment(clock, f"{day:%A}", day.isoformat()))


@when(
    parsers.parse(
        'the owner runs "horizon {args}" at {clock} on {weekday} {day} in a process of its own'
    )
)
def owner_runs_in_a_process(scene: Scene, args: str, clock: str, weekday: str, day: str) -> None:
    """Run the command in a fresh interpreter whose string-hash salt differs from every other."""
    salt = str(len(scene.processes) + 1)
    env = {
        **os.environ,
        **{name: value for name, value in scene.env().items() if value is not None},
        "PYTHONHASHSEED": salt,
    }
    at = moment(clock, weekday, day).isoformat()
    scene.processes.append(
        subprocess.run(
            [sys.executable, "-m", "tests.support.cli_process", at, *args.split()],
            cwd=repository_root(),
            env=env,
            capture_output=True,
            text=True,
            timeout=_PROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    )


# --- Then -----------------------------------------------------------------------------


@then("every check-in succeeded at the moment it was planned for")
def every_checkin_on_its_moment(scene: Scene) -> None:
    planned = _planned(scene)
    assert len(planned) == len(scene.results), "every run sends exactly one message"
    assert all(result.exit_code == 0 for result in scene.results)
    assert all("Вход выполнен" in message.text for message in scene.bot.messages)
    late = [p for p in planned if p.acted != p.planned]
    assert late == [], f"runs that did not act at their planned moment: {late}"


@then(parsers.parse("every planned check-in lies between {start} and {end}"))
def every_checkin_in_range(scene: Scene, start: str, end: str) -> None:
    outside = [p for p in _planned(scene) if not _hm(start) <= p.planned <= _hm(end)]
    assert outside == [], f"check-ins outside {start}-{end}: {outside}"


@then(parsers.parse("the planned check-ins reach both {start} and {end}"))
def checkins_reach_both_ends(scene: Scene, start: str, end: str) -> None:
    drawn = {p.planned for p in _planned(scene)}
    assert {_hm(start), _hm(end)} <= drawn, f"drawn: {sorted(drawn)}"


@then(parsers.parse("the check-in of {day} was planned for {planned}"))
def checkin_planned_for(scene: Scene, day: str, planned: str) -> None:
    on_day = [p.planned for p in _planned(scene) if p.day == date.fromisoformat(day)]
    assert on_day == [_hm(planned)]


@then("the two days were planned for different check-in moments")
def two_days_differ(scene: Scene) -> None:
    first, second = _planned(scene)
    assert first.day != second.day
    assert first.planned != second.planned


@then(parsers.parse('the schedule of {weekday} {day} reads "{schedule}"'))
def schedule_of_day_reads(scene: Scene, weekday: str, day: str, schedule: str) -> None:
    on = moment("12:00", weekday, day).date()
    lines = [s for s in _schedules(scene) if s.day == on]
    assert [f"today {s.check_in:%H:%M} / {s.check_out:%H:%M}" for s in lines] == [schedule]


@then(
    parsers.parse("on every day the check-out is at least {minutes:d} minutes after the check-in")
)
def every_day_long_enough(scene: Scene, minutes: int) -> None:
    short = [s for s in _schedules(scene) if s.length < timedelta(minutes=minutes)]
    assert short == [], f"days shorter than {minutes} minutes: {short}"


@then(
    parsers.parse(
        "on every day with a check-in at {latest} or earlier the check-out is "
        "{least:d} to {most:d} minutes after it"
    )
)
def every_unclipped_day_in_bounds(scene: Scene, latest: str, least: int, most: int) -> None:
    unclipped = [s for s in _schedules(scene) if s.check_in <= _hm(latest)]
    assert unclipped, f"no day checked in at {latest} or earlier"
    wrong = [
        s for s in unclipped if not timedelta(minutes=least) <= s.length <= timedelta(minutes=most)
    ]
    assert wrong == [], f"days not {least}-{most} minutes long: {wrong}"


@then(parsers.parse("the minutes over {base:d} reach both {low:d} and {high:d}"))
def extras_reach_both_ends(scene: Scene, base: int, low: int, high: int) -> None:
    # A day that ends at the end of its range may have been clipped and hides its extra
    # minutes; every other day shows them as its length over the base.
    end = _checkout_range_end(scene)
    extras = {
        int(s.length / timedelta(minutes=1)) - base for s in _schedules(scene) if s.check_out < end
    }
    assert {low, high} <= extras, f"extra minutes seen: {sorted(extras)}"


@then(parsers.parse("every check-out lies between {start} and {end}"))
def every_checkout_in_range(scene: Scene, start: str, end: str) -> None:
    outside = [s for s in _schedules(scene) if not _hm(start) <= s.check_out <= _hm(end)]
    assert outside == [], f"check-outs outside {start}-{end}: {outside}"


@then(parsers.parse('both processes exit with {code:d} and read "{line}"'))
def both_processes_read(scene: Scene, code: int, line: str) -> None:
    assert len(scene.processes) == 2, f"expected two processes, ran {len(scene.processes)}"
    for process in scene.processes:
        assert process.returncode == code, process.stderr
        assert line in process.stdout.splitlines(), process.stdout


@then(parsers.parse('the {run} process reads "{line}"'))
def process_reads(scene: Scene, run: str, line: str) -> None:
    command = COMMANDS[run]
    ran = [p for p in scene.processes if command in p.args]
    assert len(ran) == 1, f"expected one {command} process, ran {len(ran)}"
    assert line in ran[0].stdout.splitlines(), ran[0].stdout


@then(parsers.parse("the run slept {seconds:d} seconds before anything else"))
def slept_first(scene: Scene, seconds: int) -> None:
    clock, client = scene.ran.clock, scene.ran.client
    assert clock.sleeps[:1] == [seconds], f"sleeps: {clock.sleeps}"
    assert client.called_at, "the portal was never contacted"
    assert client.called_at[0] == scene.starts[-1] + timedelta(seconds=seconds), client.called_at


@then(parsers.parse("the portal was first contacted at {clock}"))
def first_contact_at(scene: Scene, clock: str) -> None:
    called_at = scene.ran.client.called_at
    assert called_at, "the portal was never contacted"
    assert called_at[0].time() == time.fromisoformat(clock), called_at


@then("the run never slept")
def never_slept(scene: Scene) -> None:
    assert scene.ran.clock.sleeps == []
