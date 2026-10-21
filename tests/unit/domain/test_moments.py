"""Tests for the daily draw of the check-in and check-out moments and the window built from one."""

import dataclasses
from collections.abc import Callable
from datetime import date, datetime, time, timedelta

import pytest

from horizon_tracker.domain.messages import Language
from horizon_tracker.domain.schedule import (
    DailyMoments,
    ScheduleError,
    TimeRange,
    Window,
    draw_moments,
    window_from,
)

SEED = b"horizon-test-seed"
CHECKIN_RANGE = TimeRange(start=time(7, 30), end=time(8, 10))
CHECKOUT_RANGE = TimeRange(start=time(16, 30), end=time(17, 10))
SESSION = timedelta(hours=9)
EXTRA_MAX = timedelta(minutes=10)
FIRST_DAY = date(2026, 1, 1)
THREE_YEARS = [FIRST_DAY + timedelta(days=offset) for offset in range(3 * 365)]


def draw(
    day: date,
    seed: bytes = SEED,
    session_length: timedelta = SESSION,
    extra_max: timedelta = EXTRA_MAX,
    checkin_range: TimeRange = CHECKIN_RANGE,
    checkout_range: TimeRange = CHECKOUT_RANGE,
) -> DailyMoments:
    return draw_moments(
        day=day,
        seed=seed,
        checkin_range=checkin_range,
        session_length=session_length,
        extra_max=extra_max,
        checkout_range=checkout_range,
    )


def length(moments: DailyMoments) -> timedelta:
    return datetime.combine(FIRST_DAY, moments.check_out) - datetime.combine(
        FIRST_DAY, moments.check_in
    )


# --- TimeRange and DailyMoments ----------------------------------------------------


def test_time_range_rejects_an_end_before_its_start() -> None:
    with pytest.raises(ValueError, match=r"^range start 08:10:00 must be before its end 07:30:00$"):
        TimeRange(start=time(8, 10), end=time(7, 30))


def test_time_range_rejects_an_empty_span() -> None:
    with pytest.raises(ValueError, match="must be before its end"):
        TimeRange(start=time(7, 30), end=time(7, 30))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (time(7, 30, 1), time(8, 10)),
        (time(7, 30), time(8, 10, 0, 1)),
    ],
    ids=["start-seconds", "end-microseconds"],
)
def test_time_range_is_drawn_in_whole_minutes_and_refuses_a_finer_end(
    start: time, end: time
) -> None:
    with pytest.raises(ValueError, match=r"^range ends must be whole minutes"):
        TimeRange(start=start, end=end)


def test_ranges_and_moments_are_immutable() -> None:
    moments = draw(FIRST_DAY)

    with pytest.raises(dataclasses.FrozenInstanceError):
        CHECKIN_RANGE.start = time(7, 0)  # type: ignore[misc]  # asserting the frozen dataclass rejects it
    with pytest.raises(dataclasses.FrozenInstanceError):
        moments.check_in = time(7, 0)  # type: ignore[misc]  # asserting the frozen dataclass rejects it


# --- the draw: fixed answers -------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "check_in", "check_out"),
    [
        (date(2026, 10, 21), time(7, 41), time(16, 43)),
        (date(2026, 12, 31), time(8, 0), time(17, 5)),
    ],
)
def test_the_draw_is_a_fixed_function_of_the_day_and_the_seed(
    day: date, check_in: time, check_out: time
) -> None:
    # Known answers of hmac-sha256(seed, isoformat(day)): they hold across runs, processes
    # and releases, which is what lets the morning and the evening runs agree.
    assert draw(day) == DailyMoments(check_in=check_in, check_out=check_out)


def test_the_same_day_draws_the_same_pair_twice() -> None:
    assert draw(date(2026, 10, 21)) == draw(date(2026, 10, 21))


def test_thirty_consecutive_days_draw_at_least_two_check_in_minutes() -> None:
    minutes = {draw(FIRST_DAY + timedelta(days=offset)).check_in for offset in range(30)}

    assert len(minutes) >= 2


def test_another_seed_draws_another_sequence() -> None:
    days = THREE_YEARS[:30]

    assert [draw(day) for day in days] != [draw(day, seed=b"another-seed") for day in days]


def test_an_empty_seed_is_refused() -> None:
    with pytest.raises(ValueError, match=r"^the draw needs a non-empty seed$"):
        draw(FIRST_DAY, seed=b"")


# --- the draw: the ends of the ranges ------------------------------------------------


def test_the_first_minute_of_the_check_in_range_can_be_drawn() -> None:
    # 2026-12-09 draws offset 0 and extra 0: the earliest pair there is.
    assert draw(date(2026, 12, 9)) == DailyMoments(check_in=time(7, 30), check_out=time(16, 30))


def test_the_last_minute_of_the_check_in_range_can_be_drawn() -> None:
    # 2026-02-04 draws offset 40: 08:10 + 9 h is the end of the check-out range already.
    assert draw(date(2026, 2, 4)) == DailyMoments(check_in=time(8, 10), check_out=time(17, 10))


def test_a_check_out_past_the_range_is_clipped_to_its_end() -> None:
    # 2026-01-01 draws 08:08 and extra 4: 08:08 + 9 h + 4 min = 17:12, clipped to 17:10.
    assert draw(FIRST_DAY) == DailyMoments(check_in=time(8, 8), check_out=time(17, 10))


def test_a_long_session_is_clipped_to_the_end_of_the_check_out_range() -> None:
    moments = draw(date(2026, 10, 21), session_length=timedelta(hours=10))

    assert moments.check_out == time(17, 10)


def test_a_check_out_before_the_range_is_lifted_to_its_start() -> None:
    moments = draw(date(2026, 10, 21), session_length=timedelta(hours=1))

    assert moments.check_out == time(16, 30)


def test_over_three_years_every_check_in_falls_inside_its_range_and_both_ends_are_reached() -> None:
    check_ins = [draw(day).check_in for day in THREE_YEARS]

    assert all(time(7, 30) <= moment <= time(8, 10) for moment in check_ins)
    assert min(check_ins) == time(7, 30)
    assert max(check_ins) == time(8, 10)


def test_over_three_years_every_check_out_falls_inside_its_range_and_both_ends_are_reached() -> (
    None
):
    check_outs = [draw(day).check_out for day in THREE_YEARS]

    assert all(time(16, 30) <= moment <= time(17, 10) for moment in check_outs)
    assert min(check_outs) == time(16, 30)
    assert max(check_outs) == time(17, 10)


def test_over_three_years_the_extra_minutes_span_zero_to_their_maximum() -> None:
    # Only days whose session plus extra fits the range show the extra unclipped.
    extras = {
        length(moments) - SESSION
        for moments in (draw(day) for day in THREE_YEARS)
        if moments.check_out < time(17, 10)
    }

    assert extras == {timedelta(minutes=minute) for minute in range(11)}


def test_the_day_is_never_shorter_than_the_session_when_it_fits_the_range() -> None:
    for moments in (draw(day) for day in THREE_YEARS):
        fits = datetime.combine(FIRST_DAY, moments.check_in) + SESSION <= datetime.combine(
            FIRST_DAY, time(17, 10)
        )
        if fits:
            assert length(moments) >= SESSION, moments
        else:
            assert moments.check_out == time(17, 10), moments


def test_a_session_that_does_not_fit_ends_at_the_end_of_the_range() -> None:
    # 08:10 + 9 h 05 min = 17:15 does not fit 17:10: the day ends at the range end.
    moments = draw(date(2026, 2, 4), session_length=timedelta(hours=9, minutes=5))

    assert moments == DailyMoments(check_in=time(8, 10), check_out=time(17, 10))


def test_every_moment_is_a_whole_minute() -> None:
    for moments in (draw(day) for day in THREE_YEARS[:60]):
        assert moments.check_in.second == moments.check_in.microsecond == 0
        assert moments.check_out.second == moments.check_out.microsecond == 0


def test_a_zero_extra_draws_exactly_the_session() -> None:
    moments = draw(date(2026, 10, 21), extra_max=timedelta(0))

    assert moments == DailyMoments(check_in=time(7, 41), check_out=time(16, 41))


def test_a_one_minute_check_in_range_draws_both_of_its_minutes() -> None:
    narrow = TimeRange(start=time(7, 30), end=time(7, 31))

    check_ins = {draw(day, checkin_range=narrow).check_in for day in THREE_YEARS[:30]}

    assert check_ins == {time(7, 30), time(7, 31)}


# --- the draw: refused parameters ----------------------------------------------------


@pytest.mark.parametrize(
    ("session_length", "extra_max", "message"),
    [
        (timedelta(0), EXTRA_MAX, r"^session_length must be positive, got 0:00:00$"),
        (timedelta(minutes=-1), EXTRA_MAX, r"^session_length must be positive"),
        (SESSION, timedelta(minutes=-1), r"^extra_max must not be negative, got -1 day"),
        (timedelta(hours=9, seconds=30), EXTRA_MAX, r"^session_length must be whole minutes"),
        (SESSION, timedelta(minutes=10, seconds=1), r"^extra_max must be whole minutes"),
    ],
    ids=["zero-session", "negative-session", "negative-extra", "session-seconds", "extra-seconds"],
)
def test_the_draw_refuses_a_duration_it_cannot_honour(
    session_length: timedelta, extra_max: timedelta, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        draw(FIRST_DAY, session_length=session_length, extra_max=extra_max)


def test_the_draw_refuses_a_check_out_range_that_does_not_follow_the_check_in_range() -> None:
    overlapping = TimeRange(start=time(8, 10), end=time(9, 0))

    with pytest.raises(ValueError, match=r"^the check-out range must start after the check-in"):
        draw(FIRST_DAY, checkout_range=overlapping)


def test_a_check_out_range_starting_a_minute_after_the_check_in_range_is_accepted() -> None:
    adjacent = TimeRange(start=time(8, 11), end=time(9, 0))

    assert draw(FIRST_DAY, checkout_range=adjacent).check_out >= time(8, 11)


# --- window_from ---------------------------------------------------------------------


def test_window_from_opens_at_the_moment_and_closes_after_the_grace() -> None:
    assert window_from(time(7, 43), timedelta(minutes=5)) == Window(
        start=time(7, 43), end=time(7, 48)
    )


def test_window_from_carries_a_grace_across_the_hour() -> None:
    assert window_from(time(16, 58), timedelta(minutes=5)) == Window(
        start=time(16, 58), end=time(17, 3)
    )


@pytest.mark.parametrize("grace", [timedelta(0), timedelta(minutes=-5)], ids=["zero", "negative"])
def test_window_from_refuses_a_grace_that_is_not_positive(grace: timedelta) -> None:
    with pytest.raises(ValueError, match=r"^grace must be positive, got "):
        window_from(time(7, 43), grace)


def test_window_from_refuses_a_window_that_would_cross_midnight() -> None:
    with pytest.raises(ValueError, match=r"^a window from 23:58:00 with grace 0:05:00 crosses"):
        window_from(time(23, 58), timedelta(minutes=5))


def test_window_from_accepts_a_window_ending_on_the_last_microsecond_of_the_day() -> None:
    window = window_from(time(23, 55), timedelta(minutes=4, seconds=59, microseconds=999999))

    assert window.end == time(23, 59, 59, 999999)


# --- a refusal a setting can reach reads in any language -------------------------------

READABLE_REFUSALS = {
    "range-order": (
        lambda: TimeRange(start=time(8, 10), end=time(7, 30)),
        "range start 08:10:00 must be before its end 07:30:00",
        "начало диапазона 08:10:00 должно быть раньше конца 07:30:00",
    ),
    "check-out-order": (
        lambda: draw(FIRST_DAY, checkout_range=TimeRange(start=time(8, 0), end=time(9, 0))),
        "the check-out range must start after the check-in range ends: "
        "08:00:00 is not after 08:10:00",
        "диапазон выхода должен начинаться после конца диапазона входа: 08:00:00 не позже 08:10:00",
    ),
    "session": (
        lambda: draw(FIRST_DAY, session_length=timedelta(0)),
        "session_length must be positive, got 0:00:00",
        "длина сессии должна быть положительной, получено 0:00:00",
    ),
    "grace": (
        lambda: window_from(time(7, 43), timedelta(0)),
        "grace must be positive, got 0:00:00",
        "запас окна должен быть положительным, получено 0:00:00",
    ),
    "midnight": (
        lambda: window_from(time(23, 58), timedelta(minutes=5)),
        "a window from 23:58:00 with grace 0:05:00 crosses midnight",
        "окно от 23:58:00 при запасе 0:05:00 переходит через полночь",
    ),
}


@pytest.mark.parametrize(
    ("refused", "english", "russian"), READABLE_REFUSALS.values(), ids=READABLE_REFUSALS.keys()
)
def test_a_refusal_a_setting_can_reach_carries_its_reason_in_every_language(
    refused: Callable[[], object], english: str, russian: str
) -> None:
    with pytest.raises(ScheduleError) as caught:
        refused()

    assert str(caught.value) == english
    assert caught.value.reason.in_language(Language.EN) == english
    assert caught.value.reason.in_language(Language.RU) == russian


def test_a_schedule_refusal_is_a_value_error() -> None:
    # Callers that refuse any bad value keep catching ValueError.
    assert issubclass(ScheduleError, ValueError)
