@wip @node:application @node:infrastructure @node:cli
Feature: Absences entered through the bot (HT-012)
  The owner enters, lists, edits and deletes absences (a vacation, a sick leave, a day
  off) with text commands to the bot from their own chat, and the runs respect them.

  These scenarios are named by PRD HT-012, which is approved and not built yet. Until
  BEAD-05 (the runs) and BEAD-07 (the bot) of HT-012 land, their steps SKIP with that
  reason: a skip that says why is the honest state, a scenario that passes before the
  behaviour exists is not.

  @bead:ht-xad
  Scenario: An absence entered through the bot is confirmed with its dates and an id
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-xad
  Scenario: An absence with a malformed date is refused with the expected format
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-xad
  Scenario: A message from another chat is ignored
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-xad
  Scenario: The list names every absence with its id, kind and dates
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-xad
  Scenario: A deleted absence no longer stops a run
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-xad
  Scenario: An edited absence keeps its id and takes the new dates
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-fzd
  Scenario: A morning run on a day of vacation is skipped with the kind named
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-fzd
  Scenario: An evening run on a skipped day sends nothing
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it

  @bead:ht-fzd
  Scenario: A day after the absence ends is a working day again
    Given the absences of HT-012 are not built yet
    Then the scenario is skipped until HT-012 builds it
