# Probe and dry run

Checks whether the service could run, without ever logging in: `Probe` asks the portal
for its client bundles, the calendar for today and Chrome for its version, and names the
day's drawn moments; `DryRun` plans the run a use case would make.

## Source

`src/horizon_tracker/application/probe.py`

## Specification

### Purpose

The owner and the deploy need to know whether a run could go ahead before one does,
and neither may log in to the portal to find out. `horizon probe` is the deploy's
smoke test and the first command on a new VPS. `horizon checkin --dry-run` and
`horizon checkout --dry-run` show what a run would do now.

### What the probe measures

The probe asks each dependency the one question it can answer without credentials. Each
check's detail is a `Message` (a catalogue key and its fields, `domain/messages.py`); the
CLI shows it, the check's name and its status in the language `HT_LANGUAGE` names. The
English texts:

| Check | Question | `ok` | Otherwise |
|-------|----------|------|-----------|
| `portal` | which HTML Access client bundles does the portal serve? (`HorizonClient.client_bundles()`) | `client bundles: <names>` | `failed`, `no answer: <reason>` |
| `calendar` | is today a working day? (`WorkingDayCalendar.is_working_day`) | `isdayoff.ru: <date> is a working day` or `... is a day off` | `degraded`, `isdayoff.ru did not answer for <date>; runs fall back to the Mon-Fri rule` |
| `chrome` | is Chrome at the configured path, and does it start? (`file_exists`, then `HorizonClient.browser_version()`) | `Chrome <version> started from <path>` | `failed`, `not found at <path>` or `found at <path> but did not start: <reason>` |
| `schedule` | when do today's runs fall? (the `moments` the probe is given) | `today HH:MM / HH:MM`, the check-in and the check-out moment | never anything but `ok` |

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

The `schedule` check is a fact to read, not a dependency's health, so it is always `ok`.
It comes last and only when the probe is given the day's moments. The composition root
draws them with the same `draw_moments` call a run makes today, so the owner can compare
the probe's line with the day's runs. The CLI prints it without a status:
`schedule: today 07:38 / 16:39` (the `probe.schedule` key, rendered in Russian under `HT_LANGUAGE=ru`).

### How the dry run works

`DryRun(use_case, moments).plan(force=...)` plans the very use case a run would execute:

- the decision is `use_case.runner.first_decision(force=...)`, the decision the run
  loop would take on its first attempt: now, or at the drawn moment when the run would
  wait for it first (this asks the calendar unless forced);
- the steps are `use_case.steps()` followed by `use_case.runner.steps()`, each a
  `Message` the CLI prints in the configured language;
- `waits_until` is the drawn moment a run started now would sleep until first, taken from
  the same `first_decision`, and `moments` is the day's drawn pair the dry run was given.

Neither the decision nor the steps are restated in this module, so a plan cannot drift
from the run it describes. The dry run calls nothing on the Horizon client, so it cannot
log in.

The settings are validated before either object is built: the composition root
creates a probe or a dry run only for a configuration `Settings.from_env` accepted.

## Invariants

- Neither the probe nor the dry run calls `login` or any other method that needs the
  account.
- The probe runs every check once, whatever the others answered.
- The probe starts Chrome only after the file was found at the configured path.
- A degraded calendar never makes the probe fail.
- The probe and the dry run never draw the moments themselves: they name the pair the
  composition root drew, so they cannot disagree with a run of the same day.
- The dry run sends no report and reads its decision and steps from the use case and its
  run loop.
- Neither the probe nor the dry run picks a language: every text they hand out is a
  `Message`, so the same plan reads in English or Russian without a second code path.
- A check whose name or status has no text in the catalogue cannot be made.

## API

Module `src/horizon_tracker/application/probe.py`:

- `CheckStatus` — `StrEnum`: `OK`, `DEGRADED`, `FAILED`.
- `Check(name: str, status: CheckStatus, detail: Message)` — frozen. `name` and `status`
  are identifiers; `label` (`probe.check.<name>`) and `status_label`
  (`probe.status.<status>`) are the same as messages, made with the check (not
  constructor arguments, not compared), so a name the catalogue lacks raises `KeyError`
  where the check is made. The CLI shows `label` and `status_label`.
- `ProbeReport(checks: tuple[Check, ...])` — frozen; `ok -> bool` property.
- `Probe(client: HorizonClient, calendar: WorkingDayCalendar, clock: Clock, chrome_path:
  Path, file_exists: Callable[[Path], bool], moments: DailyMoments | None = None)` —
  frozen; `run() -> ProbeReport` with the checks `portal`, `calendar`, `chrome` in that
  order, then, when `moments` is given, `schedule` (`ok`, detail
  `schedule_detail(moments)`). The probe never draws the moments; the composition root
  does.
- `schedule_detail(moments: DailyMoments) -> Message` — today's drawn pair, key
  `probe.schedule`: `today 07:43 / 16:52` in English.
- `RunPlan(kind, at, forced, decision, verdict_source, steps: tuple[Message, ...],
  waits_until: datetime | None = None, moments: DailyMoments | None = None)` — frozen; `would_run -> bool` is
  true for `RUN` and `RETRY`. `waits_until` comes from the loop's `first_decision`;
  `moments` is the day's drawn pair as the dry run was given it, forced or not.
- `PlannedRun` — `Protocol`: `kind` and `runner` properties, `steps() -> tuple[Message, ...]`.
  `MorningCheckin` and `EveningCheckout` satisfy it.
- `DryRun(use_case: PlannedRun, moments: DailyMoments | None = None)` — frozen;
  `plan(*, force: bool = False) -> RunPlan`.

The CLI builds `Probe` with `chrome_path=settings.chrome_path` and
`file_exists=Path.is_file`; the Horizon client takes its Chrome path from the same
setting.

## Testing

Tests: `tests/unit/application/test_probe.py`, `tests/unit/test_cli.py`.

Scenarios (`tests/acceptance/features/checks_without_login.feature`):

- `Probe reports the portal version without logging in`
- `A dry run walks the plan and performs no login`

Scenarios that read the `schedule:` line (`tests/acceptance/features/randomised_moments.feature`):

- `The check-out moment is nine hours plus up to ten minutes after the check-in`
- `The same date gives the same drawn moments in two separate runs`
- `A dry run names the drawn moment of the day`

Scenarios that read the probe and the dry run in a language
(`tests/acceptance/features/language.feature`):

- `The probe reads in the configured language`
- `A dry run reads in the configured language`

## Dependencies

Derived from the imports on reindex.

- Depends on: `messages`, `ports`, `schedule`, `windowed-run`, `working-day-calendar`
- Used by: `cli`
- External contract (declared in `.beadloom/_graph/landscape.yml`, not derived): consumes
  `http:horizon-client-bundle` from [`horizon-portal`](../../../external/horizon-portal/SPEC.md)

## Parent

`application` — [application README](../../README.md)
