@node:application @node:infrastructure @node:cli
Feature: Absences entered through the bot (HT-012)
  The owner enters, lists, edits and deletes absences (a vacation, a sick leave, a day
  off) with text commands to the bot from their own chat, and the runs respect them.

  The bot scenarios run `horizon bot` over the real Telegram transport, posting to a
  recording Bot API that hands out the messages each scenario writes and then stops the
  bot. The scenarios of the runs find the absence in the absences file, as the bot leaves
  it, and run the check-in or the check-out over it: a day an absence covers is skipped
  before the production calendar is asked, the morning says so once and the evening says
  nothing.

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
      Current and upcoming absences: 2
      Absence 1: vacation from 03.11.2026 to 14.11.2026
      Absence 2: day off on 20.11.2026
      """

  @bead:ht-t28.1 @node:absence-service
  Scenario: The list leaves out the finished absences and counts them
    Given the owner writes "/add dayoff 19.10.2026" to the bot
    And the owner writes "/add vacation 03.11-14.11" to the bot
    And the owner writes "/list" to the bot
    When the bot runs at 12:00 on Saturday 2026-10-24
    Then the bot's last reply reads:
      """
      Current and upcoming absences: 1
      Absence 2: vacation from 03.11.2026 to 14.11.2026
      Finished absences, not listed: 1
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

  @bead:ht-fzd @node:windowed-run
  Scenario: A morning run on a day of vacation is skipped with the kind named
    Given a vacation from 2026-11-03 to 2026-11-14 is entered as absence 1
    When the check-in runs at 07:30 on Tuesday 2026-11-03
    Then the portal was never contacted
    And the production calendar was never asked
    And exactly one message reaches the owner
    And the message reads "Вход пропущен"
    And the message reads "Причина: отпуск (03.11–14.11)"
    And no line of the message starts with "Производственный календарь"
    And no line of the message starts with "Время:"
    And the command exits with 0

  # The owner's ruling: a skipped day is reported once, in the morning; the evening is
  # silent whether an absence or the production calendar skipped the day.
  @bead:ht-fzd @node:windowed-run @node:cli
  Scenario Outline: An evening run on a skipped day sends nothing
    Given <the skipped day>
    When the check-out runs at 16:30 on <weekday> <date>
    Then the portal was never contacted
    And no message reaches the owner
    And the command exits with 0

    Examples:
      | the skipped day                                                   | weekday   | date       |
      | a vacation from 2026-11-03 to 2026-11-14 is entered as absence 1 | Tuesday   | 2026-11-03 |
      | the calendar marks the day as a day off                           | Wednesday | 2026-11-04 |

  @bead:ht-fzd @node:windowed-run
  Scenario: A day after the absence ends is a working day again
    Given a vacation from 2026-11-03 to 2026-11-10 is entered as absence 1
    And the calendar marks the day as a working day
    When the check-in runs at 07:30 on Wednesday 2026-11-11
    Then the check-in opened the desktop
    And exactly one message reaches the owner
    And the message reads "Вход выполнен"
    And the command exits with 0
