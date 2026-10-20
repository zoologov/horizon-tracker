# PRD: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Status:** Approved
> **Created:** 2026-10-20

---

## Problem

Working-time accounting at the workplace is tied to the VMware Horizon session: the check-in is
recorded by the Windows logon on a virtual desktop («DEV desktop» in the example configuration), the check-out by the end of that
session. Today both events are done by hand from the Horizon client on macOS. A manual action
at 07:55 and at 17:00 on every working day is either forgotten or happens late, and the
accounting drifts away from the actual schedule.

Portal access: `https://horizon.example.com` → a redirect to the web client at
`https://horizon.example.com/portal/webclient/` (Horizon HTML Access 2312). Login by
AD username and password, no second factor. The selection page shows two desktops: «Base
desktop» and «DEV desktop»; the second one is needed.

## Impact

One person is affected — the owner of the account. Without automation the check-in and check-out times
depend on the owner's attention rather than on the schedule; every missed event is a
discrepancy in the accounting that is later explained by hand. There is a running VPS (Ubuntu,
24/7, already hosting a neighbouring service), and `uv` and a system Chrome are already installed on it, so
the cost of hosting the service is close to zero.

## Goals

- [ ] On every working day by the production calendar the check-in (the configured desktop
      open, the Windows logon completed) happens at 07:55 in the configured time zone, with a tolerance of at most
      5 minutes across retries, after which the session is disconnected rather than
      logged off.
- [ ] On every working day at 17:00 in the configured time zone a full check-out (log off) from the desktop happens,
      with the same tolerance.
- [ ] For every run — successful or not — one Telegram message from the notification bot reaches
      the owner's private chat no later than a minute after the run
      finishes; on an error the message carries the reason and a screenshot.
- [ ] Weekends and holidays by the calendar are skipped with an "a day off, skipped" message;
      when the calendar is unreachable the Monday–Friday rule applies, and that is named in
      the message.
- [ ] A run that could not start inside its window (for example, the VPS was switched off)
      is not performed later but reports a skip.
- [ ] The service is deployed to the VPS automatically: a push to `main` installs the code, writes
      the secrets from the GitHub Environment to `/opt/horizon-tracker/.env` and restarts the
      timers. There are no secrets in the repository.
- [ ] `horizon probe` and `horizon checkin --dry-run` make it possible to check that the portal
      is reachable and to walk the scenario without logging in.

## Non-goals

- A second authentication factor (RSA, OTP, SAML) — the portal has none, and no support is
  planned.
- Changes to the neighbouring service on the same host: it takes no part in the code; only the notification bot's token is used.
- Several accounts or several desktops at once; the desktop name is a
  configuration parameter, but there is one run.
- An agent inside the Windows machine: everything is done from outside through HTML Access.
- Keeping the session "alive" during the day: in the morning only the check-in and a disconnect.
- A graphical interface and control through Telegram commands (a possible continuation,
  not this epic).

## User Stories

### US-1: Morning check-in
**As** the owner of the account, **I want** the configured desktop to open at 07:55 in the configured time zone
and the Windows logon to complete, after which the client disconnects, **so that** the accounting
system records the check-in on time and the session stays alive until the evening.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [ ] Scenario: `Morning check-in opens the desktop and disconnects`
- [ ] Scenario: `Morning check-in reports success with the recorded time`

### US-2: Evening check-out
**As** the owner of the account, **I want** the service to reconnect to the
desktop at 17:00 in the configured time zone and perform a Log Off, **so that** the accounting system records the check-out at 17:00.

**Acceptance criteria**:
- [ ] Scenario: `Evening check-out logs the desktop off`
- [ ] Scenario: `Evening check-out on an already logged-off desktop reports it and stops`

### US-3: Production calendar
**As** the owner, **I want** runs to be skipped on weekends and holidays by the production
calendar, **so that** there are no check-ins on non-working days.

**Acceptance criteria**:
- [ ] Scenario: `A day the calendar marks as a holiday is skipped with a notice`
- [ ] Scenario: `When the calendar is unreachable the weekday rule decides and says so`

### US-4: Notifications
**As** the owner, **I want** to receive one Telegram message per run with the outcome, the
time and, on an error, the reason and a screenshot, **so that** I know the state without looking
at the server.

**Acceptance criteria**:
- [ ] Scenario: `A failed run sends the reason and a screenshot`
- [ ] Scenario: `A notification never contains the password`

### US-5: Window and retries
**As** the owner, **I want** a failed run to be retried inside its window and not performed outside
the window, **so that** the check-in does not happen at 11 in the morning after the VPS was down.

**Acceptance criteria**:
- [ ] Scenario: `A failed attempt is retried inside the window`
- [ ] Scenario: `A run that starts after its window is skipped and reported`

### US-6: A check without logging in
**As** the owner, **I want** the `horizon probe` and `--dry-run` commands, **so that** I can
check the portal and the configuration on the VPS without creating a session.

**Acceptance criteria**:
- [ ] Scenario: `Probe reports the portal version without logging in`
- [ ] Scenario: `A dry run walks the plan and performs no login`

### US-7: Deploy and secrets
**As** the owner, **I want** a push to `main` to deploy the service to the VPS and refresh the
secrets from the GitHub Environment, **so that** no secret lives in the repository and
a release needs no manual steps.

**Acceptance criteria**:
- [ ] The deploy workflow installs the code into `/opt/horizon-tracker`, writes `.env` (0600) and
      restarts the timers — non-behavioural: verified by running the workflow against the VPS, not
      by a scenario in the suite.
- [ ] `git grep` over the repository finds neither the password nor the token — non-behavioural:
      a property of the repository, not of behaviour.

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [ ] Scenario: `Morning check-in opens the desktop and disconnects`
- [ ] Scenario: `Morning check-in reports success with the recorded time`
- [ ] Scenario: `Evening check-out logs the desktop off`
- [ ] Scenario: `Evening check-out on an already logged-off desktop reports it and stops`
- [ ] Scenario: `A day the calendar marks as a holiday is skipped with a notice`
- [ ] Scenario: `When the calendar is unreachable the weekday rule decides and says so`
- [ ] Scenario: `A failed run sends the reason and a screenshot`
- [ ] Scenario: `A notification never contains the password`
- [ ] Scenario: `A failed attempt is retried inside the window`
- [ ] Scenario: `A run that starts after its window is skipped and reported`
- [ ] Scenario: `Probe reports the portal version without logging in`
- [ ] Scenario: `A dry run walks the plan and performs no login`

**Non-behavioural criteria** stay checkboxes and are labelled, so the absence of a scenario is
a stated decision rather than a gap:

- [ ] The deploy workflow deploys the service and the secrets to the VPS — non-behavioural: observed
      only by running the workflow against the live VPS, the suite does not hold it.
- [ ] There are no secrets in the repository — non-behavioural: a property of the tree, checked by
      `git grep` and GitHub secret scanning.
- [ ] The first live check-in and check-out are confirmed by the owner from the Horizon journal or from the accounting
      system — non-behavioural: the observer is outside our system.
