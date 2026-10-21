"""Unit tests for the message catalogue: the languages, the lookup and its completeness."""

import string
import unicodedata
from collections.abc import Mapping

import pytest

from horizon_tracker.domain.messages import (
    DEFAULT_LANGUAGE,
    MESSAGES,
    Language,
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
