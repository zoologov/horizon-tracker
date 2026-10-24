"""The message catalogue: every text a person reads, keyed, in every supported language.

One responsibility: turning a message key into its text in a language. The catalogue is
plain data in code (two languages and a few dozen keys do not earn gettext), and
``text(key, language, **fields)`` fills a text's named fields with ``str.format``. The
use cases hand out keys and values; whoever shows them to a person picks the language.
Logs are not in here: the operator reads them in English whatever the language.

Every key has a text in every ``Language`` -- ``missing_translations()`` names any pair
that does not, and a test holds the catalogue to an empty answer. The catalogue holds
the texts of the notification, the probe, the dry run, the bot and the configuration
errors: English is the default language, Russian the other one.
"""

# beadloom:domain=domain
# beadloom:feature=messages

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Language(StrEnum):
    """A language the owner can read the messages in, by its ISO 639-1 code."""

    EN = "en"
    RU = "ru"


DEFAULT_LANGUAGE: Final = Language.EN

_EN = Language.EN
_RU = Language.RU

MESSAGES: Final[Mapping[str, Mapping[Language, str]]] = {
    # --- the run report: headline, time, calendar line, reason -----------------------
    "report.checkin.succeeded": {_EN: "Check-in succeeded", _RU: "Вход выполнен"},
    "report.checkin.failed": {_EN: "Check-in failed", _RU: "Вход не удался"},
    "report.checkin.skipped": {_EN: "Check-in skipped", _RU: "Вход пропущен"},
    "report.checkout.succeeded": {_EN: "Check-out succeeded", _RU: "Выход выполнен"},
    "report.checkout.failed": {_EN: "Check-out failed", _RU: "Выход не удался"},
    "report.checkout.skipped": {_EN: "Check-out skipped", _RU: "Выход пропущен"},
    "report.time": {_EN: "Time: {at}", _RU: "Время: {at}"},
    "report.time_planned": {
        _EN: "Time: {at}, planned for {planned}",
        _RU: "Время: {at}, назначено на {planned}",
    },
    # One line per VerdictSource, and one for a --force run that asked no calendar.
    "report.calendar.calendar": {
        _EN: "Production calendar: isdayoff.ru",
        _RU: "Производственный календарь: isdayoff.ru",
    },
    "report.calendar.weekday_fallback": {
        _EN: "Production calendar: unavailable, the Mon–Fri rule decided",
        _RU: "Производственный календарь: недоступен, решило правило Пн–Пт",
    },
    "report.calendar.not_asked": {
        _EN: "Production calendar: not asked, manual run --force",
        _RU: "Производственный календарь: не спрашивали, ручной прогон --force",
    },
    "report.reason": {_EN: "Reason: {reason}", _RU: "Причина: {reason}"},
    "report.reason_span": {
        _EN: "Reason: {reason} ({span})",
        _RU: "Причина: {reason} ({span})",
    },
    # --- why a run failed or was skipped: one per Reason ----------------------------
    "reason.non_working_day": {_EN: "a day off", _RU: "выходной"},
    "reason.too_early": {
        _EN: "the run started before its window",
        _RU: "прогон начался до своего окна",
    },
    "reason.window_missed": {
        _EN: "the run started after its window",
        _RU: "прогон начался после своего окна",
    },
    "reason.already_logged_off": {
        _EN: "no session on the desktop, nothing to log off from",
        _RU: "сессии на столе уже нет, выходить не из чего",
    },
    "reason.portal_unreachable": {
        _EN: "the Horizon portal is unreachable",
        _RU: "портал Horizon недоступен",
    },
    "reason.login_rejected": {
        _EN: "the portal rejected the login",
        _RU: "портал отклонил вход",
    },
    "reason.desktop_not_found": {
        _EN: "the desktop is not among the available ones",
        _RU: "рабочий стол не найден среди доступных",
    },
    "reason.desktop_did_not_open": {
        _EN: "the desktop did not open",
        _RU: "рабочий стол не открылся",
    },
    "reason.logoff_not_confirmed": {
        _EN: "the Windows log off was not confirmed",
        _RU: "выход из Windows не подтвердился",
    },
    "reason.unexpected": {
        _EN: "an unexpected error, details in the journal",
        _RU: "непредвиденная ошибка, подробности в журнале",
    },
    "reason.on_vacation": {_EN: "vacation", _RU: "отпуск"},
    "reason.on_sick_leave": {_EN: "sick leave", _RU: "больничный"},
    "reason.on_day_off": {_EN: "day off taken", _RU: "отгул"},
    # --- horizon probe: the settings line, the checks and their answers -------------
    "probe.settings.ok": {
        _EN: (
            "settings: ok - portal {url}, desktop {desktop!r}, check-in {checkin}, "
            "check-out {checkout}, {timezone}, language {language}"
        ),
        _RU: (
            "настройки: в порядке - портал {url}, стол {desktop!r}, вход {checkin}, "
            "выход {checkout}, {timezone}, язык {language}"
        ),
    },
    "probe.check.portal": {_EN: "portal", _RU: "портал"},
    "probe.check.calendar": {_EN: "calendar", _RU: "календарь"},
    "probe.check.chrome": {_EN: "chrome", _RU: "браузер chrome"},
    "probe.check.absences": {_EN: "absences", _RU: "отсутствия"},
    "probe.check.schedule": {_EN: "schedule", _RU: "расписание"},
    "probe.status.ok": {_EN: "ok", _RU: "в порядке"},
    "probe.status.degraded": {_EN: "degraded", _RU: "частично"},
    "probe.status.failed": {_EN: "failed", _RU: "сбой"},
    "probe.portal.no_answer": {_EN: "no answer: {reason}", _RU: "нет ответа: {reason}"},
    "probe.portal.bundles": {
        _EN: "client bundles: {bundles}",
        _RU: "бандлы клиента: {bundles}",
    },
    "probe.calendar.no_answer": {
        _EN: "isdayoff.ru did not answer for {day}; runs fall back to the Mon-Fri rule",
        _RU: "isdayoff.ru не ответил за {day}; прогоны решают по правилу пн-пт",
    },
    "probe.calendar.working_day": {
        _EN: "isdayoff.ru: {day} is a working day",
        _RU: "isdayoff.ru: {day} - рабочий день",
    },
    "probe.calendar.day_off": {
        _EN: "isdayoff.ru: {day} is a day off",
        _RU: "isdayoff.ru: {day} - выходной",
    },
    "probe.chrome.not_found": {_EN: "not found at {path}", _RU: "не найден по пути {path}"},
    "probe.chrome.did_not_start": {
        _EN: "found at {path} but did not start: {reason}",
        _RU: "найден по пути {path}, но не запустился: {reason}",
    },
    "probe.chrome.started": {
        _EN: "Chrome {version} started from {path}",
        _RU: "Chrome {version} запущен из {path}",
    },
    "probe.absences.none": {_EN: "none ({path})", _RU: "нет ({path})"},
    # {held} counts the absences whose last day is today or later, and the finished ones
    # beside them when there are any: probe.absences.held or .held_and_finished.
    "probe.absences.entered": {
        _EN: "{held}, none ahead ({path})",
        _RU: "{held}, впереди нет ({path})",
    },
    "probe.absences.entered_next": {
        _EN: "{held}, next: {kind} {span} ({path})",
        _RU: "{held}, ближайшее: {kind} {span} ({path})",
    },
    "probe.absences.held": {
        _EN: "{count} current or upcoming",
        _RU: "текущих и предстоящих: {count}",
    },
    "probe.absences.held_and_finished": {
        _EN: "{count} current or upcoming, {finished} finished",
        _RU: "текущих и предстоящих: {count}, завершённых: {finished}",
    },
    # The reason is the store's own technical English in every language, as in the journal.
    "probe.absences.unreadable": {
        _EN: "{path}: {reason}",
        _RU: "{path}: не прочитан: {reason}",
    },
    "probe.schedule": {
        _EN: "today {check_in} / {check_out}",
        _RU: "сегодня {check_in} / {check_out}",
    },
    # --- horizon checkin|checkout --dry-run: the plan --------------------------------
    "plan.header": {_EN: "dry run: {kind} at {at}", _RU: "пробный прогон: {kind} в {at}"},
    "plan.would_run": {
        _EN: "would run now: {verdict} ({decision}{forced})",
        _RU: "запустился бы сейчас: {verdict} ({decision}{forced})",
    },
    "plan.verdict.yes": {_EN: "yes", _RU: "да"},
    "plan.verdict.no": {_EN: "no", _RU: "нет"},
    "plan.forced": {
        _EN: ", forced: window and calendar ignored",
        _RU: ", принудительно: окно и календарь не учитываются",
    },
    "plan.waits_until": {_EN: "would wait until: {moment}", _RU: "ждал бы до: {moment}"},
    "plan.calendar": {_EN: "calendar: {source}", _RU: "календарь: {source}"},
    "plan.source.calendar": {_EN: "isdayoff.ru", _RU: "календарь isdayoff.ru"},
    "plan.source.weekday_fallback": {
        _EN: "isdayoff.ru unreachable, Mon-Fri rule",
        _RU: "isdayoff.ru недоступен, правило пн-пт",
    },
    "plan.source.not_asked": {
        _EN: "not asked (forced)",
        _RU: "не спрашивали (принудительно)",
    },
    "plan.source.absent": {
        _EN: "not asked (an absence covers today)",
        _RU: "не спрашивали (сегодня внесено отсутствие)",
    },
    "plan.schedule": {_EN: "schedule: {detail}", _RU: "расписание: {detail}"},
    "plan.steps": {_EN: "steps of one attempt:", _RU: "шаги одной попытки:"},
    "plan.step.login": {
        _EN: "log in to the Horizon portal",
        _RU: "войти на портал Horizon",
    },
    "plan.step.checkin.open": {
        _EN: "open desktop {desktop!r} and wait for the Blast connection and a drawn desktop",
        _RU: "открыть стол {desktop!r} и дождаться Blast-соединения и прорисованного стола",
    },
    "plan.step.checkin.hold": {
        _EN: "hold the desktop open for {seconds} s so the Windows logon completes",
        _RU: "держать стол открытым {seconds} секунд, чтобы завершился вход в Windows",
    },
    "plan.step.checkin.disconnect": {
        _EN: "read the session state, then disconnect (the Windows session keeps running)",
        _RU: "прочитать состояние сессии, затем отключиться (сессия Windows продолжает работать)",
    },
    "plan.step.checkin.confirm": {
        _EN: "log in again and confirm the session is DISCONNECTED",
        _RU: "войти снова и убедиться, что сессия в состоянии DISCONNECTED",
    },
    "plan.step.checkout.read": {
        _EN: "read the session state of desktop {desktop!r}; stop if there is no session",
        _RU: "прочитать состояние сессии стола {desktop!r}; остановиться, если сессии нет",
    },
    "plan.step.checkout.logoff": {
        _EN: "log off from the tile menu and confirm the dialog",
        _RU: "выйти через меню плитки и подтвердить диалог",
    },
    "plan.step.checkout.confirm": {
        _EN: "confirm the session is gone (NO_SESSION)",
        _RU: "убедиться, что сессии больше нет (NO_SESSION)",
    },
    "plan.step.absences": {
        _EN: (
            "skip the day if an absence entered through the bot covers it, "
            "before the calendar is asked"
        ),
        _RU: (
            "пропустить день, на который через бота внесено отсутствие, ещё до вопроса календарю"
        ),
    },
    "plan.step.wait": {
        _EN: (
            "wait until the drawn moment {moment} if started from {start}; "
            "earlier is skipped as too early"
        ),
        _RU: (
            "ждать разыгранного момента {moment}, если запуск начат от {start}; "
            "более ранний запуск пропускается как слишком ранний"
        ),
    },
    "plan.step.retry": {
        _EN: (
            "retry a failed attempt, up to {attempts} attempts {seconds} s apart, "
            "while the window allows"
        ),
        _RU: (
            "повторять неудачную попытку, до {attempts} попыток через {seconds} секунд, "
            "пока позволяет окно"
        ),
    },
    "plan.step.report": {
        _EN: "send one report to Telegram",
        _RU: "отправить один отчёт в Telegram",
    },
    # The evening run: a skipped day was already reported by the morning run.
    "plan.step.report.no_day_skip": {
        _EN: "send one report to Telegram, unless the day is skipped: the morning reports it",
        _RU: "отправить один отчёт в Telegram, кроме пропущенного дня: такой отчёт шлёт утро",
    },
    # --- the bot: the help, the replies to the owner's commands and the refusals ------
    "bot.help": {
        _EN: (
            "Commands:\n"
            "/add <kind> <from>[-<to>] - enter an absence\n"
            "/list - every absence entered\n"
            "/edit <id> [<kind>] <from>[-<to>] - change an absence\n"
            "/del <id> - delete an absence\n"
            "/help - this text\n"
            "Kinds: vacation, sick, dayoff\n"
            "Dates: 03.11, 03.11.2026 or 2026-11-03; a date without a year is the next such day\n"
            "Example: /add vacation 03.11-14.11"
        ),
        _RU: (
            "Команды:\n"
            "/add <вид> <начало>[-<конец>] - внести отсутствие\n"
            "/list - все внесённые отсутствия\n"
            "/edit <номер> [<вид>] <начало>[-<конец>] - изменить отсутствие\n"
            "/del <номер> - удалить отсутствие\n"
            "/help - этот текст\n"
            "Виды: отпуск, больничный, отгул\n"
            "Даты: 03.11, 03.11.2026 или 2026-11-03; дата без года - ближайший такой день\n"
            "Пример: /add отпуск 03.11-14.11"
        ),
    },
    # One name per AbsenceKind, keyed by its value, as a reply names the kind.
    "bot.kind.vacation": {_EN: "vacation", _RU: "отпуск"},
    "bot.kind.sick_leave": {_EN: "sick leave", _RU: "больничный"},
    "bot.kind.day_off": {_EN: "day off", _RU: "отгул"},
    # An absence's days with the year, so a date typed without one is read back in full.
    "bot.days.single": {_EN: "on {day}", _RU: "день {day}"},
    "bot.days.span": {_EN: "from {first} to {last}", _RU: "дни {first}–{last}"},
    "bot.added": {
        _EN: "Absence {id} entered: {kind} {days}",
        _RU: "Отсутствие {id} внесено: {kind}, {days}",
    },
    "bot.edited": {
        _EN: "Absence {id} changed: {kind} {days}",
        _RU: "Отсутствие {id} изменено: {kind}, {days}",
    },
    "bot.deleted": {
        _EN: "Absence {id} deleted: {kind} {days}",
        _RU: "Отсутствие {id} удалено: {kind}, {days}",
    },
    # Under an absence that would have covered today, entered once today's check-in range
    # has begun: it starts tomorrow (or, for today alone, is not entered).
    "bot.note.after_checkin_range": {
        _EN: (
            "Today's check-in range began at {start}, so an absence starts tomorrow "
            "at the earliest; this evening's check-out runs as usual"
        ),
        _RU: (
            "Диапазон входа на сегодня начался в {start}, поэтому отсутствие начнётся "
            "не раньше завтрашнего дня; вечерний выход сегодня пройдёт как обычно"
        ),
    },
    "bot.list.empty": {_EN: "No absences entered", _RU: "Отсутствий не внесено"},
    # /list names the absences whose last day is today or later; the finished ones stay in
    # the store and are only counted, so the reply stays inside Telegram's message limit.
    "bot.list.header": {
        _EN: "Current and upcoming absences: {count}",
        _RU: "Текущих и предстоящих отсутствий: {count}",
    },
    "bot.list.none_ahead": {
        _EN: "No current or upcoming absences",
        _RU: "Текущих и предстоящих отсутствий нет",
    },
    "bot.list.item": {_EN: "Absence {id}: {kind} {days}", _RU: "Отсутствие {id}: {kind}, {days}"},
    "bot.list.finished": {
        _EN: "Finished absences, not listed: {count}",
        _RU: "Завершённых отсутствий (не показаны): {count}",
    },
    "bot.error.not_a_command": {
        _EN: "Not a command; /help lists the commands",
        _RU: "Это не команда; список команд покажет /help",
    },
    "bot.error.unknown_command": {
        _EN: "Unknown command {command}; /help lists the commands",
        _RU: "Неизвестная команда {command}; список команд покажет /help",
    },
    "bot.error.usage.add": {
        _EN: "Usage: /add <kind> <from>[-<to>], for example /add vacation 03.11-14.11",
        _RU: "Формат: /add <вид> <начало>[-<конец>], например /add отпуск 03.11-14.11",
    },
    "bot.error.usage.del": {
        _EN: "Usage: /del <id>, the id /list shows",
        _RU: "Формат: /del <номер>, номер показывает /list",
    },
    "bot.error.usage.edit": {
        _EN: "Usage: /edit <id> [<kind>] <from>[-<to>], for example /edit 4 05.11-16.11",
        _RU: "Формат: /edit <номер> [<вид>] <начало>[-<конец>], например /edit 4 05.11-16.11",
    },
    "bot.error.unknown_kind": {
        _EN: "Unknown kind {kind!r}: expected vacation, sick or dayoff",
        _RU: "Неизвестный вид {kind!r}: ожидается отпуск, больничный или отгул",
    },
    "bot.error.malformed_date": {
        _EN: (
            "Not a date {text!r}: expected 03.11, 03.11.2026 or 2026-11-03; "
            "a range is written 03.11-14.11"
        ),
        _RU: (
            "Это не дата {text!r}: ожидается 03.11, 03.11.2026 или 2026-11-03; "
            "диапазон пишется как 03.11-14.11"
        ),
    },
    "bot.error.no_such_day": {
        _EN: "No such day {text!r} in the calendar",
        _RU: "Такого дня в календаре нет: {text!r}",
    },
    "bot.error.reversed_range": {
        _EN: "The range ends on {last}, before it starts on {first}",
        _RU: "Диапазон кончается {last}, раньше своего начала {first}",
    },
    "bot.error.bad_id": {
        _EN: "Not an id {text!r}: expected a whole number from 1, the one /list shows",
        _RU: "Это не номер {text!r}: ожидается целое число от 1, какое показывает /list",
    },
    "bot.error.not_found": {
        _EN: "No absence {id}; /list shows the ones entered",
        _RU: "Отсутствия {id} нет; внесённые покажет /list",
    },
    "bot.error.overlap": {
        _EN: "These days overlap absence {id}; change or delete it first",
        _RU: "Эти дни уже заняты отсутствием {id}; сначала измените или удалите это отсутствие",
    },
    "bot.error.internal": {
        _EN: "Something went wrong; the details are in the journal",
        _RU: "Что-то пошло не так; подробности в журнале",
    },
    # --- configuration errors: the line a reader gets, then the problem after "<VARIABLE>: "
    "config.error": {_EN: "configuration error: {error}", _RU: "ошибка настройки: {error}"},
    "config.required": {_EN: "is required and not set", _RU: "обязательна и не задана"},
    "config.retired.checkin_window": {
        _EN: (
            "is no longer read: the check-in moment is drawn daily from {checkin_range} and "
            "its window lasts {grace}; remove HT_CHECKIN_WINDOW from the environment"
        ),
        _RU: (
            "больше не читается: момент входа разыгрывается ежедневно из {checkin_range}, "
            "окно момента длится {grace}; уберите HT_CHECKIN_WINDOW из окружения"
        ),
    },
    "config.retired.checkout_window": {
        _EN: (
            "is no longer read: the check-out moment is drawn daily from {checkout_range} "
            "({session_length} plus up to {extra_max} after the check-in) and its "
            "window lasts {grace}; remove HT_CHECKOUT_WINDOW from the environment"
        ),
        _RU: (
            "больше не читается: момент выхода разыгрывается ежедневно из {checkout_range} "
            "({session_length} и ещё до {extra_max} после входа), окно момента "
            "длится {grace}; уберите HT_CHECKOUT_WINDOW из окружения"
        ),
    },
    "config.unknown_time_zone": {
        _EN: "unknown time zone {key!r}",
        _RU: "неизвестный часовой пояс {key!r}",
    },
    "config.unknown_language": {
        _EN: "expected one of {choices}, got {text!r}",
        _RU: "ожидается одно из {choices}, получено {text!r}",
    },
    "config.expected_range": {
        _EN: "expected HH:MM-HH:MM, got {text!r}",
        _RU: "ожидается чч:мм-чч:мм, получено {text!r}",
    },
    "config.invalid_range": {
        _EN: "not a valid range {text!r}: {error}",
        _RU: "недопустимый диапазон {text!r}: {error}",
    },
    "config.no_such_time": {_EN: "no such time of day", _RU: "такого времени суток нет"},
    "config.expected_minutes": {
        _EN: "expected a whole number of minutes from 0 to {limit}, got {text!r}",
        _RU: "ожидается целое число минут от 0 до {limit}, получено {text!r}",
    },
    "config.expected_seconds": {
        _EN: "expected a whole number of seconds, got {text!r}",
        _RU: "ожидается целое число секунд, получено {text!r}",
    },
    "config.checkout_after_checkin": {
        _EN: "must start after {checkin_range} ends: {error}",
        _RU: "должен начинаться после конца {checkin_range}: {error}",
    },
    "config.unusable_session_length": {
        _EN: "not a usable session length: {error}",
        _RU: "непригодная длина сессии: {error}",
    },
    "config.malformed_token": {
        _EN: "is malformed: expected <bot id>:<secret>",
        _RU: "искажён: ожидается <номер бота>:<секрет>",
    },
    "config.unusable_grace": {
        _EN: "not a usable grace: {error}",
        _RU: "непригодный запас окна: {error}",
    },
    # --- the schedule's refusals of a value a setting can reach: a config line's {error}
    "schedule.range_order": {
        _EN: "range start {start} must be before its end {end}",
        _RU: "начало диапазона {start} должно быть раньше конца {end}",
    },
    "schedule.checkout_after_checkin": {
        _EN: (
            "the check-out range must start after the check-in range ends: "
            "{checkout_start} is not after {checkin_end}"
        ),
        _RU: (
            "диапазон выхода должен начинаться после конца диапазона входа: "
            "{checkout_start} не позже {checkin_end}"
        ),
    },
    "schedule.session_length_not_positive": {
        _EN: "session_length must be positive, got {session_length}",
        _RU: "длина сессии должна быть положительной, получено {session_length}",
    },
    "schedule.grace_not_positive": {
        _EN: "grace must be positive, got {grace}",
        _RU: "запас окна должен быть положительным, получено {grace}",
    },
    "schedule.window_crosses_midnight": {
        _EN: "a window from {moment} with grace {grace} crosses midnight",
        _RU: "окно от {moment} при запасе {grace} переходит через полночь",
    },
}


def text(key: str, language: Language, /, **fields: object) -> str:
    """The text of ``key`` in ``language`` with its named ``fields`` filled in.

    An unknown key or a field the text names but the caller did not pass raises
    ``KeyError`` naming it: both are a programming error the tests catch, not a state
    production should paper over with a half-rendered message. ``key`` and ``language``
    are positional, so a text may name a field ``language`` (the probe's settings line).
    """
    return MESSAGES[key][language].format(**fields)


@dataclass(frozen=True)
class Message:
    """A message key with the values of its fields: a text that has no language yet.

    The use cases hand these out; whoever shows them to a person picks the language with
    ``in_language``. An unknown key is refused when the message is made, so a typo fails
    where it is written rather than when the text is first shown. The fields are a
    read-only copy: neither the caller nor a reader can change a message once made.
    """

    key: str
    fields: Mapping[str, object] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        if self.key not in MESSAGES:
            raise KeyError(self.key)
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def in_language(self, language: Language) -> str:
        """The message's text in ``language``; a field that is a message reads in it too."""
        filled = {
            name: value.in_language(language) if isinstance(value, Message) else value
            for name, value in self.fields.items()
        }
        return text(self.key, language, **filled)


def missing_translations(
    catalogue: Mapping[str, Mapping[Language, str]] = MESSAGES,
) -> list[tuple[str, Language]]:
    """Every ``(key, language)`` pair of ``catalogue`` with no text or a blank one, in order."""
    return [
        (key, language)
        for key in sorted(catalogue)
        for language in Language
        if not catalogue[key].get(language, "").strip()
    ]
