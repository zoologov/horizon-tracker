@bead:ht-0jm @node:application @node:cli
Feature: Evening check-out
  At 17:00 Moscow time the service logs the Windows session of the desktop off, so the
  accounting system records the end of the working day.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day

  Scenario: Evening check-out logs the desktop off
    Given the desktop has a session no client is attached to
    When the check-out runs at 17:00:00 on Wednesday 2026-10-21
    Then the desktop was logged off
    And the desktop has no session
    And exactly one message reaches the owner
    And the message reads "Выход выполнен"
    And the command exits with 0

  Scenario: Evening check-out on an already logged-off desktop reports it and stops
    Given the desktop has no session
    When the check-out runs at 17:00:00 on Wednesday 2026-10-21
    Then the desktop was never logged off
    And the portal was logged in to 1 time
    And exactly one message reaches the owner
    And the message reads "Выход пропущен"
    And the message reads "Причина: сессии на столе уже нет, выходить не из чего"
    And the command exits with 0
