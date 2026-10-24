@bead:ht-3fs @node:infrastructure @node:application
Feature: No client dialog in the check-in photo
  The HTML Access client can show a dialog of its own over the remote desktop after the
  service cancelled its first Fullscreen offer: on 2026-10-24 the check-in photo carried
  "Fullscreen - Click OK to grant permission for full screen" over the painted desktop.
  Right before the photo the service cancels any dialog the client shows, never accepts
  one, and takes the photo only once no dialog is in the way. A dialog that will not
  close leaves no photo, and the check-in still reports its success as text. These
  scenarios drive the real browser adapter on the HTML Access fixture portal.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the check-in drives the browser client on a fixture portal whose desktop has no session

  Scenario: A successful check-in's photo shows the desktop without a client dialog
    Given the client offers Fullscreen again while the desktop is held
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message is a photo of the painted desktop without a client dialog
    And the client's Fullscreen offer was never accepted
    And the message reads "Вход выполнен"
    And the command exits with 0

  Scenario: A client dialog that cannot be dismissed leaves the check-in a text success
    Given the client offers Fullscreen again while the desktop is held, and the offer ignores Cancel
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    Then exactly one message reaches the owner
    And the message is text without a photo
    And the client's Fullscreen offer was never accepted
    And the message reads "Вход выполнен"
    And the command exits with 0
