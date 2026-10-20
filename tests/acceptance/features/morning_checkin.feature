@bead:ht-0jm @node:application @node:cli
Feature: Morning check-in
  At the day's drawn check-in moment, between 07:30 and 08:10 Moscow time, the service
  opens the desktop until Windows has logged on, then lets the client go and leaves the
  Windows session running until the evening. Its timer fires at 07:30, the start of the
  range; on Wednesday 2026-10-21 the drawn moment is 07:38.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day

  Scenario: Morning check-in opens the desktop and disconnects
    Given the desktop has no session
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the desktop was opened and then disconnected
    And the desktop was never logged off
    And the Windows session of the desktop is left running without a client
    And the command exits with 0

  Scenario: Morning check-in reports success with the recorded time
    Given the desktop has no session
    And the desktop is held open for 120 seconds
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message reads "Вход выполнен"
    And the message reads "Время: 21.10.2026 07:38:00 MSK, назначено на 07:38"
    And the message reads "Календарь: производственный календарь isdayoff.ru"
