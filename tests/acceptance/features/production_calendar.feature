@bead:ht-0x2 @node:domain @node:application
Feature: Production calendar
  Runs happen on working days of the Russian production calendar. When the calendar
  cannot be asked, Monday to Friday counts as working, and the message says so.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the desktop has no session

  Scenario: A day the calendar marks as a holiday is skipped with a notice
    Given the calendar marks the day as a day off
    When the check-in runs at 07:30:00 on Wednesday 2026-11-04
    Then the portal was never contacted
    And exactly one message reaches the owner
    And the message reads "Вход пропущен"
    And the message reads "Причина: выходной"
    And the message reads "Производственный календарь: isdayoff.ru"
    And the command exits with 0

  Scenario Outline: When the calendar is unreachable the weekday rule decides and says so
    Given the calendar cannot be reached
    When the check-in runs at 07:30:00 on <weekday> <date>
    Then the message reads "<headline>"
    And the message reads "Производственный календарь: недоступен, решило правило Пн–Пт"
    And the portal was logged in to <logins> times

    Examples:
      | weekday   | date       | headline      | logins |
      | Wednesday | 2026-10-21 | Вход выполнен | 2      |
      | Saturday  | 2026-10-24 | Вход пропущен | 0      |

  # PRD HT-012 US-4: a day the calendar marks non-working is skipped for the day itself,
  # so the notice states no time and no drawn moment, only the calendar and the reason.
  @bead:ht-4um
  Scenario: A skipped non-working day is reported without a time line
    Given the calendar marks the day as a day off
    When the check-in runs at 07:30:00 on Saturday 2026-10-24
    Then the portal was never contacted
    And exactly one message reaches the owner
    And the message reads "Вход пропущен"
    And the message reads "Производственный календарь: isdayoff.ru"
    And the message reads "Причина: выходной"
    And no line of the message starts with "Время:"
    And the command exits with 0
