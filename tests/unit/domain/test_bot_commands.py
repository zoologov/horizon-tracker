"""Unit tests for the bot's text command parser: commands, kinds, dates and refusals."""

import dataclasses
import random
from datetime import date

import pytest

from horizon_tracker.domain.absence import AbsenceKind
from horizon_tracker.domain.bot_commands import (
    KIND_WORDS,
    Add,
    CommandError,
    Delete,
    Edit,
    Help,
    List,
    parse,
)
from horizon_tracker.domain.messages import MESSAGES, Language, Message

TODAY = date(2026, 10, 24)  # a Saturday; any day far from the New Year

VACATION = AbsenceKind.VACATION
SICK_LEAVE = AbsenceKind.SICK_LEAVE
DAY_OFF = AbsenceKind.DAY_OFF


def _refusal(text: str, today: date = TODAY) -> Message:
    parsed = parse(text, today)
    assert isinstance(parsed, CommandError), parsed
    return parsed.problem


# --- the commands without arguments -------------------------------------------


def test_list_is_the_list_command() -> None:
    assert parse("/list", TODAY) == List()


@pytest.mark.parametrize("text", ["/help", "/start"])
def test_help_and_start_are_the_help_command(text: str) -> None:
    assert parse(text, TODAY) == Help()


@pytest.mark.parametrize("text", ["/list now", "/help me", "/start payload-from-a-link"])
def test_a_command_without_arguments_ignores_the_words_after_it(text: str) -> None:
    # Telegram's /start may carry a deep-link payload; nothing after these commands is read.
    assert isinstance(parse(text, TODAY), List | Help)


@pytest.mark.parametrize("text", ["/LIST", "/List", "  /list  ", "\n/list\n"])
def test_the_command_word_ignores_case_and_surrounding_space(text: str) -> None:
    assert parse(text, TODAY) == List()


def test_a_command_addressed_to_the_bot_by_name_is_the_same_command() -> None:
    # Telegram appends @<bot name> to a command picked from the menu in some clients.
    assert parse("/list@horizon_tracker_bot", TODAY) == List()


# --- /add ---------------------------------------------------------------------


def test_add_with_a_range_of_two_yearless_dates() -> None:
    assert parse("/add vacation 03.11-14.11", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


def test_add_with_the_prd_example_in_russian() -> None:
    assert parse("/add отпуск 03.11-14.11", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


def test_add_with_two_iso_dates_separated_by_a_space() -> None:
    assert parse("/add vacation 2026-11-03 2026-11-14", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


def test_add_with_two_iso_dates_joined_by_a_dash() -> None:
    assert parse("/add vacation 2026-11-03-2026-11-14", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


def test_add_with_two_full_dotted_dates() -> None:
    assert parse("/add sick 03.11.2026-14.11.2026", TODAY) == Add(
        SICK_LEAVE, date(2026, 11, 3), date(2026, 11, 14)
    )


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_a_range_may_be_joined_by_a_hyphen_an_en_dash_or_an_em_dash(dash: str) -> None:
    # A phone keyboard turns "--" into a dash; the owner should not have to notice.
    assert parse(f"/add vacation 03.11{dash}14.11", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_a_range_may_have_its_dash_standing_apart(dash: str) -> None:
    assert parse(f"/add vacation 03.11 {dash} 14.11", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


def test_a_single_date_is_a_one_day_absence() -> None:
    assert parse("/add dayoff 05.11", TODAY) == Add(DAY_OFF, date(2026, 11, 5), date(2026, 11, 5))


def test_a_range_of_one_day_is_a_one_day_absence() -> None:
    assert parse("/add dayoff 05.11-05.11", TODAY) == Add(
        DAY_OFF, date(2026, 11, 5), date(2026, 11, 5)
    )


def test_single_digit_days_and_months_are_read() -> None:
    assert parse("/add dayoff 5.1.2027", TODAY) == Add(DAY_OFF, date(2027, 1, 5), date(2027, 1, 5))


def test_an_iso_date_with_single_digit_month_and_day_is_read() -> None:
    assert parse("/add dayoff 2027-1-5", TODAY) == Add(DAY_OFF, date(2027, 1, 5), date(2027, 1, 5))


def test_add_reads_extra_spaces_between_its_words() -> None:
    assert parse("/add   vacation    03.11   14.11", TODAY) == Add(
        VACATION, date(2026, 11, 3), date(2026, 11, 14)
    )


# --- the kinds ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "kind"),
    [
        ("vacation", VACATION),
        ("отпуск", VACATION),
        ("sick", SICK_LEAVE),
        ("sick_leave", SICK_LEAVE),
        ("больничный", SICK_LEAVE),
        ("dayoff", DAY_OFF),
        ("day_off", DAY_OFF),
        ("отгул", DAY_OFF),
    ],
)
def test_every_kind_word_names_its_kind(word: str, kind: AbsenceKind) -> None:
    assert parse(f"/add {word} 05.11", TODAY) == Add(kind, date(2026, 11, 5), date(2026, 11, 5))


@pytest.mark.parametrize("word", ["Vacation", "ОТПУСК", "Больничный", "DAY_OFF"])
def test_a_kind_word_ignores_case(word: str) -> None:
    parsed = parse(f"/add {word} 05.11", TODAY)

    assert isinstance(parsed, Add)


def test_the_kind_words_are_exactly_the_eight_of_the_rfc() -> None:
    assert dict(KIND_WORDS) == {
        "vacation": VACATION,
        "отпуск": VACATION,
        "sick": SICK_LEAVE,
        "sick_leave": SICK_LEAVE,
        "больничный": SICK_LEAVE,
        "dayoff": DAY_OFF,
        "day_off": DAY_OFF,
        "отгул": DAY_OFF,
    }


def test_an_unknown_kind_is_refused_naming_it() -> None:
    assert _refusal("/add holiday 05.11") == Message("bot.error.unknown_kind", {"kind": "holiday"})


# --- a date without a year: the next occurrence from today ---------------------


@pytest.mark.parametrize(
    ("today", "text", "expected"),
    [
        # Today counts: a date that is today has not passed.
        (date(2026, 12, 30), "30.12", date(2026, 12, 30)),
        # Across the year boundary from 30.12: January is next year.
        (date(2026, 12, 30), "02.01", date(2027, 1, 2)),
        # Yesterday is a year away.
        (date(2026, 12, 30), "29.12", date(2027, 12, 29)),
        (date(2026, 12, 30), "31.12", date(2026, 12, 31)),
        # From 02.01 the other way: December is this year, the 1st of January the next one.
        (date(2027, 1, 2), "30.12", date(2027, 12, 30)),
        (date(2027, 1, 2), "02.01", date(2027, 1, 2)),
        (date(2027, 1, 2), "01.01", date(2028, 1, 1)),
        (date(2027, 1, 2), "03.01", date(2027, 1, 3)),
    ],
)
def test_a_yearless_single_date_is_its_next_occurrence_from_today(
    today: date, text: str, expected: date
) -> None:
    assert parse(f"/add dayoff {text}", today) == Add(DAY_OFF, expected, expected)


def test_a_yearless_range_across_the_new_year_ends_next_year() -> None:
    assert parse("/add vacation 28.12-09.01", TODAY) == Add(
        VACATION, date(2026, 12, 28), date(2027, 1, 9)
    )


@pytest.mark.parametrize("today", [date(2026, 12, 30), date(2027, 1, 2)])
def test_a_yearless_range_that_has_started_keeps_its_start(today: date) -> None:
    # On 30.12 and on 02.01 the vacation of 28.12-09.01 is running: it is that one.
    assert parse("/add vacation 28.12-09.01", today) == Add(
        VACATION, date(2026, 12, 28), date(2027, 1, 9)
    )


def test_a_yearless_range_entered_after_it_started_is_the_running_one() -> None:
    # A sick leave entered on its second day: the end is ahead, the start just behind.
    assert parse("/add sick 23.10-27.10", TODAY) == Add(
        SICK_LEAVE, date(2026, 10, 23), date(2026, 10, 27)
    )


def test_a_yearless_range_ending_today_is_this_years() -> None:
    assert parse("/add sick 20.10-24.10", TODAY) == Add(
        SICK_LEAVE, date(2026, 10, 20), date(2026, 10, 24)
    )


def test_a_yearless_range_that_is_over_is_its_next_occurrence() -> None:
    # The end has passed this year, so the whole range is next year's.
    assert parse("/add vacation 01.10-05.10", TODAY) == Add(
        VACATION, date(2027, 10, 1), date(2027, 10, 5)
    )


def test_a_yearless_start_before_a_dated_end_takes_the_end_year() -> None:
    assert parse("/add vacation 28.12-09.01.2028", TODAY) == Add(
        VACATION, date(2027, 12, 28), date(2028, 1, 9)
    )


def test_a_yearless_start_on_its_dated_end_is_that_day() -> None:
    assert parse("/add dayoff 09.01-09.01.2028", TODAY) == Add(
        DAY_OFF, date(2028, 1, 9), date(2028, 1, 9)
    )


def test_a_yearless_end_after_a_dated_start_is_its_next_occurrence_from_the_start() -> None:
    assert parse("/add vacation 28.12.2027-09.01", TODAY) == Add(
        VACATION, date(2027, 12, 28), date(2028, 1, 9)
    )


def test_a_yearless_end_on_its_dated_start_is_that_day() -> None:
    assert parse("/add dayoff 28.12.2027-28.12", TODAY) == Add(
        DAY_OFF, date(2027, 12, 28), date(2027, 12, 28)
    )


def test_a_dated_range_ignores_today() -> None:
    # An explicit year is taken as written, even when the days are over.
    assert parse("/add vacation 01.10.2025-05.10.2025", TODAY) == Add(
        VACATION, date(2025, 10, 1), date(2025, 10, 5)
    )


def test_the_29th_of_february_is_read_in_the_next_year_that_has_it() -> None:
    # 2027 has none, so from a day in 2027 after February the next one is 2028's.
    assert parse("/add dayoff 29.02", date(2027, 3, 1)) == Add(
        DAY_OFF, date(2028, 2, 29), date(2028, 2, 29)
    )


def test_the_29th_of_february_this_year_when_it_is_still_ahead() -> None:
    assert parse("/add dayoff 29.02", date(2028, 1, 10)) == Add(
        DAY_OFF, date(2028, 2, 29), date(2028, 2, 29)
    )


def test_the_29th_of_february_with_no_leap_year_ahead_is_refused() -> None:
    # From October 2026 neither 2026 nor 2027 has one: not this year, not next.
    assert _refusal("/add dayoff 29.02") == Message("bot.error.no_such_day", {"text": "29.02"})


def test_a_yearless_29th_of_february_as_a_start_takes_the_leap_year_before_the_end() -> None:
    assert parse("/add vacation 29.02-02.03.2029", TODAY) == Add(
        VACATION, date(2028, 2, 29), date(2029, 3, 2)
    )


def test_a_yearless_29th_of_february_as_a_start_with_no_leap_year_before_is_refused() -> None:
    assert _refusal("/add vacation 29.02-02.03.2027") == Message(
        "bot.error.no_such_day", {"text": "29.02"}
    )


def test_a_yearless_29th_of_february_as_an_end_takes_the_leap_year_after_the_start() -> None:
    assert parse("/add vacation 20.02.2028-29.02", TODAY) == Add(
        VACATION, date(2028, 2, 20), date(2028, 2, 29)
    )


def test_a_yearless_29th_of_february_as_an_end_with_no_leap_year_after_is_refused() -> None:
    assert _refusal("/add vacation 20.03.2026-29.02") == Message(
        "bot.error.no_such_day", {"text": "29.02"}
    )


def test_a_yearless_range_whose_end_has_no_day_ahead_is_refused() -> None:
    assert _refusal("/add vacation 20.02-29.02") == Message(
        "bot.error.no_such_day", {"text": "29.02"}
    )


def test_a_yearless_range_whose_start_has_no_day_before_its_end_is_refused() -> None:
    # The end, 02.03, is next in 2027; neither 2027 nor 2026 has a 29th of February.
    assert _refusal("/add vacation 29.02-02.03") == Message(
        "bot.error.no_such_day", {"text": "29.02"}
    )


# --- the refusals of /add -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "/add",
        "/add vacation",
        "/add 03.11-14.11",
        "/add vacation 03.11 05.11 07.11",
        "/add vacation 03.11 - 05.11 07.11",
    ],
)
def test_add_with_the_wrong_number_of_words_is_refused_with_its_usage(text: str) -> None:
    assert _refusal(text) == Message("bot.error.usage.add")


@pytest.mark.parametrize(
    "token",
    [
        "3/11",
        "03.11.26",
        "03-11",
        "2026.11.03",
        "tomorrow",
        "03.11.",
        ".03.11",
        "\uff11\uff12.11",
        "003.11",
    ],
)
def test_a_malformed_date_is_refused_with_the_expected_format(token: str) -> None:
    assert _refusal(f"/add vacation {token}") == Message(
        "bot.error.malformed_date", {"text": token}
    )


def test_a_malformed_date_in_a_joined_range_names_the_whole_range() -> None:
    assert _refusal("/add vacation 03.11-14.1x") == Message(
        "bot.error.malformed_date", {"text": "03.11-14.1x"}
    )


def test_a_malformed_second_date_of_a_spaced_range_is_named() -> None:
    assert _refusal("/add vacation 03.11 14.1x") == Message(
        "bot.error.malformed_date", {"text": "14.1x"}
    )


def test_a_malformed_first_date_of_a_spaced_range_is_named() -> None:
    assert _refusal("/add vacation 03.1x 14.11") == Message(
        "bot.error.malformed_date", {"text": "03.1x"}
    )


def test_a_joined_range_as_one_of_two_words_is_a_malformed_date() -> None:
    assert _refusal("/add vacation 03.11-05.11 07.11") == Message(
        "bot.error.malformed_date", {"text": "03.11-05.11"}
    )


def test_a_separator_alone_is_not_a_date() -> None:
    assert _refusal("/add vacation -") == Message("bot.error.malformed_date", {"text": "-"})


@pytest.mark.parametrize("token", ["31.02.2027", "00.11", "32.01", "15.13", "15.00", "2027-02-30"])
def test_a_day_the_calendar_does_not_have_is_refused_naming_it(token: str) -> None:
    assert _refusal(f"/add vacation {token}") == Message("bot.error.no_such_day", {"text": token})


def test_a_year_out_of_range_is_a_day_the_calendar_does_not_have() -> None:
    assert _refusal("/add vacation 0000-01-01") == Message(
        "bot.error.no_such_day", {"text": "0000-01-01"}
    )


def test_a_reversed_dated_range_is_refused_with_both_days() -> None:
    assert _refusal("/add vacation 14.11.2026-03.11.2026") == Message(
        "bot.error.reversed_range", {"first": "14.11.2026", "last": "03.11.2026"}
    )


def test_a_reversed_iso_range_is_refused_with_both_days_written_dotted() -> None:
    assert _refusal("/add vacation 2026-11-14 2026-11-03") == Message(
        "bot.error.reversed_range", {"first": "14.11.2026", "last": "03.11.2026"}
    )


def test_a_kind_is_checked_before_the_dates() -> None:
    assert _refusal("/add holiday 3/11") == Message("bot.error.unknown_kind", {"kind": "holiday"})


# --- /del -----------------------------------------------------------------------


def test_del_names_the_id_to_delete() -> None:
    assert parse("/del 4", TODAY) == Delete(4)


def test_del_reads_a_large_id() -> None:
    assert parse("/del 1234", TODAY) == Delete(1234)


def test_del_reads_the_first_id() -> None:
    assert parse("/del 1", TODAY) == Delete(1)


@pytest.mark.parametrize("text", ["/del", "/del 4 5"])
def test_del_with_the_wrong_number_of_words_is_refused_with_its_usage(text: str) -> None:
    assert _refusal(text) == Message("bot.error.usage.del")


@pytest.mark.parametrize("token", ["0", "-1", "four", "4.0", "#4", "\uff11", "+4", "4x"])
def test_del_with_something_other_than_an_id_is_refused_naming_it(token: str) -> None:
    assert _refusal(f"/del {token}") == Message("bot.error.bad_id", {"text": token})


def test_del_with_an_id_longer_than_nine_digits_is_refused() -> None:
    assert _refusal("/del 1234567890") == Message("bot.error.bad_id", {"text": "1234567890"})


def test_del_with_a_wall_of_digits_is_refused_rather_than_raising() -> None:
    # int() refuses more than 4300 digits with a ValueError; the parser must not get there.
    digits = "9" * 5000

    assert _refusal(f"/del {digits}") == Message("bot.error.bad_id", {"text": digits})


def test_del_reads_the_longest_id() -> None:
    assert parse("/del 999999999", TODAY) == Delete(999_999_999)


# --- /edit ----------------------------------------------------------------------


def test_edit_with_new_dates_keeps_the_kind() -> None:
    assert parse("/edit 4 05.11-16.11", TODAY) == Edit(
        4, None, date(2026, 11, 5), date(2026, 11, 16)
    )


def test_edit_with_a_kind_and_new_dates() -> None:
    assert parse("/edit 4 больничный 05.11 16.11", TODAY) == Edit(
        4, SICK_LEAVE, date(2026, 11, 5), date(2026, 11, 16)
    )


def test_edit_with_a_single_date() -> None:
    assert parse("/edit 2 dayoff 05.11", TODAY) == Edit(
        2, DAY_OFF, date(2026, 11, 5), date(2026, 11, 5)
    )


def test_edit_of_a_running_absence_extends_it() -> None:
    # On 24.10 the sick leave of 20.10 is running: its new end is ahead, its start behind.
    assert parse("/edit 5 20.10-30.10", TODAY) == Edit(
        5, None, date(2026, 10, 20), date(2026, 10, 30)
    )


@pytest.mark.parametrize(
    "text", ["/edit", "/edit 4", "/edit 4 vacation", "/edit 4 sick 1.11 2.11 3.11"]
)
def test_edit_without_dates_or_with_too_many_words_is_refused_with_its_usage(text: str) -> None:
    assert _refusal(text) == Message("bot.error.usage.edit")


def test_edit_with_something_other_than_an_id_is_refused_naming_it() -> None:
    assert _refusal("/edit vacation 05.11") == Message("bot.error.bad_id", {"text": "vacation"})


def test_edit_with_an_unknown_kind_is_refused_naming_it() -> None:
    assert _refusal("/edit 4 holiday 05.11") == Message(
        "bot.error.unknown_kind", {"kind": "holiday"}
    )


def test_edit_with_a_malformed_date_is_refused_with_the_expected_format() -> None:
    assert _refusal("/edit 4 5/11") == Message("bot.error.malformed_date", {"text": "5/11"})


def test_edit_with_a_reversed_range_is_refused() -> None:
    assert _refusal("/edit 4 sick 14.11.2026 03.11.2026") == Message(
        "bot.error.reversed_range", {"first": "14.11.2026", "last": "03.11.2026"}
    )


# --- what is not a command ------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "hello", "add vacation 03.11", "отпуск"])
def test_a_text_that_is_not_a_command_is_refused_with_the_hint(text: str) -> None:
    assert _refusal(text) == Message("bot.error.not_a_command")


@pytest.mark.parametrize("text", ["/delete 4", "/foo", "/", "/Remove 4"])
def test_an_unknown_command_is_refused_naming_it(text: str) -> None:
    command = text.split()[0].lower()

    assert _refusal(text) == Message("bot.error.unknown_command", {"command": command})


def test_an_unknown_command_addressed_to_the_bot_is_named_without_the_bot() -> None:
    assert _refusal("/foo@horizon_tracker_bot") == Message(
        "bot.error.unknown_command", {"command": "/foo"}
    )


# --- the values -------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        Add(VACATION, date(2026, 11, 3), date(2026, 11, 14)),
        Delete(4),
        Edit(4, None, date(2026, 11, 3), date(2026, 11, 3)),
        List(),
        Help(),
        CommandError(Message("bot.error.usage.add")),
    ],
)
def test_a_parsed_command_is_immutable(command: object) -> None:
    attribute = "changed_later"

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(command, attribute, 1)


def test_parse_does_not_build_an_absence_with_a_reversed_range() -> None:
    # Absence raises a bare ValueError on a reversed range; the parser refuses first.
    parsed = parse("/add vacation 2026-11-14 2026-11-03", TODAY)

    assert isinstance(parsed, CommandError)


# --- every refusal is a catalogue message ---------------------------------------

_REFUSAL_FOR_EACH_KEY = {
    "bot.error.not_a_command": "hello",
    "bot.error.unknown_command": "/foo",
    "bot.error.unknown_kind": "/add holiday 05.11",
    "bot.error.malformed_date": "/add vacation 3/11",
    "bot.error.no_such_day": "/add vacation 31.02.2027",
    "bot.error.reversed_range": "/add vacation 14.11.2026-03.11.2026",
    "bot.error.bad_id": "/del four",
    "bot.error.usage.add": "/add",
    "bot.error.usage.del": "/del",
    "bot.error.usage.edit": "/edit",
}


@pytest.mark.parametrize(("key", "text"), sorted(_REFUSAL_FOR_EACH_KEY.items()))
def test_each_refusal_is_its_catalogue_message(key: str, text: str) -> None:
    assert _refusal(text).key == key
    assert key in MESSAGES


@pytest.mark.parametrize("text", sorted(_REFUSAL_FOR_EACH_KEY.values()))
@pytest.mark.parametrize("language", list(Language))
def test_every_refusal_reads_in_every_language(text: str, language: Language) -> None:
    assert _refusal(text).in_language(language).strip()


# --- any text at all ----------------------------------------------------------------

_PIECES = [
    "/add",
    "/edit",
    "/del",
    "/list",
    "/x",
    "vacation",
    "отгул",
    "4",
    "0",
    "-",
    "–",
    " ",
    "03.11",
    "29.02",
    "31.12",
    "2026-11-03",
    "14.11.2026",
    "1.1",
    ".",
    "x",
    "@b",
    "\n",
]


def test_parse_answers_every_text_with_a_command_or_a_refusal() -> None:
    # A seeded sweep over the pieces the parser reads: it never raises, and never answers
    # a range that ends before it starts.
    rng = random.Random(20261024)
    for _ in range(3000):
        text = "".join(rng.choice(_PIECES) for _ in range(rng.randint(0, 6)))
        parsed = parse(text, TODAY)
        if isinstance(parsed, Add | Edit):
            assert parsed.first_day <= parsed.last_day, text
        else:
            assert isinstance(parsed, List | Help | Delete | CommandError), text
