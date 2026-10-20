# Probe and dry run

Checks whether the service could run, without ever logging in: `Probe` asks the portal
for its client bundles, the calendar for today and Chrome for its version; `DryRun`
plans the run a use case would make.

## Source

`src/horizon_tracker/application/probe.py`

## Specification

### Purpose

The owner and the deploy need to know whether a run could go ahead before one does,
and neither may log in to the portal to find out. `horizon probe` is the deploy's
smoke test and the first command on a new VPS. `horizon checkin --dry-run` and
`horizon checkout --dry-run` show what a run would do now.

### What the probe measures

The probe asks each dependency the one question it can answer without credentials:

| Check | Question | `ok` | Otherwise |
|-------|----------|------|-----------|
| `portal` | which HTML Access client bundles does the portal serve? (`HorizonClient.client_bundles()`) | `client bundles: <names>` | `failed`, `no answer: <reason>` |
| `calendar` | is today a working day? (`WorkingDayCalendar.is_working_day`) | `isdayoff.ru: <date> is a working day` or `... is a day off` | `degraded`, `isdayoff.ru did not answer for <date>; runs fall back to the Mon-Fri rule` |
| `chrome` | is Chrome at the configured path, and does it start? (`file_exists`, then `HorizonClient.browser_version()`) | `Chrome <version> started from <path>` | `failed`, `not found at <path>` or `found at <path> but did not start: <reason>` |

The probe reads no portal version. It names the bundle files as the portal serves them in
`index.html` and parses nothing out of them, and it names the version the started Chrome
reports. The acceptance scenario keeps its approved PRD name,
`Probe reports the portal version without logging in`, while its steps assert the client
bundles and the Chrome version. Renaming it is an amendment of the approved PRD, which is
the owner's decision.

The Chrome check looks for the file first and starts Chrome only when the file exists,
so a missing binary is named without a launch. A binary that exists but does not start
(for example, a Chrome updated past what the locked Playwright can drive, or missing
system libraries) is named separately from a missing one.

An unreachable calendar degrades the probe rather than failing it, because a run falls
back to the Monday-Friday rule. `ProbeReport.ok` is true unless a check `FAILED`.

### How the dry run works

`DryRun(use_case).plan(force=...)` plans the very use case a run would execute:

- the decision is `use_case.runner.first_decision(force=...)`, the decision the run
  loop would take on its first attempt now (this asks the calendar unless forced);
- the steps are `use_case.steps()` followed by `use_case.runner.steps()`.

Neither is restated in this module, so a plan cannot describe a run that no longer
exists. The dry run calls nothing on the Horizon client, so it cannot log in.

The settings are validated before either object is built: the composition root
creates a probe or a dry run only for a configuration `Settings.from_env` accepted.

## Invariants

- Neither the probe nor the dry run calls `login` or any other method that needs the
  account.
- The probe runs every check once, whatever the others answered.
- The probe starts Chrome only after the file was found at the configured path.
- A degraded calendar never makes the probe fail.
- The dry run sends no report and reads its decision and steps from the use case and its
  run loop.

## API

Module `src/horizon_tracker/application/probe.py`:

- `CheckStatus` — `StrEnum`: `OK`, `DEGRADED`, `FAILED`.
- `Check(name: str, status: CheckStatus, detail: str)` — frozen.
- `ProbeReport(checks: tuple[Check, ...])` — frozen; `ok -> bool` property.
- `Probe(client: HorizonClient, calendar: WorkingDayCalendar, clock: Clock, chrome_path:
  Path, file_exists: Callable[[Path], bool])` — frozen; `run() -> ProbeReport` with the
  checks `portal`, `calendar`, `chrome` in that order.
- `RunPlan(kind, at, forced, decision, verdict_source, steps)` — frozen;
  `would_run -> bool` is true for `RUN` and `RETRY`.
- `PlannedRun` — `Protocol`: `kind` and `runner` properties, `steps()`.
  `MorningCheckin` and `EveningCheckout` satisfy it.
- `DryRun(use_case: PlannedRun)` — frozen; `plan(*, force: bool = False) -> RunPlan`.

The CLI builds `Probe` with `chrome_path=settings.chrome_path` and
`file_exists=Path.is_file`; the Horizon client takes its Chrome path from the same
setting.

## Testing

Tests: `tests/unit/application/test_probe.py`, `tests/unit/test_cli.py`.

Scenarios (`tests/acceptance/features/checks_without_login.feature`):

- `Probe reports the portal version without logging in`
- `A dry run walks the plan and performs no login`

## Dependencies

Derived from the imports on reindex.

- Depends on: `ports`, `schedule`, `windowed-run`, `working-day-calendar`
- Used by: `cli`

## Parent

`application` — [application README](../../README.md)
