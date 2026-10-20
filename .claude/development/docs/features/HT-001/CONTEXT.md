# CONTEXT: HT-001 — Automatic check-in and check-out of Horizon VDI

> **Status:** Draft
> **Created:** 2026-10-20
> **Last updated:** 2026-10-20

---

## Goal

A service on the VPS that on every working day at 07:55 in the configured time zone opens the configured desktop in
VMware Horizon until the Windows logon has completed and disconnects, and at 17:00 performs
Log Off, and reports every run to Telegram.

## Key Constraints

- The check-in counts as happened only with an open Blast connection and a drawn desktop;
  the morning exit is a disconnect, the evening one a log off. These two actions are not to be confused.
- The live portal only from the VPS. No logging into the portal from CI or the agent's sandbox; the browser
  adapter is checked on a local markup fixture with the same ids as in the bundle of
  HTML Access 2312.
- Secrets (the AD account, the notification bot's token, the chat id) — only in the GitHub Environment `horizon-vps`
  and in `/opt/horizon-tracker/.env`; they appear in no logs, screenshots or bead comments.
- Dependency direction `cli → infrastructure → application → domain`, the ports are declared by
  `domain`; `beadloom lint --strict` on a clean index holds this rule.
- The configured time zone (`Europe/Moscow`); the domain receives time as an argument and does not read the clock itself.
- Working days by isdayoff.ru with a fallback to Mon–Fri when it is unreachable; the source of the verdict
  is named in the notification.
- A neighbouring service shares the VPS: a separate user `horizon`, home `/opt/horizon-tracker`,
  the neighbour's directory is not touched. The deploy repeats the shape of the neighbour's commands (`sudo -u`, `systemctl`).
- The owner's time: the first live run is done by the owner from the VPS with `--force` and the
  result is checked against the Horizon journal or the accounting system; the timers are enabled after that.

## Code Standards

### Language and Environment
- Python 3.12 (`str | None`, `zoneinfo`, `pathlib`), `uv` and `uv.lock`, the package `horizon-tracker`
  with the entry point `horizon`.
- Dependencies: `click`, `httpx`, `playwright`; dev: `pytest`, `pytest-cov`, `pytest-bdd`,
  `ruff`, `mypy`, `mutmut`.

### Methodologies

| Methodology | Application |
|-------------|-------------|
| TDD | Red → Green → Refactor; the test for the core is written before the core's code |
| Clean Code | SRP, DRY, KISS; short functions, names from the Horizon domain |
| Architecture | a hexagon in four graph nodes: `domain` without I/O, `application` over the ports, `infrastructure` implements the ports, `cli` assembles; see the ARCHITECTURE section of CLAUDE.md |
| Cohesion-driven | one nameable responsibility per module and class, named in the first line of the docstring; `review` checks in both directions |
| BDD acceptance | the twelve PRD scenarios as `.feature` in `tests/acceptance/features/`, steps over fakes of the ports; the document references a scenario by name |
| Mutation | `mutmut` only on `src/horizon_tracker/domain/`; score ≥ 85 %, equivalent mutants named, not silenced |

### Testing
- **Framework:** pytest + pytest-cov; `pytest-bdd` for acceptance; Playwright headless
  Chromium on a local fixture for the browser adapter.
- **Coverage:** minimum 80 % over `src/`; the `domain/` core — 100 % of lines, not a goal but a consequence of TDD.
- **Structure:** `tests/unit/` (the core and the use cases on fakes), `tests/acceptance/` (BDD),
  `tests/adapters/` (Playwright on the fixture, isdayoff and Telegram on `httpx.MockTransport`),
  `tests/fixtures/htmlaccess/` (the markup).
- **Whether the tests bite:** a new test must go red on a sabotage of the code; "green on broken code" is not
  a test. Compare the numbers collected and passed, not the colour.

### Code Quality
- **Linter/type-checker:** `uv run ruff check src/ tests/`, `uv run mypy src/` (strict).
- **Gate:** `rm -f .beadloom/beadloom.db && beadloom reindex && beadloom ci` — on a clean
  index, because an incremental reindex does not update the import edges.

### Restrictions
- No unjustified escape hatch from the type system
- No stray debug output — use the language's logging facility
- No catch-all exception handler — name the exception
- Language-specific restrictions: see the STACK section of CLAUDE.md (no `Any` without
  a reason, no `print()`, no bare `except:`, no `os.path`, no `yaml.load`)
- The password reaches no `str()`/`repr()`: `Settings` keeps it in a field that
  `__repr__` masks; `RunReport` has no such field by construction.
- No `time.sleep` in the domain and the use cases: waiting is the port `Clock.sleep`, a fake in the
  tests.

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-20 | Playwright over the system Chrome, not the XML API or the native client | only the client brings up Blast, and the check-in is recorded by the Windows logon; Chrome is already on the VPS |
| 2026-10-20 | The evening Log Off from the tile menu on `#/launchitems`, the desktop is not opened | the bundle has `#menu-item-logoff-btn` → `kill-session`; shorter and without Blast |
| 2026-10-20 | In the morning disconnect = closing the browser context, holding for `HT_HOLD_SECONDS` (120 s) | the owner: hold until the desktop has loaded; the session must remain until 17:00 |
| 2026-10-20 | Notifications straight to the Bot API with the notification bot's token, the neighbouring service is not changed | one `sendMessage` is not worth editing someone else's gates; a service voice by meaning |
| 2026-10-20 | systemd timers without `Persistent`, the skip outside the window is decided by the service | a late check-in is worse than a skip; the skip report is visible in Telegram |
| 2026-10-20 | Windows 07:55–08:00 and 17:00–17:05, retries inside the window | the owner agreed to a 5-minute tolerance |
| 2026-10-20 | The isdayoff.ru calendar with a fallback to Mon–Fri | an external service can go down; the fallback is named in the notification |
| 2026-10-20 | Deploy on a push to `main`, `.env` is written by the deploy from the secrets | the owner's requirement: secrets in GitHub, a release without manual steps |
| 2026-10-20 | The epic's axes declared by the owner, not derived | over the empty skeleton the derivation found no seed; recorded in the RFC |
| 2026-10-20 | The desktop state is read from the tile; XML `get-launch-items` is a hypothesis until the first `probe` | the shape of the answer is not measured |

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode)

- `beadloom ctx domain` / `application` / `infrastructure` / `cli` / `horizon-tracker`
- PRD, RFC, PLAN, ACTIVE in `.claude/development/docs/features/HT-001/`

## Current Phase

- **Phase:** Planning
- **Current bead:** —
- **Blockers:** none
