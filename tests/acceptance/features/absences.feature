@wip @node:application @node:infrastructure @node:cli
Feature: Absences entered through the bot (HT-012)
  The owner enters, lists, edits and deletes absences (a vacation, a sick leave, a day
  off) with text commands to the bot from their own chat, and the runs respect them.

  The bot scenarios run `horizon bot` over the real Telegram transport, posting to a
  recording Bot API that hands out the messages each scenario writes and then stops the
  bot. The three scenarios of the runs (BEAD-05 of HT-012, ht-fzd) are not built yet and
  SKIP with that reason: a skip that says why is the honest state, a scenario that passes
  before the behaviour exists is not.

  @bead:ht-xad @node:absence-service @node:bot-loop
  Scenario: An absence entered through the bot is confirmed with its dates and an id
    Given the owner writes "/add vacation 03.11-14.11" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the command exits with 0
    And the bot's last reply reads "Absence 1 entered: vacation from 03.11.2026 to 14.11.2026"
    And the absences file holds a vacation from 2026-11-03 to 2026-11-14 as absence 1

  @bead:ht-xad @node:bot-loop
  Scenario: An absence with a malformed date is refused with the expected format
    Given the owner writes "/add vacation 3 November" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the bot's last reply reads "Not a date '3': expected 03.11, 03.11.2026 or 2026-11-03; a range is written 03.11-14.11"
    And the absences file holds no absence

  @bead:ht-xad @node:bot-loop
  Scenario: A message from another chat is ignored
    Given the chat 1000 writes "/add vacation 03.11-14.11" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the command exits with 0
    And the bot sends no reply
    And the absences file holds no absence
    And the service log names the chat 1000 and not the text it wrote

  @bead:ht-xad @node:absence-service
  Scenario: The list names every absence with its id, kind and dates
    Given the owner writes "/add vacation 03.11-14.11" to the bot
    And the owner writes "/add dayoff 20.11" to the bot
    And the owner writes "/list" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the bot's last reply reads:
      """
      Absences entered: 2
      Absence 1: vacation from 03.11.2026 to 14.11.2026
      Absence 2: day off on 20.11.2026
      """

  @bead:ht-xad @node:absence-service
  Scenario: A deleted absence no longer stops a run
    Given the owner writes "/add vacation 03.11-14.11" to the bot
    And the owner writes "/del 1" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the bot's last reply reads "Absence 1 deleted: vacation from 03.11.2026 to 14.11.2026"
    And the absences file holds no absence
    When the check-in runs at 07:30 on Tuesday 2026-11-03
    Then the check-in opened the desktop

  @bead:ht-xad @node:absence-service
  Scenario: An edited absence keeps its id and takes the new dates
    Given the owner writes "/add vacation 03.11-14.11" to the bot
    And the owner writes "/edit 1 05.11-16.11" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the bot's last reply reads "Absence 1 changed: vacation from 05.11.2026 to 16.11.2026"
    And the absences file holds a vacation from 2026-11-05 to 2026-11-16 as absence 1

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
