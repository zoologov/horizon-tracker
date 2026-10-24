@bead:ht-bm9 @node:application @node:infrastructure @node:cli
Feature: Screenshot preview in the success notification
  A successful check-in reports with a photo of the opened desktop, and a successful
  check-out with a photo of the launch list once the session is gone. The check-in photo
  is taken after the desktop was held, while Blast is still open, and the time in the
  caption stays the moment the desktop opened. The caption is the text the run would
  otherwise send alone. A run whose photo could not be taken still reports its success,
  as text: the photo is evidence, not a condition of the run.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day

  Scenario: A successful check-in sends a screenshot of the opened desktop
    Given the desktop has no session
    And the client photographs the opened desktop
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message is the photo of the opened desktop
    And the message reads "Вход выполнен"
    And the message reads "Время: 21.10.2026 07:38:00 MSK, назначено на 07:38"
    And the message reads "Производственный календарь: isdayoff.ru"
    And the command exits with 0

  Scenario: A successful check-in's screenshot is taken after the desktop was held
    Given the desktop has no session
    And the client photographs the opened desktop
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the opened desktop was photographed after the hold, before the disconnect
    And the message is the photo of the opened desktop
    And the message reads "Время: 21.10.2026 07:38:00 MSK, назначено на 07:38"
    And the command exits with 0

  Scenario: A check-in whose screenshot failed still reports success as text
    Given the desktop has no session
    And the client cannot photograph the opened desktop
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the portal was logged in to 2 times
    And exactly one message reaches the owner
    And the message is text without a photo
    And the message reads "Вход выполнен"
    And the message reads "Время: 21.10.2026 07:38:00 MSK, назначено на 07:38"
    And the command exits with 0

  Scenario: A successful check-out sends a screenshot of the launch list without a session
    Given the desktop has a session no client is attached to
    And the client photographs the launch list after its log off
    When the check-out runs at 16:30:00 on Wednesday 2026-10-21
    Then the desktop was logged off 1 time
    And the desktop has no session
    And exactly one message reaches the owner
    And the message is the photo of the launch list
    And the message reads "Выход выполнен"
    And the message reads "Время: 21.10.2026 16:39:00 MSK, назначено на 16:39"
    And the command exits with 0

  Scenario: A check-in the broker did not confirm sends no photo of the opened desktop
    Given the desktop has no session
    And the client photographs the opened desktop
    And the Windows session ends when the client lets go
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then the desktop was opened 3 times
    And exactly one message reaches the owner
    And the message is text without a photo
    And the message reads "Вход не удался"
    And the message reads "Причина: рабочий стол не открылся"
    And the command exits with 1

  Scenario Outline: A check-out confirmed only on its retry reports success as text
    # The first log off ends the session but the attempt is not confirmed: the retry finds
    # no session and logs nothing off, so there is no fresh photo of the list to send.
    # Neither the lost attempt's photo nor its failure screenshot goes with the success.
    Given the desktop has a session no client is attached to
    And the client photographs the launch list after its log off
    And after the first log off <loss>
    When the check-out runs at 16:30:00 on Wednesday 2026-10-21
    Then the desktop was logged off 1 time
    And the portal was logged in to 2 times
    And the desktop has no session
    And exactly one message reaches the owner
    And the message is text without a photo
    And the message reads "Выход выполнен"
    And the command exits with 0

    Examples:
      | loss                                                  |
      | the client answers that the log off was not confirmed |
      | reading the session state fails                       |
