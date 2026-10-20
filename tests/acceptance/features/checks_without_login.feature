@bead:ht-oqx @node:cli @node:application
Feature: Checks without logging in
  The owner can ask whether a run could go ahead, and what it would do, without the
  service ever logging in to the portal.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the desktop has a session no client is attached to

  Scenario: Probe reports the portal version without logging in
    Given the portal serves the client bundle "app-htmlaccess.fake-2312.js"
    And the installed Chrome reports the version "131.0.6778.85"
    When the owner runs "horizon probe" at 12:00:00 on Wednesday 2026-10-21
    Then the output reads "portal: ok - client bundles: app-htmlaccess.fake-2312.js"
    And the output reads "chrome: ok - Chrome 131.0.6778.85 started from"
    And the output reads "schedule: today 07:38 / 16:39"
    And the portal was asked for its client bundles, Chrome for its version, and nothing else
    And no message reaches the owner
    And the command exits with 0

  Scenario Outline: A dry run walks the plan and performs no login
    When the owner runs "horizon <run> --dry-run" at <start> on Wednesday 2026-10-21
    Then the output reads "dry run: <run>"
    And the output reads "would run now: yes (run)"
    And the output reads "1. log in to the Horizon portal"
    And the output reads "<step>"
    And the portal was never contacted
    And no message reaches the owner
    And the command exits with 0

    Examples:
      | run      | start    | step                                    |
      | checkin  | 07:30:00 | hold the desktop open for 120 s         |
      | checkout | 16:30:00 | log off from the tile menu              |
