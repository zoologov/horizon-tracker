# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). What the
version number promises, and which change raises which part of it, is stated in
[`docs/guides/releasing.md`](docs/guides/releasing.md).

## [Unreleased]

## [1.0.1] - 2026-10-22

`1.0.1` is a patch: the morning check-in photograph changes, and the public surface does not.

### Fixed

- **Check-in photograph.** The morning check-in photographed the desktop as soon as the canvas had a size, before Windows had finished logging on, so the Telegram photo was a black screen. It now holds the desktop, then photographs the first non-blank frame of the remote surface while the session is still open. A surface that stays blank sends the text report and no photo. The time in the report stays the moment the desktop opened. Check-out still photographs the launch list.

## [1.0.0] - 2026-10-21

The first release is `1.0.0` and not `0.x`, because the service has run in production on its
host since its first deploy and its public surface (the `horizon` command, the environment
variables and the deploy contract) is already in use.

### Added

- **Morning check-in.** `horizon checkin` logs in to the portal through VMware Horizon HTML
  Access, opens the configured desktop (`HORIZON_DESKTOP`), holds it for `HT_HOLD_SECONDS`
  so that Windows logs on and the logon is recorded on the virtual machine, then
  disconnects quietly: the Windows session keeps running.
- **Evening check-out.** `horizon checkout` reconnects to the portal, logs the Windows
  session off from the desktop's menu and confirms on the broker's answer that the session
  ended.
- **Working days.** Every run asks the isdayoff.ru production calendar whether the day is a
  working day; when the calendar does not answer, Monday to Friday decides.
- **Moments drawn per date.** The check-in moment is drawn inside `HT_CHECKIN_RANGE`, and
  the check-out moment `HT_SESSION_LENGTH_MINUTES` later plus up to
  `HT_SESSION_EXTRA_MAX_MINUTES`, clipped into `HT_CHECKOUT_RANGE`. The draw is
  deterministic for a date and a seed (`HT_JITTER_SEED`), so the morning and the evening
  runs agree without shared state.
- **Telegram report.** Every run sends one report through a Telegram bot: what happened,
  when, which calendar rule decided and why, with a screenshot of the step when there is
  one. A screenshot is never taken on the login page, and no report carries a credential.
- **Language.** `HT_LANGUAGE` (`en` by default, or `ru`) picks the language of the
  notification, `horizon probe`, a dry run and a configuration error; logs stay English.
- **Diagnostics.** `horizon probe` checks the settings, the portal, the calendar and Chrome
  without logging in and prints the day's drawn moments. `--dry-run` on `checkin` and
  `checkout` prints a run's plan without touching the portal, and `--force` runs at once,
  without the wait, the window or the calendar.
- **systemd units.** `horizon-checkin.timer` and `horizon-checkout.timer` fire at the start
  of their ranges, and their oneshot services run as the `horizon` user from
  `/opt/horizon-tracker`; `deploy/bootstrap.sh` prepares a host once.
- **Deploy.** A deploy job in the GitHub Environment `horizon-vps` updates the clone on the
  host, writes `/opt/horizon-tracker/.env` (0600) from the Environment's secrets and
  variables, installs the units and ends with a `horizon probe` smoke on the host.
- **Release flow on tags.** A tag `vX.Y.Z` on `main` starts the Release workflow: it verifies
  the tag against `pyproject.toml` and `CHANGELOG.md`, runs CI on the tagged commit,
  deploys, publishes a GitHub Release with the version's `CHANGELOG.md` section as its notes
  and the wheel and the sdist as assets, and publishes the Beadloom architecture portal to
  GitHub Pages.
- **Three workflows, one per event.** `ci.yml` runs on a pull request and on a push to `main`
  (lint, types, workflow lint, tests, the architecture gate, `ci-ok`, and on a pull request the
  mutation of the domain functions it changed); `release.yml` runs on a release tag;
  `mutation.yml` runs the weekly mutation sample. Every action is pinned to a commit SHA, and
  Dependabot proposes the updates weekly.
- **One version source.** `horizon --version` prints the version `pyproject.toml` declares.

[Unreleased]: https://github.com/zoologov/horizon-tracker/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/zoologov/horizon-tracker/releases/tag/v1.0.1
[1.0.0]: https://github.com/zoologov/horizon-tracker/releases/tag/v1.0.0
