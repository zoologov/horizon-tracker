# RFC: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Status:** Draft
> **Created:** 2026-10-20

---

## Overview

A service on the VPS that, from systemd timers at 07:55 and 17:00 in the configured time zone, drives the web client
VMware Horizon HTML Access 2312 through Playwright over the system Chrome: in the morning it opens
the configured desktop until the Windows logon has completed and disconnects, in the evening it performs
Log Off from the desktop menu. The decisions (is it a working day, is it inside the window, whether to retry,
what to report) are taken by a pure core without I/O; the browser, the isdayoff.ru calendar and Telegram
live in adapters behind ports. The deploy is GitHub Actions on a push to `main`, modelled on
the host's existing bootstrap for a neighbouring service on the same VPS.

## Motivation

### Problem
The check-in and check-out are done by hand from the macOS client and do not match the schedule. The only
fact the accounting system observes is the Windows logon and logoff on the VM, so the "check-in" must
be an open Blast connection, not an authentication on the portal.

### Solution
The headless browser walks the same path as a person: `#/home` → login → `#/launchitems` →
the desktop tile → `#/desktop` with an open Blast. For the check-out the path is shorter: on
`#/launchitems` the tile has a context menu with a Log Off button, which sends
`kill-session` to the broker without opening the desktop. All the selectors below were taken from the client bundle
`app-htmlaccess.4eb7424a56fc03317f06.js`, not guessed.

## Technical Context

### Constraints
- Python 3.12 (`python3.12` on the VPS), `uv`, Playwright 1.47+ over `/usr/bin/google-chrome`
  (already on the VPS; no separate browser is downloaded). See the STACK section of CLAUDE.md.
- The configured time zone (`Europe/Moscow` in the example, which has no DST changes); time reaches the domain
  as an argument, `zoneinfo` in the clock adapter.
- Dependency direction `cli → infrastructure → application → domain`, the ports are declared by
  `domain`; the rule `architecture-layers` in `.beadloom/_graph/rules.yml`.
- No logging into the portal from CI or the sandbox. The Playwright adapter is tested on a local
  markup fixture with the same ids; a live run only on the VPS.
- Secrets only in the GitHub Environment `horizon-vps` and in `/opt/horizon-tracker/.env`.
- A neighbouring service already lives on the VPS (its own directory, user and systemd unit). A separate
  user `horizon`, home `/opt/horizon-tracker`, the neighbour is not touched.

### Affected Areas
The whole tree `src/horizon_tracker/` — right now an empty skeleton, so there are no constraints
from surrounding code, apart from the graph rules and the project layer of CLAUDE.md.

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/ --section` (and again over
> `src/horizon_tracker/cli.py`, the same answer), 2026-10-20, an explicit run of the explore role
> **Seed:** none — no name the target reaches performs a declared effect under rule
> `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 no-seed, 2 unresolved-terminator-name (the run of 2026-10-20 over the empty
> skeleton: the tree holds not a single call with an effect, so co-writers and callers are
> not derived rather than empty)

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row: no seed found, no node named |
| callers | — | no site found | — | no | no row: no seed found, no node named |
| branches | cli | `main`: 1 branch(es), 0 exit form(s), over every call | none | yes | the only function in the tree; the epic adds the `checkin`, `checkout`, `probe` commands to it |
| declared (greenfield) | domain | no sites: the package is empty, `src/horizon_tracker/domain/__init__.py` | none | yes | the epic creates the core: windows, the calendar verdict, the session state, the ports |
| declared (greenfield) | application | no sites: the package is empty, `src/horizon_tracker/application/__init__.py` | none | yes | the epic creates the use cases `checkin`, `checkout`, `probe` |
| declared (greenfield) | infrastructure | no sites: the package is empty, `src/horizon_tracker/infrastructure/__init__.py` | none | yes | the epic creates the adapters: Playwright, isdayoff, Telegram, config, clock |
| declared (greenfield) | horizon-tracker | `deploy/`, `.github/workflows/` — outside `src/`, the derivation does not read them | none | yes | the systemd units, the bootstrap and the workflows belong to the root service |

The `declared (greenfield)` rows are a person's decision, not the derivation's output: over an empty
tree no rule finds a seed, and that is recorded above. Once code exists, the axes of
every following work item are derived afresh.

## Proposed Solution

### Approach

A hexagon of four graph nodes. The pure core decides, the adapters execute, the use case
binds, the CLI assembles.

**Domain (`src/horizon_tracker/domain/`)** — no I/O:

| Module | One responsibility |
|--------|----------------------|
| `schedule.py` | the run window and the decision "perform / retry / skip as late": `Window`, `RunKind` (CHECKIN, CHECKOUT), `decide(now, window, verdict) -> Decision`, `RetryPolicy` |
| `calendar.py` | the working-day verdict: `WorkingDayVerdict(is_working, source=CALENDAR \| WEEKDAY_FALLBACK)`, the Mon–Fri rule as the fallback |
| `session.py` | the Horizon session states and the allowed transitions: `NO_SESSION`, `CONNECTED`, `DISCONNECTED`; what "the check-in happened" and "the check-out happened" mean |
| `report.py` | the run report as a value (`RunReport`) and its text for the notification; by construction the report has no password field |
| `ports.py` | Protocols: `HorizonClient`, `WorkingDayCalendar`, `Notifier`, `Clock`, `ArtifactStore` |

**Application (`src/horizon_tracker/application/`)**:

| Module | One responsibility |
|--------|----------------------|
| `checkin.py` | the morning run: verdict → decision → attempts inside the window: login, open the desktop, wait for the connection, hold for `hold_seconds`, disconnect → report → notification |
| `checkout.py` | the evening run: verdict → decision → login → desktop state → Log Off from the tile menu → confirmation → report → notification; a desktop without a session = "already logged off", report and stop |
| `probe.py` | a check without logging in: the portal version and reachability, the configuration in place; `--dry-run` walks the plan and names the steps without calling login |

**Infrastructure (`src/horizon_tracker/infrastructure/`)**:

| Module | One responsibility |
|--------|----------------------|
| `horizon_playwright.py` | `HorizonClient` over Playwright and the system Chrome (selectors below); a screenshot on error only away from the login page |
| `isdayoff.py` | `WorkingDayCalendar` over `https://isdayoff.ru/YYYYMMDD` (0 working, 1 day off, 2 shortened = working), 5 s timeout, `None` on failure |
| `telegram.py` | `Notifier` over the Bot API `sendMessage` / `sendPhoto` with the notification bot's token into `TELEGRAM_CHAT_ID` |
| `config.py` | `Settings` from environment variables, validated and with no defaults for secrets |
| `clock.py` | `Clock` with `zoneinfo` for the configured time zone (`Europe/Moscow`) |
| `artifacts.py` | the directory of screenshots and run logs, with rotation |

**CLI (`src/horizon_tracker/cli.py`)** — composition root: `horizon checkin|checkout
[--dry-run] [--force]`, `horizon probe`. `--force` ignores the window and the calendar for a
manual run from the VPS; `--dry-run` does not call login. Exit code 0 on success and on a
deliberate skip, 1 on failure; systemd tells `failed` apart by it.

### The path through the web client (selectors taken from the bundle)

| Step | Where | Selector / signal |
|-----|-----|-------------------|
| Open the portal | `https://horizon.example.com/portal/webclient/#/home` | client routes: `home`, `launchitems`, `desktop`, `warning` |
| Login | `#/home` | `#username`, `#password`, `#loginButton` (`#cancelLoginBtn` to cancel); an error — a dialog with `#okDialogBtn` |
| Desktop selection | `#/launchitems` | the tile `li[title="DEV desktop"]`, the launch button `#launch-<id>` inside it; the name is the `HORIZON_DESKTOP` parameter |
| The tile's context menu | `#/launchitems`, the «…» button | `#menu-item-launch-btn`, `#menu-item-logoff-btn`, `#menu-item-reset-btn`; Log Off is confirmed by the `LOGOFF_DESKTOP_T/M` dialog → `#okDialogBtn` |
| The Fullscreen dialog | `#/desktop` | `#cancelDialogBtn` (on this dialog the blue one is Cancel), `#okDialogBtn` |
| Desktop open | `#/desktop` | `#canvas` in `#canvas-container` with a non-zero size and an open Blast WebSocket on `/r/…` (or `/d/…`), tracked by `page.on("websocket")`; secondarily — `#sidebar-toggler` is available |
| Disconnect | `#/desktop` | close the browser context; the client records `VDPCONNECT_USER_INIT_DISCONNECT`, the session remains |
| Log Off from the desktop (the fallback path) | `#/desktop` → `#sidebar-toggler` | `#sidebar-logout-button` (icon `icon-logoff-desktop-image`) → `#okDialogBtn` |
| Desktop state | after login | `page.request.post("/broker/xml", <get-launch-items>)` from the authenticated context: the same endpoint the client uses (`do-submit-authentication`, `get-launch-items`, `kill-session`, `disconnect-session`, `do-logout`); used to read the state, not to log in |

The "desktop open" signal and the shape of the `get-launch-items` answer are confirmed by the first
`horizon probe` on the VPS; until then they are a hypothesis from the bundle and are marked so in the code.

### Schedule and deploy

- The timers `horizon-checkin.timer` (`*-*-* 07:55:00 Europe/Moscow`) and
  `horizon-checkout.timer` (`*-*-* 17:00:00 Europe/Moscow`), `Persistent=no`: the skip is
  decided by the service inside the window, not by systemd after the fact. The services are `Type=oneshot`,
  `User=horizon`, `EnvironmentFile=/opt/horizon-tracker/.env`.
- `deploy/bootstrap.sh` modelled on the host's existing bootstrap: the user `horizon`, a clone into
  `/opt/horizon-tracker`, `uv sync`, the units in `/etc/systemd/system`, `daemon-reload`,
  `enable --now` of the timers. It does not touch the secrets.
- `.github/workflows/ci.yml`: `uv sync --extra dev` → ruff → mypy → pytest → beadloom ci
  on a clean index (as the neighbouring service does, but without the workarounds: beadloom 9.0.0 itself pins
  tree-sitter).
- `.github/workflows/deploy.yml`: `on: push: branches [main]` + `workflow_dispatch`,
  environment `horizon-vps`: gate → ssh → `git fetch && checkout` → `uv sync` →
  writing `.env` from the secrets (0600, `horizon:horizon`) → installing the units →
  `systemctl restart` of the timers → `horizon probe` as the user `horizon` as a smoke test.

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/{schedule,calendar,session,report,ports}.py` | the pure core and the ports |
| `src/horizon_tracker/application/{checkin,checkout,probe}.py` | use cases |
| `src/horizon_tracker/infrastructure/{horizon_playwright,isdayoff,telegram,config,clock,artifacts}.py` | adapters |
| `src/horizon_tracker/cli.py` | the `checkin`, `checkout`, `probe` commands; dependency assembly |
| `tests/unit/`, `tests/acceptance/{features,steps}/`, `tests/adapters/` | unit over the core, BDD over the PRD scenarios on fakes, the Playwright adapter on a local markup fixture |
| `tests/fixtures/htmlaccess/` | a static copy of the login, tile, menu and dialog markup with the same ids |
| `deploy/{horizon-checkin,horizon-checkout}.{service,timer}`, `deploy/bootstrap.sh`, `deploy/RUNBOOK.md` | systemd and the initial installation |
| `.github/workflows/{ci,deploy}.yml` | CI and auto-deploy |
| `.beadloom/_graph/*.yml`, `docs/**` | `kind: feature` nodes for every feature with a `SPEC.md`, updated layer READMEs |
| `pyproject.toml` | `pytest-bdd` in the dev dependencies, `[tool.mutmut]` for the core |

### API Changes

The public interface is the CLI and the environment variables:

| Variable | Purpose |
|------------|-----------|
| `HORIZON_URL` | `https://horizon.example.com/portal/webclient/` |
| `HORIZON_USERNAME`, `HORIZON_PASSWORD` | the AD account (secret) |
| `HORIZON_DESKTOP` | the tile name, e.g. `DEV desktop` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | the notification bot and the owner's private chat (secret) |
| `HT_TIMEZONE` | `Europe/Moscow` |
| `HT_CHECKIN_WINDOW`, `HT_CHECKOUT_WINDOW` | `07:55-08:00`, `17:00-17:05` |
| `HT_HOLD_SECONDS` | how long to hold the open desktop in the morning, 120 by default |
| `HT_CHROME_PATH` | `/usr/bin/google-chrome` |
| `HT_ARTIFACTS_DIR` | the directory of screenshots and logs |

## Alternatives Considered

### Option A: only the broker's XML API, no browser
`/broker/xml` can do `do-submit-authentication`, `get-launch-items`, `kill-session`. For the
check-out that would be enough, but the check-in needs an open Blast connection, which cannot be
brought up without the client. Rejected as the only path; kept as reading the state from the
authenticated Playwright context.

### Option B: the native Horizon Client on the VPS under Xvfb
A heavy installation, a licensed client, brittle window automation. Rejected.

### Option C: notifications through the neighbouring service's front door
Editing another project and its gates for the sake of one `sendMessage`. Rejected in favour of a
direct Bot API call with the notification bot's token.

### Option D: cron instead of systemd timers
No `journalctl`, no `failed` status, no `EnvironmentFile`. Rejected.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| The "desktop open" signal in headless differs from the hypothesis from the bundle | Med | High | the first `probe` and a manual `checkin --force` on the VPS before the timers are enabled; the signal is isolated in one adapter method |
| The pool policy ends the session N minutes after a disconnect | Med | Med | the evening run recognises "no session" and reports; the owner checks against the journal in the first days; if confirmed — keeping the session alive is discussed as separate work |
| UAG or the client rejects headless (UA, WebGL) | Low | High | a regular UA, `--use-gl=swiftshader`; the fallback path is `headless=new` Chrome |
| isdayoff.ru is unreachable | Low | Low | fallback to Mon–Fri, the source is named in the notification |
| Chrome on the VPS updated and broke Playwright | Low | Med | `probe` in the deploy as a smoke test; the Playwright version is pinned in `uv.lock` |
| The VPS is off during the window | Low | Med | a skip with a notification, not a late check-in |
| A secret leaked into a log or a screenshot | Low | High | the report has no password field by construction; a screenshot only away from `#/home`; the test `A notification never contains the password` |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | How long to hold the open desktop in the morning so that the Windows logon definitely completes? | Pending: 120 s by default, tuned from the first runs |
| Q2 | Does the pool auto-log-off after a disconnect? | Pending: the owner checks in the first days from the evening reports |
| Q3 | Is `--force` needed for a manual run from the VPS outside the window? | Decided: yes, only by hand from the VPS, the timers do not pass it |
| Q4 | The Python version on the VPS and sudo for `VPS_USER` for `sudo -u horizon` and `systemctl` | Pending: the same user and key as the neighbouring service's deploy; confirmed by the first deploy |
| Q5 | The shape of the `get-launch-items` answer (the session-state field) | Pending: read by the first `probe` on the VPS |
