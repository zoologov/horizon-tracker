---

## Project layer — horizon-tracker's own rules (`.beadloom/flow/claude/CLAUDE.md`)

Everything above is the composition of the beadloom core and the overlays `.beadloom/flow.yml` selects.
Everything below is true of this repository only, survives a beadloom upgrade and
is never distributed.

### Project facts (authoritative; the auto-region §0.1 is coarser)

- **What it is.** A service on a VPS (Ubuntu, systemd timers, the configured time zone, e.g. `Europe/Moscow`) which in the morning
  opens a desktop (e.g. "DEV desktop") in VMware Horizon through HTML Access and quietly
  disconnects, and in the evening reconnects and performs a full Log Off. Working days come
  from a production calendar (isdayoff.ru) with a fallback to "Mon–Fri".
- **Stack.** Python 3.12 (`python3.12` is on the VPS), `uv`, Playwright over the system
  Chrome `/usr/bin/google-chrome` (already present on the VPS), `click`, `httpx`. Tests pytest,
  ruff, mypy --strict.
- **Neighbourhood.** A neighbouring service lives on the same host (in the neighbour's directory, under its own user). This service is
  a separate system user `horizon` with the home `/opt/horizon-tracker`; nothing of the
  neighbour is touched. Notifications go to the owner's private chat from the notification bot
  (its token), not in the neighbour's voice; the neighbour takes no part in the code.
- **bd.** The core above is written for bd 1.0.4. This environment has bd 1.3.1
  (`gastownhall/beads`, formerly `steveyegge/beads`). The core's flags and caveats about 1.0.4
  — verify against `bd <cmd> --help`, do not take them on trust.

### Horizon semantics — do not confuse

- **Disconnect** — close the client; the session on the VM lives on, the Windows user is not
  logged off. This is the morning's "quiet disconnect".
- **Log off** — end the Windows session. This is the evening's "check-out".
- A "check-in" is not authentication on the portal but an open Blast connection and a
  rendered desktop: the attendance record hangs on the Windows logon, not on the web client.

### Clean Architecture and cohesion-driven — standing rules

- **Direction of dependencies:** `cli` (composition root) → `infrastructure` (adapters)
  → `application` (use cases) → `domain`. Never the other way round. Ports (Protocol) are
  declared by `domain`, adapters implement them. The rule `architecture-layers` in
  `.beadloom/_graph/rules.yml` holds this, `beadloom lint --strict` reports a
  crossing.
- **Cohesion-driven:** every module and class has ONE nameable responsibility, and it is
  named in the first line of the docstring. `dev` names it before the code; `review` checks it both
  ways: no second responsibility in a module, and no single one smeared over several.
- **A pure core without I/O:** `domain` knows neither the browser, nor the network, nor the wall clock —
  time arrives as an argument. Everything that takes a decision (windows, attempts, the calendar
  verdict, the session state) lives there and is tested first (TDD).
- **A test on a fake proves the fake's contract.** The Playwright adapter is checked against a
  local copy of the HTML Access markup (a fixture from the real client bundle), and
  the only runs against the live portal happen on the VPS (`horizon probe`, the timers).

### Secrets and the live portal

- The AD account, the bot token and the chat id — only in the GitHub Environment `horizon-vps` and in
  `/opt/horizon-tracker/.env` (0600, written by the deploy). They are never in the repository.
- The password never reaches a log, a bead comment or an error screenshot (the screenshot is taken
  after leaving the login page or with the field masked).
- From CI and from the agent's sandbox, do NOT log in to the portal. Only
  unauthenticated access to the client bundle is allowed, to take the selectors.

### Git — what actually holds `main` here

The core above claims that `main` is branch-protected. For this repository that is not
measured: for a neighbouring service on the same host the same GitHub plan answered `403 Upgrade to Pro`. Until measured,
treat CI on a PR as **informative** and `main` as held by discipline: a branch per
work item, one PR, re-verification of the gates on the final tree. The measurement:
`gh api repos/:owner/:repo/branches/main/protection`.

### Language

The flow documents (PRD, RFC, CONTEXT, PLAN, ACTIVE, BRIEF) are written in English (`language: en`).
Code, docstrings, AS-IS documentation in `docs/` and commit messages are in English too; the language of notifications and the CLI is the runtime setting `HT_LANGUAGE` (default `en`).
