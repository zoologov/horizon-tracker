"""Unit tests for the run report value and the notification text rendered from it."""

import dataclasses
import unicodedata
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from horizon_tracker.domain.absence import Absence, AbsenceKind
from horizon_tracker.domain.calendar import VerdictSource
from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.report import (
    ABSENCE_REASONS,
    Outcome,
    Reason,
    RunReport,
    absence_reason,
    render,
)
from horizon_tracker.domain.schedule import RunKind

MOSCOW = ZoneInfo("Europe/Moscow")
MORNING = datetime(2026, 10, 20, 7, 56, 12, tzinfo=MOSCOW)
PASSWORD = "S3cr3t-Pa55w0rd!"

SUCCESS = RunReport(
    kind=RunKind.CHECKIN,
    outcome=Outcome.SUCCEEDED,
    at=MORNING,
    verdict_source=VerdictSource.CALENDAR,
)


VACATION = Absence(
    id=3, kind=AbsenceKind.VACATION, first_day=date(2026, 11, 3), last_day=date(2026, 11, 14)
)
_KIND_OF = {reason: kind for kind, reason in ABSENCE_REASONS.items()}


def _failure(reason: Reason, screenshot: Path | None = None) -> RunReport:
    return dataclasses.replace(
        SUCCESS, outcome=Outcome.FAILED, reason=reason, screenshot=screenshot
    )


def _absent(absence: Absence = VACATION, planned_at: time | None = time(7, 43)) -> RunReport:
    """The skip of a run on a day ``absence`` covers: the calendar was not asked."""
    return dataclasses.replace(
        SUCCESS,
        outcome=Outcome.SKIPPED,
        reason=absence_reason(absence.kind),
        absence=absence,
        verdict_source=None,
        planned_at=planned_at,
    )


def _for_reason(reason: Reason) -> RunReport:
    """A well-formed report ending for ``reason``: an absence skip or a plain failure."""
    if reason in _KIND_OF:
        return _absent(dataclasses.replace(VACATION, kind=_KIND_OF[reason]))
    return _failure(reason)


# --- the text -----------------------------------------------------------------

RU = Language.RU
EN = Language.EN


@pytest.mark.parametrize(
    ("language", "kind", "outcome", "reason", "headline"),
    [
        (RU, RunKind.CHECKIN, Outcome.SUCCEEDED, None, "Вход выполнен"),
        (RU, RunKind.CHECKOUT, Outcome.SUCCEEDED, None, "Выход выполнен"),
        (RU, RunKind.CHECKIN, Outcome.FAILED, Reason.LOGIN_REJECTED, "Вход не удался"),
        (RU, RunKind.CHECKOUT, Outcome.SKIPPED, Reason.ALREADY_LOGGED_OFF, "Выход пропущен"),
        (EN, RunKind.CHECKIN, Outcome.SUCCEEDED, None, "Check-in succeeded"),
        (EN, RunKind.CHECKOUT, Outcome.SUCCEEDED, None, "Check-out succeeded"),
        (EN, RunKind.CHECKIN, Outcome.FAILED, Reason.LOGIN_REJECTED, "Check-in failed"),
        (EN, RunKind.CHECKOUT, Outcome.SKIPPED, Reason.ALREADY_LOGGED_OFF, "Check-out skipped"),
    ],
)
def test_render_opens_with_the_kind_and_the_outcome(
    language: Language, kind: RunKind, outcome: Outcome, reason: Reason | None, headline: str
) -> None:
    report = dataclasses.replace(SUCCESS, kind=kind, outcome=outcome, reason=reason)

    assert render(report, language).splitlines()[0] == headline


@pytest.mark.parametrize(
    ("language", "line"),
    [(RU, "Время: 20.10.2026 07:56:12 MSK"), (EN, "Time: 20.10.2026 07:56:12 MSK")],
)
def test_render_states_the_time_in_the_reports_own_time_zone(language: Language, line: str) -> None:
    assert line in render(SUCCESS, language).splitlines()


@pytest.mark.parametrize(
    ("language", "source", "line"),
    [
        (RU, VerdictSource.CALENDAR, "Производственный календарь: isdayoff.ru"),
        (
            RU,
            VerdictSource.WEEKDAY_FALLBACK,
            "Производственный календарь: недоступен, решило правило Пн–Пт",
        ),
        (RU, None, "Производственный календарь: не спрашивали, ручной прогон --force"),
        (EN, VerdictSource.CALENDAR, "Production calendar: isdayoff.ru"),
        (
            EN,
            VerdictSource.WEEKDAY_FALLBACK,
            "Production calendar: unavailable, the Mon–Fri rule decided",
        ),
        (EN, None, "Production calendar: not asked, manual run --force"),
    ],
)
def test_render_names_which_rule_decided_the_working_day(
    language: Language, source: VerdictSource | None, line: str
) -> None:
    report = dataclasses.replace(SUCCESS, verdict_source=source)

    assert line in render(report, language).splitlines()


@pytest.mark.parametrize(
    ("language", "line"),
    [
        (RU, "Время: 20.10.2026 07:56:12 MSK, назначено на 07:43"),
        (EN, "Time: 20.10.2026 07:56:12 MSK, planned for 07:43"),
    ],
)
def test_render_puts_the_planned_moment_beside_the_actual_time(
    language: Language, line: str
) -> None:
    report = dataclasses.replace(SUCCESS, planned_at=time(7, 43))

    assert line in render(report, language).splitlines()


@pytest.mark.parametrize(("language", "word"), [(RU, "назначено"), (EN, "planned")])
def test_render_names_no_planned_moment_when_the_run_had_none(
    language: Language, word: str
) -> None:
    # A --force run has no drawn moment: the time line stands alone.
    assert word not in render(SUCCESS, language)


def test_report_keeps_the_planned_moment() -> None:
    assert dataclasses.replace(SUCCESS, planned_at=time(16, 41)).planned_at == time(16, 41)


@pytest.mark.parametrize(("language", "prefix"), [(RU, "Причина:"), (EN, "Reason:")])
def test_a_success_carries_no_reason_line(language: Language, prefix: str) -> None:
    assert not any(line.startswith(prefix) for line in render(SUCCESS, language).splitlines())


@pytest.mark.parametrize(
    ("language", "line"), [(RU, "Причина: выходной"), (EN, "Reason: a day off")]
)
def test_a_holiday_skip_says_it_is_a_day_off(language: Language, line: str) -> None:
    report = dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.NON_WORKING_DAY)

    assert line in render(report, language).splitlines()


@pytest.mark.parametrize(
    ("language", "reason", "line"),
    [
        (RU, Reason.TOO_EARLY, "Причина: прогон начался до своего окна"),
        (RU, Reason.WINDOW_MISSED, "Причина: прогон начался после своего окна"),
        (EN, Reason.TOO_EARLY, "Reason: the run started before its window"),
        (EN, Reason.WINDOW_MISSED, "Reason: the run started after its window"),
    ],
    ids=["early-ru", "late-ru", "early-en", "late-en"],
)
def test_a_window_skip_says_on_which_side_of_the_window_the_run_started(
    language: Language, reason: Reason, line: str
) -> None:
    report = dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=reason)

    assert line in render(report, language).splitlines()


ABSENCE_REASON_SET = frozenset(ABSENCE_REASONS.values())

RUSSIAN_REASONS = {
    Reason.NON_WORKING_DAY: "выходной",
    Reason.TOO_EARLY: "прогон начался до своего окна",
    Reason.WINDOW_MISSED: "прогон начался после своего окна",
    Reason.ALREADY_LOGGED_OFF: "сессии на столе уже нет, выходить не из чего",
    Reason.PORTAL_UNREACHABLE: "портал Horizon недоступен",
    Reason.LOGIN_REJECTED: "портал отклонил вход",
    Reason.DESKTOP_NOT_FOUND: "рабочий стол не найден среди доступных",
    Reason.DESKTOP_DID_NOT_OPEN: "рабочий стол не открылся",
    Reason.LOGOFF_NOT_CONFIRMED: "выход из Windows не подтвердился",
    Reason.UNEXPECTED: "непредвиденная ошибка, подробности в журнале",
}


@pytest.mark.parametrize(
    "reason", [reason for reason in Reason if reason not in ABSENCE_REASON_SET]
)
def test_every_reason_reads_in_russian_as_it_did_before_the_catalogue(reason: Reason) -> None:
    assert f"Причина: {RUSSIAN_REASONS[reason]}" in render(_failure(reason), RU).splitlines()


@pytest.mark.parametrize(("language", "prefix"), [(RU, "Причина:"), (EN, "Reason:")])
@pytest.mark.parametrize("reason", list(Reason))
def test_every_reason_renders_its_own_non_empty_line(
    reason: Reason, language: Language, prefix: str
) -> None:
    text = render(_for_reason(reason), language)
    lines = [line for line in text.splitlines() if line.startswith(prefix)]

    assert len(lines) == 1
    assert lines[0].removeprefix(prefix).strip()


@pytest.mark.parametrize("language", list(Language))
def test_every_reason_reads_differently(language: Language) -> None:
    texts = {render(_for_reason(reason), language) for reason in Reason}

    assert len(texts) == len(Reason)


def _every_report() -> list[RunReport]:
    """One report per kind, outcome, calendar source and planned moment, each reason once."""
    reports = []
    for kind in RunKind:
        for source in [*VerdictSource, None]:
            for planned in (None, time(7, 43)):
                base = dataclasses.replace(
                    SUCCESS, kind=kind, verdict_source=source, planned_at=planned
                )
                reports.append(base)
                reports.extend(
                    dataclasses.replace(base, outcome=outcome, reason=reason)
                    for outcome in (Outcome.FAILED, Outcome.SKIPPED)
                    for reason in Reason
                    if reason not in ABSENCE_REASON_SET
                )
        for kind_of_absence in AbsenceKind:
            for planned in (None, time(7, 43)):
                absence = dataclasses.replace(VACATION, kind=kind_of_absence)
                reports.append(dataclasses.replace(_absent(absence, planned), kind=kind))
    return reports


def _has_cyrillic(text: str) -> bool:
    return any(unicodedata.name(letter, "").startswith("CYRILLIC") for letter in text)


def test_an_english_notification_holds_no_russian_word() -> None:
    # Any branch of render that skipped the catalogue would leave a Russian literal here.
    assert not [report for report in _every_report() if _has_cyrillic(render(report, EN))]


def test_a_russian_and_an_english_notification_differ_on_every_line() -> None:
    for report in _every_report():
        russian, english = render(report, RU).splitlines(), render(report, EN).splitlines()

        assert len(russian) == len(english)
        assert all(ru != en for ru, en in zip(russian, english, strict=True))


# --- the value: well-formed by construction -------------------------------------


def test_report_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        SUCCESS.outcome = Outcome.FAILED  # type: ignore[misc]  # asserting the frozen dataclass rejects it


def test_report_keeps_the_screenshot_for_the_notifier() -> None:
    shot = Path("/var/lib/horizon/shots/checkin.png")

    assert _failure(Reason.DESKTOP_DID_NOT_OPEN, shot).screenshot == shot


def test_report_refuses_a_time_without_a_time_zone() -> None:
    with pytest.raises(ValueError, match=r"^RunReport\.at must carry a time zone$"):
        dataclasses.replace(SUCCESS, at=MORNING.replace(tzinfo=None))


REASON_RULE = r"^RunReport\.reason is required for a failure or a skip, and only then$"


def test_a_success_refuses_a_reason() -> None:
    with pytest.raises(ValueError, match=REASON_RULE):
        dataclasses.replace(SUCCESS, reason=Reason.UNEXPECTED)


@pytest.mark.parametrize("outcome", [Outcome.FAILED, Outcome.SKIPPED])
def test_a_failure_or_a_skip_requires_a_reason(outcome: Outcome) -> None:
    with pytest.raises(ValueError, match=REASON_RULE):
        dataclasses.replace(SUCCESS, outcome=outcome)


@pytest.mark.parametrize(
    "field",
    ["kind", "outcome", "at", "verdict_source", "reason", "screenshot", "planned_at", "absence"],
)
def test_a_value_of_the_wrong_type_is_refused_naming_the_field_and_the_type(field: str) -> None:
    # The refusal goes to the journal: it names the field and the type, never the value.
    expected = rf"^RunReport\.{field} has the wrong type: str$"

    with pytest.raises(TypeError, match=expected):
        # Deliberately ill-typed: the runtime guard of the report is what is under test.
        dataclasses.replace(_failure(Reason.UNEXPECTED), **{field: "free text"})  # type: ignore[arg-type]


def test_report_refuses_free_text_as_a_reason() -> None:
    with pytest.raises(TypeError, match="reason"):
        _failure("login failed for user with password hunter2")  # type: ignore[arg-type]  # the runtime guard under test


# --- the password never reaches the notification ----------------------------------


def _with_field(field: str, value: object) -> RunReport | None:
    """The base failure report with one field replaced, or None when the report refuses it.

    A refusal must not echo the refused value either: its message goes to the journal.
    """
    try:
        # Deliberately ill-typed values: the runtime guard of the report is what is under test.
        return dataclasses.replace(_failure(Reason.LOGIN_REJECTED), **{field: value})  # type: ignore[arg-type]
    except (TypeError, ValueError) as refusal:
        assert PASSWORD not in str(refusal)
        return None


@pytest.mark.parametrize("field", [field.name for field in dataclasses.fields(RunReport)])
@pytest.mark.parametrize(
    "carrier",
    [PASSWORD, Path(PASSWORD), Path("/var/lib/horizon") / f"{PASSWORD}.png"],
    ids=["str", "bare-path", "nested-path"],
)
def test_a_password_passed_through_any_field_never_reaches_the_text(
    field: str, carrier: object
) -> None:
    report = _with_field(field, carrier)

    if report is not None:
        assert all(PASSWORD not in render(report, language) for language in Language)


def test_the_password_test_covers_the_planned_moment() -> None:
    # The any-field test reads the fields at collection; this pins that it reaches the new one.
    assert "planned_at" in {field.name for field in dataclasses.fields(RunReport)}


def test_the_screenshot_travels_beside_the_text_not_inside_it() -> None:
    report = _failure(Reason.DESKTOP_DID_NOT_OPEN, Path(f"/var/lib/horizon/{PASSWORD}.png"))

    assert report.screenshot is not None
    assert all(PASSWORD not in render(report, language) for language in Language)


# --- HT-012: a day-level skip, an absence, the calendar line --------------------


def _lines(*lines: str) -> str:
    """A notification text from its lines; a literal "\\n" would glue Latin to Cyrillic."""
    return "\n".join(lines)


RUSSIAN_SKIP_OF_A_HOLIDAY = _lines(
    "Вход пропущен", "Производственный календарь: isdayoff.ru", "Причина: выходной"
)
ENGLISH_SKIP_OF_A_HOLIDAY = _lines(
    "Check-in skipped", "Production calendar: isdayoff.ru", "Reason: a day off"
)


@pytest.mark.parametrize(
    ("language", "expected"),
    [(RU, RUSSIAN_SKIP_OF_A_HOLIDAY), (EN, ENGLISH_SKIP_OF_A_HOLIDAY)],
)
@pytest.mark.parametrize("planned_at", [None, time(7, 43)], ids=["unplanned", "planned"])
def test_a_skipped_non_working_day_is_reported_without_a_time_line(
    language: Language, expected: str, planned_at: time | None
) -> None:
    report = dataclasses.replace(
        SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.NON_WORKING_DAY, planned_at=planned_at
    )

    assert render(report, language) == expected


def test_a_failure_for_a_non_working_day_still_states_its_time() -> None:
    # Only a skip is day-level: the outcome and the reason are both part of the rule.
    report = dataclasses.replace(_failure(Reason.NON_WORKING_DAY), planned_at=time(7, 43))

    assert "Time: 20.10.2026 07:56:12 MSK, planned for 07:43" in render(report, EN).splitlines()


@pytest.mark.parametrize(
    ("language", "kind", "expected"),
    [
        (RU, AbsenceKind.VACATION, _lines("Вход пропущен", "Причина: отпуск (03.11–14.11)")),
        (RU, AbsenceKind.SICK_LEAVE, _lines("Вход пропущен", "Причина: больничный (03.11–14.11)")),
        (RU, AbsenceKind.DAY_OFF, _lines("Вход пропущен", "Причина: отгул (03.11–14.11)")),
        (EN, AbsenceKind.VACATION, _lines("Check-in skipped", "Reason: vacation (03.11–14.11)")),
        (
            EN,
            AbsenceKind.SICK_LEAVE,
            _lines("Check-in skipped", "Reason: sick leave (03.11–14.11)"),
        ),
        (
            EN,
            AbsenceKind.DAY_OFF,
            _lines("Check-in skipped", "Reason: day off taken (03.11–14.11)"),
        ),
    ],
)
def test_an_absence_skip_names_the_kind_and_its_span_and_nothing_else(
    language: Language, kind: AbsenceKind, expected: str
) -> None:
    # No time line (a day-level skip) and no calendar line (the calendar was not asked).
    report = _absent(dataclasses.replace(VACATION, kind=kind))

    assert render(report, language) == expected


@pytest.mark.parametrize(
    ("language", "line"), [(RU, "Причина: отгул (05.11)"), (EN, "Reason: day off taken (05.11)")]
)
def test_a_one_day_absence_names_its_one_day(language: Language, line: str) -> None:
    one_day = Absence(
        id=1, kind=AbsenceKind.DAY_OFF, first_day=date(2026, 11, 5), last_day=date(2026, 11, 5)
    )

    assert render(_absent(one_day), language).splitlines()[-1] == line


def test_an_absence_across_the_new_year_names_both_days_without_a_year() -> None:
    winter = Absence(
        id=2, kind=AbsenceKind.VACATION, first_day=date(2026, 12, 28), last_day=date(2027, 1, 9)
    )

    assert render(_absent(winter), EN).splitlines()[-1] == "Reason: vacation (28.12–09.01)"


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (
            SUCCESS,
            "Check-in succeeded\nTime: 20.10.2026 07:56:12 MSK\nProduction calendar: isdayoff.ru",
        ),
        (
            dataclasses.replace(SUCCESS, planned_at=time(7, 43)),
            "Check-in succeeded\nTime: 20.10.2026 07:56:12 MSK, planned for 07:43\n"
            "Production calendar: isdayoff.ru",
        ),
        (
            _failure(Reason.DESKTOP_DID_NOT_OPEN),
            "Check-in failed\nTime: 20.10.2026 07:56:12 MSK\nProduction calendar: isdayoff.ru\n"
            "Reason: the desktop did not open",
        ),
        (
            dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.TOO_EARLY),
            "Check-in skipped\nTime: 20.10.2026 07:56:12 MSK\nProduction calendar: isdayoff.ru\n"
            "Reason: the run started before its window",
        ),
        (
            dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.WINDOW_MISSED),
            "Check-in skipped\nTime: 20.10.2026 07:56:12 MSK\nProduction calendar: isdayoff.ru\n"
            "Reason: the run started after its window",
        ),
    ],
    ids=["success", "success-planned", "failure", "too-early", "window-missed"],
)
def test_the_other_reports_keep_every_line_they_had(report: RunReport, expected: str) -> None:
    assert render(report, EN) == expected


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (SUCCESS, False),
        (_failure(Reason.NON_WORKING_DAY), False),
        (dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.TOO_EARLY), False),
        (dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.WINDOW_MISSED), False),
        (
            dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.ALREADY_LOGGED_OFF),
            False,
        ),
        (
            dataclasses.replace(SUCCESS, outcome=Outcome.SKIPPED, reason=Reason.NON_WORKING_DAY),
            True,
        ),
        *[(_for_reason(reason), True) for reason in ABSENCE_REASONS.values()],
    ],
)
def test_a_day_level_skip_is_a_skip_for_the_day_itself(report: RunReport, expected: bool) -> None:
    assert report.is_day_level_skip is expected


def test_every_kind_of_absence_has_its_own_reason() -> None:
    assert ABSENCE_REASONS == {
        AbsenceKind.VACATION: Reason.ON_VACATION,
        AbsenceKind.SICK_LEAVE: Reason.ON_SICK_LEAVE,
        AbsenceKind.DAY_OFF: Reason.ON_DAY_OFF,
    }
    assert all(absence_reason(kind) is reason for kind, reason in ABSENCE_REASONS.items())


def test_the_absence_reasons_name_their_kind() -> None:
    assert [Reason.ON_VACATION.value, Reason.ON_SICK_LEAVE.value, Reason.ON_DAY_OFF.value] == [
        "on_vacation",
        "on_sick_leave",
        "on_day_off",
    ]


def test_an_absence_skip_keeps_its_absence() -> None:
    assert _absent().absence == VACATION


ABSENCE_RULE = r"^RunReport\.absence is required for an absence reason, and only then$"


def test_an_absence_reason_requires_the_absence() -> None:
    with pytest.raises(ValueError, match=ABSENCE_RULE):
        dataclasses.replace(_absent(), absence=None)


@pytest.mark.parametrize("reason", [Reason.NON_WORKING_DAY, Reason.UNEXPECTED])
def test_an_absence_is_refused_beside_another_reason(reason: Reason) -> None:
    with pytest.raises(ValueError, match=ABSENCE_RULE):
        dataclasses.replace(_absent(), reason=reason)


def test_a_success_refuses_an_absence() -> None:
    with pytest.raises(ValueError, match=ABSENCE_RULE):
        dataclasses.replace(SUCCESS, absence=VACATION)


def test_the_absence_reason_must_name_the_absences_kind() -> None:
    with pytest.raises(
        ValueError, match=r"^RunReport\.reason does not name the kind of its absence$"
    ):
        dataclasses.replace(_absent(), reason=Reason.ON_SICK_LEAVE)


def test_an_absence_ends_in_a_skip_only() -> None:
    with pytest.raises(ValueError, match=r"^RunReport\.outcome of an absence must be skipped$"):
        dataclasses.replace(_absent(), outcome=Outcome.FAILED)


@pytest.mark.parametrize("source", list(VerdictSource))
def test_an_absence_skip_asked_no_calendar(source: VerdictSource) -> None:
    expected = r"^RunReport\.verdict_source of an absence must be None: no calendar is asked$"
    with pytest.raises(ValueError, match=expected):
        dataclasses.replace(_absent(), verdict_source=source)
