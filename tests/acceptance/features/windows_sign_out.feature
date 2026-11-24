@bead:ht-oe6 @node:horizon-playwright-client
Feature: Windows sign-out through Horizon HTML Access
  The evening adapter opens the remote desktop and uses the Windows Win+X menu and Run
  dialog to sign out, then trusts only a freshly fetched broker launch-items list for the
  confirmation. The scenario drives the real Playwright adapter against the local HTML
  Access fixture.

  Scenario: Windows Win+X sign-out is confirmed by a fresh broker list
    Given the fixture portal's desktop has a disconnected session
    When the Playwright client logs off "DEV desktop"
    Then the desktop was opened before Windows signed out
    And Windows received Start right-click, Run, "shutdown /l" and Enter in order
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker

  Scenario: An already-open Windows Run dialog is reused without Win+X
    Given the fixture portal's desktop has a disconnected session
    And the fixture Windows Run dialog is already open
    When the Playwright client logs off "DEV desktop"
    Then Windows received the existing Run field, "shutdown /l" and Enter in order
    And no Win+X mouse sequence reached Windows
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker
