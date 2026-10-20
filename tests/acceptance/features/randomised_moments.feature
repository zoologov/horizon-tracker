@bead:ht-slm @node:cli @node:application @node:domain
Feature: Randomised check-in and check-out moments (HT-003)
  The check-in moment of a working day is drawn from a range, the check-out follows a
  full day later, and both are derived from the date so the morning and the evening run
  agree. The timers fire at the starts of the ranges and each run waits for its moment.

  The moments named below are the ones the seed of the Background draws; an oracle of the
  RFC formula that imports nothing from the project computed them.

  Background:
    Given the service is configured for the desktop "DEV desktop"
    And the calendar marks the day as a working day
    And the check-in range is 07:30-08:10 and the check-out range is 16:30-17:10
    And a working day lasts 540 minutes plus up to 10 minutes
    And the moments are drawn with the seed "horizon-acceptance-6"

  Scenario: The check-in moment of a working day lies inside the check-in range
    Given the desktop has no session
    When the check-in runs at 07:30:00 on every weekday from Monday 2026-10-19 to Friday 2026-11-13
    Then every check-in succeeded at the moment it was planned for
    And every planned check-in lies between 07:30 and 08:10
    And the planned check-ins reach both 07:30 and 08:10

  Scenario: Two different days draw different check-in moments
    Given the desktop has no session
    When the check-in runs at 07:30:00 on Wednesday 2026-10-21
    And the check-in runs at 07:30:00 on Thursday 2026-10-22
    Then the check-in of 2026-10-21 was planned for 07:38
    And the check-in of 2026-10-22 was planned for 07:37
    And the two days were planned for different check-in moments

  Scenario: The check-out moment is nine hours plus up to ten minutes after the check-in
    When the owner runs "horizon probe" at 12:00:00 on every day from Monday 2026-10-19 to Sunday 2026-11-15
    Then the schedule of Wednesday 2026-10-21 reads "today 07:38 / 16:39"
    And on every day the check-out is at least 540 minutes after the check-in
    And on every day with a check-in at 08:00 or earlier the check-out is 540 to 550 minutes after it
    And the minutes over 540 reach both 0 and 10
    And every check-out lies between 16:30 and 17:10

  Scenario: A check-out past the end of its range is clipped to the end
    # 08:08 plus 540 minutes plus the 4 extra minutes this day draws is 17:12.
    Given the desktop has a session no client is attached to
    When the check-out runs at 16:30:00 on Thursday 2026-10-29
    And the owner runs "horizon checkout --dry-run" at 17:30:00 on Thursday 2026-10-29
    Then the message reads "Выход выполнен"
    And the message reads "Время: 29.10.2026 17:10:00 MSK, назначено на 17:10"
    And the output reads "schedule: today 08:08 / 17:10"

  Scenario: The same date gives the same drawn moments in two separate runs
    When the owner runs "horizon checkin --dry-run" at 07:30:00 on Wednesday 2026-10-21 in a process of its own
    And the owner runs "horizon checkout --dry-run" at 16:30:00 on Wednesday 2026-10-21 in a process of its own
    Then both processes exit with 0 and read "schedule: today 07:38 / 16:39"
    And the check-in process reads "would wait until: 07:38"
    And the check-out process reads "would wait until: 16:39"

  Scenario Outline: A run started at the range start waits until its drawn moment before the first attempt
    Given the desktop has <session>
    When the <run> runs at <start> on Wednesday 2026-10-21
    Then the run slept <wait> seconds before anything else
    And the portal was first contacted at <moment>:00
    And exactly one message reaches the owner
    And the message reads "<headline>"
    And the message reads "Время: 21.10.2026 <moment>:00 MSK, назначено на <moment>"
    And the command exits with 0

    Examples:
      | run       | start    | session                                | wait | moment | headline       |
      | check-in  | 07:30:00 | no session                             | 480  | 07:38  | Вход выполнен  |
      | check-out | 16:30:00 | a session no client is attached to     | 540  | 16:39  | Выход выполнен |

  Scenario Outline: A dry run names the drawn moment of the day
    When the owner runs "horizon <run> --dry-run" at <start> on Wednesday 2026-10-21
    Then the output reads "would run now: yes (run)"
    And the output reads "would wait until: <moment>"
    And the output reads "schedule: today 07:38 / 16:39"
    And the run never slept
    And the portal was never contacted
    And no message reaches the owner
    And the command exits with 0

    Examples:
      | run      | start    | moment |
      | checkin  | 07:30:00 | 07:38  |
      | checkout | 16:30:00 | 16:39  |
