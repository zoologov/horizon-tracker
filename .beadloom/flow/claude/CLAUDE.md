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

Trunk-based development, held by GitHub once the repository is public (HT-008; the owner
applies it in BEAD-05):

- **A branch per work item** (`features/<KEY>`), **one PR** to `main`, no direct push to
  `main` for anyone, the owner included (`enforce_admins: true`).
- **`ci-ok` is the one required status check, and it is strict**: a branch is up to date with
  `main` before it merges. `ci.yml`'s `mutation-per-change` is informative and not required.
- **0 required reviews**: the owner merges their own PR; the review is the flow's `review`
  role, not GitHub's. Force-push to `main` and its deletion stay at GitHub's default,
  forbidden.
- **A release is a tag `vX.Y.Z` on `main`**, protected by two `v*` tag rulesets (a bypass
  list applies to a whole ruleset, so the two rules take two): only the owner creates one,
  nobody updates or deletes one. A tag starts `release.yml` (verify, CI gate,
  deploy, GitHub Release, portal); a merge to `main` deploys nothing.
  `docs/guides/releasing.md` is the procedure.
- **Set with** `beadloom setup-branch-protection --repo zoologov/horizon-tracker --check ci-ok`.
  `--check` is mandatory: the command's default contexts are Beadloom's own job names
  (`gate`, `tests (3.10)`, `site-build`, ...), which this repository never produces, and a
  required check that never reports makes `main` unmergeable (§6 above).
- **Measured with** `gh api repos/zoologov/horizon-tracker/branches/main/protection` and
  `gh api repos/zoologov/horizon-tracker/rulesets`.
  Measured: 2026-10-21 — protection: a PR required, `ci-ok` the one required check, `strict`,
  `enforce_admins: true`, 0 reviews, force-push and deletion forbidden; rulesets: two active
  `tag` rulesets on `refs/tags/v*`, `creation` with the admin role's bypass, and
  `update` + `deletion` + `non_fast_forward` with no bypass. The environments were read back
  the same day: `horizon-vps` and `github-pages` each admit exactly `branch main` and
  `tag v*`. A re-run of the setup command is re-measured the same way and this date moves.
  The refusal of a direct push is what `enforce_admins: true` means in that reading; it was
  not probed with a push.

### Language

The flow documents (PRD, RFC, CONTEXT, PLAN, ACTIVE, BRIEF) are written in English (`language: en`).
Code, docstrings, AS-IS documentation in `docs/` and commit messages are in English too; the language of notifications and the CLI is the runtime setting `HT_LANGUAGE` (default `en`).
