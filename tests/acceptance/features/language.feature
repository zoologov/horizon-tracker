@bead:ht-bsc @node:domain @node:infrastructure @node:cli
Feature: Language of the notifications and the CLI output
  What a person reads -- the Telegram notification, the probe, the dry run and a
  configuration error -- comes from the message catalogue in the language HT_LANGUAGE
  names: English when it is unset or blank, Russian for "ru". Any other value is refused
  when the settings load, before anything is built. The service log is the operator's
  and stays English whatever language the owner reads.

  A line is read as Russian when it holds a Cyrillic letter and as English when it holds
  none; identifiers such as "checkin" or "(run)" stay untranslated inside a Russian line.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the desktop has no session

  Scenario Outline: A notification is rendered in the configured language
    Given HT_LANGUAGE is "<code>"
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message reads "<headline>"
    And the message reads "<time>"
    And the message reads "<calendar>"
    And every line of the message is in <language>
    And the command exits with 0

    Examples:
      | code | language | headline           | time                                               | calendar                                          |
      | ru   | Russian  | Вход выполнен      | Время: 21.10.2026 07:38:00 MSK, назначено на 07:38 | Календарь: производственный календарь isdayoff.ru |
      | en   | English  | Check-in succeeded | Time: 21.10.2026 07:38:00 MSK, planned for 07:38   | Calendar: the isdayoff.ru production calendar     |

  Scenario: The default language is English
    Given HT_LANGUAGE is not set
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    And the owner runs "horizon checkout --dry-run" at 16:30:00 on Wednesday 2026-10-21
    Then the message reads "Check-in succeeded"
    And the message reads "Time: 21.10.2026 07:38:00 MSK, planned for 07:38"
    And the message reads "Calendar: the isdayoff.ru production calendar"
    And every line of the message is in English
    And the output reads "would run now: yes (run)"
    And the output reads "steps of one attempt:"
    And every line of the output is in English
    And the command exits with 0

  Scenario: A blank HT_LANGUAGE reads as the default English
    Given HT_LANGUAGE is set to blanks only
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the message reads "Check-in succeeded"
    And every line of the message is in English
    And the command exits with 0

  Scenario: Every message key has a text in every supported language
    Given the message catalogue the service ships
    When every key is asked for in every supported language with each of its fields filled
    Then every key answers a text in every supported language
    And every Russian text holds a Russian letter
    And no English text holds a Russian letter
    And the catalogue names no missing translation

  Scenario Outline: An unknown language is refused when the settings load
    Given HT_LANGUAGE is "<code>"
    When the owner runs "horizon <command>" at 07:30:00 on Wednesday 2026-10-21
    Then the command exits with 1
    And the service log reads "configuration error: HT_LANGUAGE: expected one of en, ru, got '<code>'"
    And HT_LANGUAGE is named on 1 line of the error output
    And no adapter was built
    And the portal was never contacted
    And no message reaches the owner

    Examples:
      | code  | command           |
      | de    | checkin           |
      | RU    | probe             |
      | en-US | checkout          |
      | ру    | checkin --dry-run |

  Scenario Outline: The probe reads in the configured language
    Given HT_LANGUAGE is "<code>"
    When the owner runs "horizon probe" at 12:00:00 on Wednesday 2026-10-21
    Then the output reads "<settings>"
    And the output reads "<portal>"
    And the output reads "<schedule>"
    And every line of the output is in <language>
    And no message reaches the owner
    And the command exits with 0

    Examples:
      | code | language | settings                   | portal                     | schedule                          |
      | en   | English  | Europe/Moscow, language en | portal: ok - client        | schedule: today 07:38 / 16:39     |
      | ru   | Russian  | Europe/Moscow, язык ru     | портал: в порядке - бандлы | расписание: сегодня 07:38 / 16:39 |

  Scenario Outline: A dry run reads in the configured language
    Given HT_LANGUAGE is "<code>"
    When the owner runs "horizon checkin --dry-run" at 07:30:00 on Wednesday 2026-10-21
    Then the output reads "<verdict>"
    And the output reads "<wait>"
    And the output reads "<steps>"
    And every line of the output is in <language>
    And the portal was never contacted
    And the command exits with 0

    Examples:
      | code | language | verdict                        | wait                    | steps                 |
      | en   | English  | would run now: yes (run)       | would wait until: 07:38 | steps of one attempt: |
      | ru   | Russian  | запустился бы сейчас: да (run) | ждал бы до: 07:38       | шаги одной попытки:   |

  Scenario: The service log stays English while the owner reads Russian
    Given HT_LANGUAGE is "ru"
    And every login attempt is refused
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the message reads "Вход не удался"
    And the message reads "Причина: портал отклонил вход"
    And every line of the message is in Russian
    And the service log reads "checkin attempt 1 failed: login_rejected"
    And the service log reads "checkin run failed (login_rejected)"
    And no line of the service log is in Russian
    And the command exits with 1

  Scenario: The service log is the same whatever language the owner reads
    Given every login attempt is refused
    When a check-in runs at 07:30:00 on Wednesday 2026-10-21 for a reader of each language
    Then each reader got the message in their own language
    And every run logged the same lines, their timestamps aside

  Scenario: A configuration error reaches a Russian reader in Russian beside the English log line
    Given HT_LANGUAGE is "ru"
    And the variable HT_HOLD_SECONDS is "soon"
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the command exits with 1
    And the service log reads "configuration error: HT_HOLD_SECONDS: expected a whole number of seconds, got 'soon'"
    And the error output reads "ошибка настройки: HT_HOLD_SECONDS: ожидается целое число секунд, получено 'soon'"
    And HT_HOLD_SECONDS is named on 2 lines of the error output
    And no line of the service log is in Russian

  @bead:ht-7a0.1
  Scenario Outline: A value the schedule refuses reaches a Russian reader with its reason in Russian
    Given HT_LANGUAGE is "ru"
    And the variable <variable> is "<value>"
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the command exits with 1
    And the service log reads "configuration error: <variable>: <english>"
    And the error output reads "ошибка настройки: <variable>: <russian>"
    And no line of the service log is in Russian

    Examples:
      | variable                  | value       | english                                                                            | russian                                                                                   |
      | HT_CHECKIN_RANGE          | 08:10-07:30 | not a valid range '08:10-07:30': range start 08:10:00 must be before its end 07:30:00 | недопустимый диапазон '08:10-07:30': начало диапазона 08:10:00 должно быть раньше конца 07:30:00 |
      | HT_CHECKOUT_RANGE         | 25:00-26:00 | not a valid range '25:00-26:00': no such time of day                                | недопустимый диапазон '25:00-26:00': такого времени суток нет                             |
      | HT_SESSION_LENGTH_MINUTES | 0           | not a usable session length: session_length must be positive, got 0:00:00          | непригодная длина сессии: длина сессии должна быть положительной, получено 0:00:00        |

  Scenario: A configuration error is said once to an English reader
    Given HT_LANGUAGE is not set
    And the variable HT_HOLD_SECONDS is "soon"
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the command exits with 1
    And the service log reads "configuration error: HT_HOLD_SECONDS: expected a whole number of seconds, got 'soon'"
    And HT_HOLD_SECONDS is named on 1 line of the error output
    And no line of the error output is in Russian
