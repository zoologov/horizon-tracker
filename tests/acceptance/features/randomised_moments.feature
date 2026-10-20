@wip @bead:ht-slm @node:application @node:domain
Feature: Randomised check-in and check-out moments (HT-003)
  The check-in moment of a working day is drawn from a range, the check-out follows a
  full day later, and both are derived from the date so the two runs agree.

  These scenarios are named by PRD HT-003, which is approved and not built yet. Until
  BEAD-06 of HT-003 lands their steps SKIP with that reason: a skip that says why is the
  honest state, a scenario that passes before the behaviour exists is not.

  Scenario: The check-in moment of a working day lies inside the check-in range
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: Two different days draw different check-in moments
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: The check-out moment is nine hours plus up to ten minutes after the check-in
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: A check-out past the end of its range is clipped to the end
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: The same date gives the same drawn moments in two separate runs
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: A run started at the range start waits until its drawn moment before the first attempt
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands

  Scenario: A dry run names the drawn moment of the day
    Given the randomised schedule of HT-003 is not built yet
    Then the scenario is skipped until HT-003 BEAD-06 lands
