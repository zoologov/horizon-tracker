"""Language: HT_LANGUAGE picks what the owner reads; the operator's log stays English.

Every scenario leaves the notifier unpinned, so the language travels as in production:
``HT_LANGUAGE`` in the command's environment, ``Settings.language`` when the command loads
it, and the Telegram notifier built from those settings by the composition root. The Then
steps read only the boundary: the messages that reached the recording Bot API, the
command's stdout, its stderr and its exit code.

On stderr two kinds of line meet. A log record starts with its timestamp and level
(``2026-10-21 07:30:00,123 INFO horizon_tracker...: <message>``); anything else is a line
the command said to the reader, such as a configuration error echoed in their language.
A line is Russian when it holds a Cyrillic letter, English when it holds none.

The catalogue scenario asks the catalogue itself, through ``text``, for every key in every
supported language with the fields that key's default-language text names, as a caller of
the key would fill them.
"""

import re
from dataclasses import dataclass, field
from string import Formatter

from pytest_bdd import given, parsers, scenarios, then, when

from horizon_tracker.domain.messages import (
    DEFAULT_LANGUAGE,
    MESSAGES,
    Language,
    missing_translations,
    text,
)
from horizon_tracker.domain.ports import HorizonClientError
from horizon_tracker.domain.report import Reason
from tests.acceptance.steps.conftest import Scene, moment
from tests.support.cli_world import World

scenarios("../features/language.feature")

LANGUAGE = "HT_LANGUAGE"
# More attempts than the retry policy ever makes, so every attempt of the run is refused.
EVERY_ATTEMPT = 9

_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_LOG_RECORD = re.compile(
    r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} (?P<record>[A-Z]+ \S+: (?P<message>.*))$"
)
_READERS = {"English": Language.EN, "Russian": Language.RU}


def _is_russian(line: str) -> bool:
    return _CYRILLIC.search(line) is not None


def _lines(output: str) -> list[str]:
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines, "nothing was said, so no language can be read off it"
    return lines


def _in_language(lines: list[str], reader: str) -> list[str]:
    """The lines that are not in ``reader``'s language."""
    wanted = _READERS[reader] is Language.RU
    return [line for line in lines if _is_russian(line) is not wanted]


def _log_records(stderr: str) -> list[str]:
    """Every log record on ``stderr``, without its timestamp; there must be at least one."""
    records = [m["record"] for line in stderr.splitlines() if (m := _LOG_RECORD.match(line))]
    assert records, f"the command logged nothing:\n{stderr}"
    return records


def _log_messages(stderr: str) -> list[str]:
    return [m["message"] for line in stderr.splitlines() if (m := _LOG_RECORD.match(line))]


def _reads_in(scene: Scene, code: str | None) -> None:
    """The scene's command reads ``HT_LANGUAGE`` as ``code``; the notifier follows it."""
    scene.notification_language = None
    scene.env_overrides[LANGUAGE] = code


def _refused_login(world: World) -> None:
    world.client.fail_on("login", HorizonClientError(Reason.LOGIN_REJECTED), times=EVERY_ATTEMPT)


@dataclass
class CatalogueAnswers:
    """What the catalogue answered for every key in every language, and what it refused."""

    texts: dict[tuple[str, Language], str] = field(default_factory=dict)
    refused: list[tuple[str, Language]] = field(default_factory=list)


def _fields_of(key: str) -> dict[str, str]:
    """The fields the key's default-language text names, each filled with its own name."""
    template = MESSAGES[key].get(DEFAULT_LANGUAGE, "")
    names = {name for _, name, _, _ in Formatter().parse(template) if name}
    return {name: f"<{name}>" for name in names}


# --- Given ----------------------------------------------------------------------------


@given(parsers.parse('HT_LANGUAGE is "{code}"'))
def language_is(scene: Scene, code: str) -> None:
    _reads_in(scene, code)


@given("HT_LANGUAGE is not set")
def language_unset(scene: Scene) -> None:
    _reads_in(scene, None)


@given("HT_LANGUAGE is set to blanks only")
def language_blank(scene: Scene) -> None:
    _reads_in(scene, "   ")


@given(parsers.parse('the variable {name} is "{value}"'))
def variable_is(scene: Scene, name: str, value: str) -> None:
    scene.env_overrides[name] = value


@given("every login attempt is refused")
def login_refused(scene: Scene) -> None:
    scene.scripts.append(_refused_login)


@given("the message catalogue the service ships", target_fixture="answers")
def shipped_catalogue() -> CatalogueAnswers:
    assert MESSAGES, "the service ships no message catalogue"
    return CatalogueAnswers()


# --- When -----------------------------------------------------------------------------


@when("every key is asked for in every supported language with each of its fields filled")
def ask_every_key(answers: CatalogueAnswers) -> None:
    for key in sorted(MESSAGES):
        fields = _fields_of(key)
        for language in Language:
            try:
                answers.texts[key, language] = text(key, language, **fields)
            except KeyError:
                answers.refused.append((key, language))


@when(parsers.parse("a check-in runs at {clock} on {weekday} {day} for a reader of each language"))
def checkin_for_each_reader(scene: Scene, clock: str, weekday: str, day: str) -> None:
    for language in Language:
        _reads_in(scene, language.value)
        scene.run(["checkin"], moment(clock, weekday, day))


# --- Then: the catalogue ----------------------------------------------------------------


@then("every key answers a text in every supported language")
def every_key_answers(answers: CatalogueAnswers) -> None:
    assert answers.refused == [], f"keys refused in a language: {answers.refused}"
    blank = [pair for pair, answer in answers.texts.items() if not answer.strip()]
    assert blank == [], f"keys answering a blank text: {blank}"
    assert len(answers.texts) == len(MESSAGES) * len(Language)


@then("every Russian text holds a Russian letter")
def russian_texts_are_russian(answers: CatalogueAnswers) -> None:
    latin = [
        key
        for (key, language), answer in answers.texts.items()
        if language is Language.RU and not _is_russian(answer)
    ]
    assert latin == [], f"Russian texts without a Russian letter: {latin}"


@then("no English text holds a Russian letter")
def english_texts_are_english(answers: CatalogueAnswers) -> None:
    russian = [
        key
        for (key, language), answer in answers.texts.items()
        if language is Language.EN and _is_russian(answer)
    ]
    assert russian == [], f"English texts with a Russian letter: {russian}"


@then("the catalogue names no missing translation")
def nothing_missing() -> None:
    assert missing_translations() == []


# --- Then: what the owner read ----------------------------------------------------------


@then(parsers.parse("every line of the message is in {reader}"))
def message_in(scene: Scene, reader: str) -> None:
    lines = _lines(scene.only_message().text)
    assert _in_language(lines, reader) == [], f"not in {reader}:\n{lines}"


@then(parsers.parse("every line of the output is in {reader}"))
def output_in(scene: Scene, reader: str) -> None:
    lines = _lines(scene.outcome.stdout)
    assert _in_language(lines, reader) == [], f"not in {reader}:\n{lines}"


@then("each reader got the message in their own language")
def each_reader_in_their_language(scene: Scene) -> None:
    messages = scene.bot.messages
    assert len(messages) == len(Language), f"expected one message per reader: {messages}"
    for language, message in zip(Language, messages, strict=True):
        reader = next(name for name, code in _READERS.items() if code is language)
        lines = _lines(message.text)
        assert _in_language(lines, reader) == [], f"the {reader} reader got:\n{lines}"


# --- Then: what the operator and the reader read on stderr ------------------------------


@then(parsers.parse('the service log reads "{message}"'))
def log_reads(scene: Scene, message: str) -> None:
    logged = _log_messages(scene.outcome.stderr)
    assert message in logged, f"{message!r} is not a log message of:\n{scene.outcome.stderr}"


@then(parsers.parse('the error output reads "{line}"'))
def error_output_reads(scene: Scene, line: str) -> None:
    stderr = scene.outcome.stderr
    assert line in stderr.splitlines(), f"{line!r} is not a line of:\n{stderr}"


@then(
    parsers.re(r"(?P<variable>[A-Z_]+) is named on (?P<count>\d+) lines? of the error output"),
    converters={"count": int},
)
def variable_named(scene: Scene, variable: str, count: int) -> None:
    stderr = scene.outcome.stderr
    naming = [line for line in stderr.splitlines() if f"{variable}:" in line]
    assert len(naming) == count, f"{variable} is named on {len(naming)} lines of:\n{stderr}"


@then("no line of the service log is in Russian")
def log_in_english(scene: Scene) -> None:
    russian = [record for record in _log_records(scene.outcome.stderr) if _is_russian(record)]
    assert russian == [], f"log records in Russian: {russian}"


@then("no line of the error output is in Russian")
def error_output_in_english(scene: Scene) -> None:
    lines = _lines(scene.outcome.stderr)
    assert _in_language(lines, "English") == [], f"not in English:\n{lines}"


@then("every run logged the same lines, their timestamps aside")
def same_log_for_every_reader(scene: Scene) -> None:
    logs = [_log_records(result.stderr) for result in scene.results]
    assert len(logs) == len(Language), f"expected one run per reader, ran {len(logs)}"
    assert all(log == logs[0] for log in logs), f"the logs differ by reader: {logs}"
    russian = [record for record in logs[0] if _is_russian(record)]
    assert russian == [], f"log records in Russian: {russian}"


@then("no adapter was built")
def nothing_built(scene: Scene) -> None:
    assert scene.ran.opened == [], "the adapters were built before the settings were refused"
