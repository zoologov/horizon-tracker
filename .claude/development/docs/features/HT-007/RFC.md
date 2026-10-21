# RFC: HT-007 — Language of the notifications and the CLI output (i18n)

> **Status:** Done
> **Created:** 2026-10-20

---

## Overview

A new domain module `domain/messages.py` (node `messages`): `Language` (`en`, `ru`),
the catalogue `MESSAGES: dict[str, dict[Language, str]]` with keys of the form `report.checkin.succeeded`,
`probe.settings.ok`, `plan.step.login`, and the pure function `text(key, language, **params)`.
`render(report, language)` in `domain/report.py` builds the notification from the catalogue. `Settings`
reads `HT_LANGUAGE` into a `Language`; the notifier and the CLI receive the language at assembly. The logs are not
touched.

## Motivation

### Problem
Russian literals in `report.render`, `cli._echo_*`, `probe` and the `ConfigError` messages.

### Solution
One catalogue in the domain, the language choice in the settings, the language passed along at assembly.

## Technical Context

### Constraints
- The catalogue is plain data without I/O; a completeness test over every key and language.
- `Language` is a `StrEnum`; an unknown `HT_LANGUAGE` value → `ConfigError` with the variable's name.
- The logs stay English (journald is read by the operator, not the owner).
- Message parameters (the time, the reason, the moment) are substituted through `str.format` with
  named fields; the password cannot get into the catalogue — `RunReport` does not carry it.

### Affected Areas
`run-report`, the new `messages`, `telegram-notifier` (receives the language), `probe` and `cli`
(the output lines), `settings` (`HT_LANGUAGE`).

## Axes

Derived, never authored. Run `beadloom impact <path|symbol>`, paste its answer into the table,
then take the scope decision in the last two columns — the derivation says what a change ranges
over, a person says how much of it this work item takes. The `refs:` of every bead below is
generated from the rows kept in scope, so a bead naming a node this table does not is a finding.

Rule each row by the node's role in the change: the axis a node surfaced under is not its role.
The axis is the node's relation to the seed, so a `callers` row can be a work site — a node that
calls into the change can also own what the change must edit. `Owns unread` names the files the
node owns that the derivation could not read; a count there is a question to answer before `no`.

> **Derived by:** `beadloom impact src/horizon_tracker/domain/report.py --section` and `src/horizon_tracker/cli.py --section` over `src/horizon_tracker`, 2026-10-20, role explore
> **Seed:** none — no name the target reaches performs a declared effect under rule `reaches-an-effect-sink`, so every axis below is unresolved and not empty
> **Unresolved:** 1 name-defined-more-than-once, 1 no-seed, 2 unresolved-terminator-name (report); 2 name-defined-more-than-once, 1 no-seed, 32 unresolved-terminator-name (cli); `probe.py` and `config.py` were not run — declared below

| Axis | Node | Sites | Owns unread | In scope | Why |
|------|------|-------|-------------|----------|-----|
| co-writers | — | unresolved — no declared effect rule found a sink this target reaches, so there is no commit point to ask who else writes through | — | no | no row |
| callers | telegram-notifier | 1 — `src/horizon_tracker/infrastructure/telegram.py:66` | none | yes | calls `render`; receives the language at assembly |
| branches | run-report | `render`: 2 branch(es), 1 exit form(s), over every call | none | yes | the text from the catalogue by language |
| branches | run-report | `_time_line`: 1 branch(es), 2 exit form(s), over every call | none | yes | the same |
| branches | run-report | `_require`, `__post_init__` | none | no | the field validation does not change |
| branches | telegram-notifier | `send`: 2 branch(es), 1 exit form(s), over every call, from a caller's seat | none | yes | passes the language to `render` |
| callers | schedule | 1 — `src/horizon_tracker/domain/schedule.py:139` | none | no | the draw carries no text |
| branches | cli | `_echo_plan`, `_echo_probe`, `_probe_line`, `_guarded` (the ConfigError message) | none | yes | the output lines from the catalogue |
| branches | cli | the others (`open_adapters`, `_notifier`, `main`, `checkin`, `checkout`, `probe`, `_run`, `_prune`, `_todays_moments`, `_use_case`, `_probe`, `_draw_range`, `_hold`, `_span`, `_configure_logging`, `prune`) | none | no | assembly; `_notifier` only passes the language |
| declared (outside the derivation) | messages | the new `src/horizon_tracker/domain/messages.py` | none | yes | the catalogue and `text()` |
| declared (outside the derivation) | probe | `src/horizon_tracker/application/probe.py` — the `DryRun.plan` and `ProbeReport` lines | none | yes | the texts of the steps and checks from the catalogue (or keys the CLI translates) |
| declared (outside the derivation) | settings | `src/horizon_tracker/infrastructure/config.py` | none | yes | `HT_LANGUAGE` → `Language` |

## Proposed Solution

### Changes

| File / Module | Change |
|---------------|--------|
| `src/horizon_tracker/domain/messages.py` | `Language`, `MESSAGES`, `text()`, `missing_translations()` |
| `src/horizon_tracker/domain/report.py` | `render(report, language=Language.EN)` from the catalogue |
| `src/horizon_tracker/application/probe.py` | `DryRun`/`Probe` hand out keys and parameters; the CLI translates (or they take the language — BEAD-02 decides, uniformly) |
| `src/horizon_tracker/infrastructure/config.py` | `HT_LANGUAGE`, validation |
| `src/horizon_tracker/infrastructure/telegram.py` | the language in the constructor |
| `src/horizon_tracker/cli.py` | the output lines and `ConfigError` through the catalogue; the language at assembly |
| tests, BDD, the SPEC of `messages`, `run-report`, `settings`, `cli.md` | |

### API Changes
`HT_LANGUAGE` (`en` by default, `ru`); `render(report, language)`; `TelegramNotifier(..., language)`.

## Alternatives Considered

### Option A: gettext/.po
Infrastructure for the sake of two languages and ~40 strings. Rejected; a catalogue in code is simpler and typed.

### Option B: the language from the system locale
The VPS runs in `C.UTF-8`; an explicit setting is more honest. Rejected.

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| A key missing in one language | Med | Low | the catalogue completeness test; `text()` fails on an unknown key in the tests, in production returns the key and logs |
| The existing BDD steps are bound to Russian strings | High | Low | the steps check keys/the English text; Russian is checked by one scenario |

## Open Questions

| # | Question | Decision |
|---|----------|----------|
| Q1 | Approval | Decided: the owner's standing decision of 2026-10-20 |
| Q2 | Where to translate the probe/dry-run lines | Decided in BEAD-02: the use cases hand out keys and parameters, the CLI translates — the domain and application do not know the output language |
