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
    And the fixture Windows Run dialog is already open at the v1.1.6 production geometry
    And the fixture offers Fullscreen asynchronously over the fresh broker list
    When the Playwright client logs off "DEV desktop"
    Then Windows received the existing Run field, "shutdown /l" and Enter in order
    And no Win+X mouse sequence reached Windows
    And the fresh-list Fullscreen offer was cancelled without OK
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker

  Scenario: Fullscreen intercepting a fresh-list menu click is cancelled before retry
    Given the fixture portal's desktop has a disconnected session
    And the fixture Windows Run dialog is already open at the v1.1.6 production geometry
    And the fixture offers Fullscreen beyond the old fresh-list observation window
    When the Playwright client logs off "DEV desktop"
    Then the blocked fresh-list overflow click was retried after Cancel without OK
    And Windows received the existing Run field, "shutdown /l" and Enter in order
    And Windows received Enter exactly once
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker

  Scenario: Fullscreen arising in Run input gaps is cancelled before Windows input
    Given the fixture portal's desktop has a disconnected session
    And the fixture Windows Run dialog is already open at the v1.1.6 production geometry
    And the fixture offers Fullscreen during the post-Run wait
    And the fixture offers Fullscreen during the pre-Enter screenshot
    When the Playwright client logs off "DEV desktop"
    Then both gap Fullscreen offers were cancelled without OK
    And Windows received the existing Run field, "shutdown /l" and Enter in order
    And Windows received Enter exactly once
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker

  Scenario: Checkout grants a delayed initial Fullscreen permission once before Windows input
    Given the fixture portal's desktop has a disconnected session
    And the fixture delays its initial Fullscreen permission
    And the fixture offers Fullscreen during the post-Run wait
    When the Playwright client logs off "DEV desktop"
    Then the initial Fullscreen permission was granted once before Start and Run input
    And the later Fullscreen offer was cancelled without another OK
    And Windows received Start right-click, Run, "shutdown /l" and Enter in order
    And Windows received Enter exactly once
    And no kill-session command reached the broker
    And the desktop has no session on the fixture broker
