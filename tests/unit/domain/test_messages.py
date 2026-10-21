"""Unit tests for the message catalogue: the languages, the lookup and its completeness."""

import re
import string
import unicodedata
from collections.abc import Mapping, MutableMapping

import pytest

from horizon_tracker.domain.messages import (
    DEFAULT_LANGUAGE,
    MESSAGES,
    Language,
    Message,
    missing_translations,
    text,
)

# --- the languages ----------------------------------------------------------------


def test_the_supported_languages_are_english_and_russian() -> None:
    assert {language.value for language in Language} == {"en", "ru"}


def test_the_default_language_is_english() -> None:
    assert DEFAULT_LANGUAGE is Language.EN


def test_a_language_is_read_from_its_code() -> None:
    assert Language("ru") is Language.RU


def test_an_unknown_language_code_is_refused() -> None:
    with pytest.raises(ValueError, match="'de'"):
        Language("de")


# --- the lookup -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "expected"),
    [(Language.EN, "Check-in succeeded"), (Language.RU, "Вход выполнен")],
)
def test_text_answers_in_the_language_asked(language: Language, expected: str) -> None:
    assert text("report.checkin.succeeded", language) == expected


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (Language.EN, "Time: 20.10.2026 07:56:12 MSK, planned for 07:43"),
        (Language.RU, "Время: 20.10.2026 07:56:12 MSK, назначено на 07:43"),
    ],
)
def test_text_fills_the_named_fields(language: Language, expected: str) -> None:
    filled = text("report.time_planned", language, at="20.10.2026 07:56:12 MSK", planned="07:43")

    assert filled == expected


def test_text_leaves_a_text_without_fields_as_written() -> None:
    # Only the named fields are filled: a brace-free text passes through untouched.
    assert text("plan.steps", Language.EN) == "steps of one attempt:"


def test_text_refuses_an_unknown_key_naming_it() -> None:
    with pytest.raises(KeyError, match=r"'report\.nothing'"):
        text("report.nothing", Language.EN)


def test_text_refuses_a_missing_field_naming_it() -> None:
    with pytest.raises(KeyError, match="'planned'"):
        text("report.time_planned", Language.EN, at="now")


def test_text_refuses_to_answer_a_text_with_its_fields_left_unfilled() -> None:
    # No fields passed is no excuse: "Time: {at}" must never reach the owner.
    with pytest.raises(KeyError, match="'at'"):
        text("report.time", Language.RU)


def test_text_takes_a_field_named_like_its_own_parameters() -> None:
    # The probe names the configured language; the key and the language are positional.
    filled = text("probe.settings.ok", Language.EN, **SETTINGS_FIELDS)

    assert filled.endswith(", Europe/Moscow, language ru")


# --- a message: a key and its fields, not yet in a language -----------------------

SETTINGS_FIELDS: Mapping[str, object] = {
    "url": "https://portal.example.invalid/",
    "desktop": "DEV desktop",
    "checkin": "07:30-08:10",
    "checkout": "16:30-17:10",
    "timezone": "Europe/Moscow",
    "language": "ru",
}


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (Language.EN, "open desktop 'DEV desktop' and wait"),
        (Language.RU, "открыть стол 'DEV desktop' и дождаться"),
    ],
)
def test_a_message_reads_in_the_language_asked(language: Language, expected: str) -> None:
    message = Message("plan.step.checkin.open", {"desktop": "DEV desktop"})

    assert message.in_language(language).startswith(expected)


def test_a_message_without_fields_reads_as_its_text() -> None:
    assert Message("plan.step.login").in_language(Language.EN) == "log in to the Horizon portal"


def test_a_message_with_an_unknown_key_is_refused_when_it_is_made() -> None:
    # A typo in a use case fails where it is written, not when the CLI prints it.
    with pytest.raises(KeyError, match=r"'plan\.step\.nothing'"):
        Message("plan.step.nothing")


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (Language.EN, "configuration error: no such time of day"),
        (Language.RU, "ошибка настройки: такого времени суток нет"),
    ],
)
def test_a_message_in_a_field_reads_in_the_same_language(language: Language, expected: str) -> None:
    # A reason handed over as a message must not fall back into another language.
    message = Message("config.error", {"error": Message("config.no_such_time")})

    assert message.in_language(language) == expected


def test_a_message_keeps_its_fields_when_the_callers_mapping_changes_later() -> None:
    given = {"path": "/usr/bin/google-chrome"}
    message = Message("probe.chrome.not_found", given)

    given["path"] = "/opt/chrome"

    assert message.fields == {"path": "/usr/bin/google-chrome"}


def test_the_fields_of_a_message_cannot_be_changed() -> None:
    message = Message("probe.chrome.not_found", {"path": "/usr/bin/google-chrome"})

    assert not isinstance(message.fields, MutableMapping)


def test_two_messages_with_the_same_key_and_fields_are_equal_and_hash_alike() -> None:
    first = Message("probe.chrome.not_found", {"path": "/usr/bin/google-chrome"})
    second = Message("probe.chrome.not_found", {"path": "/usr/bin/google-chrome"})

    assert first == second
    assert hash(first) == hash(second)
    assert first != Message("probe.chrome.not_found", {"path": "/opt/chrome"})


# --- completeness -----------------------------------------------------------------


def test_every_key_has_a_text_in_every_language() -> None:
    assert missing_translations() == []


def test_the_catalogue_is_not_empty() -> None:
    # A vacuous catalogue would pass the completeness test above.
    assert len(MESSAGES) > len(Language)


def test_a_key_without_a_language_is_named_with_that_language() -> None:
    catalogue = {"a.key": {Language.EN: "text"}, "b.key": {Language.RU: "текст"}}

    assert missing_translations(catalogue) == [("a.key", Language.RU), ("b.key", Language.EN)]


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_text_counts_as_missing(blank: str) -> None:
    catalogue = {"a.key": {Language.EN: "text", Language.RU: blank}}

    assert missing_translations(catalogue) == [("a.key", Language.RU)]


def test_a_complete_catalogue_misses_nothing() -> None:
    catalogue = {"a.key": {Language.EN: "text", Language.RU: "текст"}}

    assert missing_translations(catalogue) == []


def _fields(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field is not None}


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_every_translation_of_a_key_takes_the_same_fields(key: str) -> None:
    # A field one language lacks would fail only in that language, at 07:43.
    translations: Mapping[Language, str] = MESSAGES[key]

    assert len({frozenset(_fields(template)) for template in translations.values()}) == 1


def _has_cyrillic(text_: str) -> bool:
    return any(unicodedata.name(letter, "").startswith("CYRILLIC") for letter in text_)


def test_the_cyrillic_probe_tells_the_scripts_apart() -> None:
    assert _has_cyrillic("Вход выполнен")
    assert not _has_cyrillic("Check-in succeeded")


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_no_english_text_falls_into_cyrillic(key: str) -> None:
    assert not _has_cyrillic(MESSAGES[key][Language.EN])


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_every_russian_text_is_written_in_russian(key: str) -> None:
    # A Russian entry copied from English would pass completeness and still read English.
    assert _has_cyrillic(MESSAGES[key][Language.RU])


# An environment variable is an identifier the reader types, so it stays as written.
_VARIABLE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_REFUSALS = sorted(key for key in MESSAGES if key.startswith(("config.", "schedule.")))


def _latin_outside_fields_and_variables(template: str) -> str:
    literal = "".join(text_ for text_, _, _, _ in string.Formatter().parse(template))
    return "".join(
        letter for letter in _VARIABLE.sub("", literal) if letter.isascii() and letter.isalpha()
    )


def test_the_latin_probe_skips_fields_and_variable_names() -> None:
    assert _latin_outside_fields_and_variables("уберите HT_CHECKIN_WINDOW: {text!r}") == ""
    assert _latin_outside_fields_and_variables("ожидается HH:MM") == "HHMM"


@pytest.mark.parametrize("key", _REFUSALS)
def test_a_russian_refusal_names_nothing_in_english(key: str) -> None:
    # PRD US-2: no line falls into another language; only identifiers and values stay.
    assert _latin_outside_fields_and_variables(MESSAGES[key][Language.RU]) == ""
