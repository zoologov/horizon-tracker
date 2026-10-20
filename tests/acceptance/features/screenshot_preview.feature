@wip @bead:ht-bm9 @node:application @node:infrastructure
Feature: Screenshot preview in the success notification (HT-004)
  A successful check-in and check-out send a screenshot beside the text.

  These scenarios are named by PRD HT-004, which is approved and not built yet. Until
  BEAD-03 of HT-004 lands their steps SKIP with that reason: a skip that says why is the
  honest state, a scenario that passes before the behaviour exists is not.

  Scenario: A successful check-in sends a screenshot of the opened desktop
    Given the screenshot preview of HT-004 is not built yet
    Then the scenario is skipped until HT-004 BEAD-03 lands

  Scenario: A check-in whose screenshot failed still reports success as text
    Given the screenshot preview of HT-004 is not built yet
    Then the scenario is skipped until HT-004 BEAD-03 lands

  Scenario: A successful check-out sends a screenshot of the launch list without a session
    Given the screenshot preview of HT-004 is not built yet
    Then the scenario is skipped until HT-004 BEAD-03 lands
