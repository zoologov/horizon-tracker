@bead:ht-0jm @node:application @node:domain
Feature: Run window and retries
  A run may start only inside its window: the five minutes from the day's drawn moment.
  On Wednesday 2026-10-21 that is 07:38-07:43 for the check-in and 16:39-16:44 for the
  check-out. A failed attempt is retried inside the window and never after it.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the desktop has no session

  Scenario Outline: A failed attempt is retried inside the window
    Given the first <failures> attempts to open the desktop fail
    When the check-in runs at <start> on Wednesday 2026-10-21
    Then the desktop was opened <opens> times
    And exactly one message reaches the owner
    And the message reads "<headline>"
    And the command exits with <code>

    Examples:
      | start    | failures | opens | headline       | code |
      | 07:30:00 | 1        | 2     | Вход выполнен  | 0    |
      | 07:30:00 | 3        | 3     | Вход не удался | 1    |
      | 07:42:45 | 1        | 1     | Вход не удался | 1    |

  Scenario Outline: A run that starts after its window is skipped and reported
    Given the desktop has a session no client is attached to
    When the <run> runs at <start> on Wednesday 2026-10-21
    Then the portal was never contacted
    And exactly one message reaches the owner
    And the message reads "<headline>"
    And the message reads "Причина: прогон начался после своего окна"
    And the command exits with 0

    Examples:
      | run       | start    | headline       |
      | check-in  | 07:43:01 | Вход пропущен  |
      | check-in  | 11:00:00 | Вход пропущен  |
      | check-out | 16:44:01 | Выход пропущен |
