@bead:ht-axc @node:infrastructure @node:domain @node:cli
Feature: Notifications
  Every run sends one message to the owner's Telegram chat through the the notification bot bot. A
  failure carries its reason and a screenshot; no message ever carries a credential.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the desktop has no session

  Scenario: A failed run sends the reason and a screenshot
    Given every attempt to open the desktop fails and the adapter captures the page
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message is a photo of the captured page
    And the message reads "Вход не удался"
    And the message reads "Причина: рабочий стол не открылся"
    And the command exits with 1

  Scenario Outline: A notification never contains the password
    Given the check-in <goes>
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And nothing sent to Telegram contains the password or the account name
    And the service log does not contain the password or the account name

    Examples:
      | goes                                       |
      | succeeds                                   |
      | is refused at the login page               |
      | fails with an error quoting the password   |
