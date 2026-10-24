# CONTEXT: HT-012 — Absences through the bot, and one notice for a skipped day

> **Status:** Approved
> **Created:** 2026-10-24
> **Last updated:** 2026-10-24

---

## Goal

The owner enters absences (vacation, sick leave, day off) through the Telegram bot and
the scheduled runs respect them; a skipped day produces one readable morning notice and
no evening one.

## Key Constraints

- Direction `cli` → `infrastructure` → `application` → `domain`; ports in `domain/ports.py`;
  the domain reads no clock, file or network (today's date arrives as an argument).
- The pure domain (`absence.py`, `bot_commands.py`, `report.py`, `messages.py`) is inside
  the mutation gate: no surviving non-equivalent mutant.
- Secrets: the bot token never reaches the journal (the notifier's redaction is reused);
  the live Bot API and the live portal are never called from CI or the sandbox.
- One poller per bot: `horizon-bot.service` is the only `getUpdates` caller.
- Absences live in `HT_STATE_DIR/absences.json` (default `/opt/horizon-tracker/state`),
  outside the checkout, 0600, written atomically; they survive deploy, restart and reboot.
- A broken store never stops a working day: the run logs it and treats it as empty;
  `probe` reports it.
- Only `TELEGRAM_CHAT_ID` is served; any other sender gets no reply and its text is not logged.
- Owner's rulings (2026-10-24): one notice in the morning on any day-level skip (calendar or
  absence), the evening is silent; text commands only, no keyboards; one release `v1.1.0`
  after HT-010 and HT-012 are both merged.

## Code Standards

### Language and Environment
- Python 3.12, `uv`, `click`, `httpx`; see the STACK section of `.claude/CLAUDE.md`.

### Methodologies

| Methodology | Application |
|-------------|-------------|
| TDD | Red → Green → Refactor; domain first |
| Clean Code | one nameable responsibility per module, named in the docstring's first line |
| Architecture | DDD layers as in the project layer of `.claude/CLAUDE.md`; `beadloom lint --strict` enforces |

### Testing
- **Framework:** pytest + pytest-cov; pytest-bdd for the scenarios; `httpx.MockTransport` for the Bot API
- **Coverage:** minimum 80 % (the tree is at 99 %; do not lower it)

### Code Quality
- ruff (lint + format), mypy --strict on `src` and `tests`

### Restrictions
- No `Any` / `# type: ignore` without a stated reason; no `print()`; no bare `except:`;
  pathlib only; `yaml.safe_load` only (no YAML is expected here); JSON through `json`.

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-24 | The PRD was approved by the owner in chat ("Утверждаю, всё"); the RFC, CONTEXT and PLAN are approved by the owner's standing decision of the same day ("Дальше веди сам") and were reported to the owner at the control point | the owner asked the coordinator to run the flow end to end |
| 2026-10-24 | Absences are checked before the calendar and without a calendar call | no network for a day that will not run; the notice names the absence, not the weekend |
| 2026-10-24 | A day-level skip (`NON_WORKING_DAY`, the absence reasons) notifies from the morning run only, through `WindowedRun(notify_day_skips=...)` set by the CLI per command | the owner's ruling; the anomalies `TOO_EARLY` / `WINDOW_MISSED` keep notifying |
| 2026-10-24 | The command parser is a pure domain function returning `Command | CommandError` with catalogue `Message`s | replies in `HT_LANGUAGE` without the parser knowing a language; mutation-tested |
| 2026-10-24 | Long polling in a separate `horizon-bot.service`, `Restart=always` | no public endpoint; the timers stay oneshot and never wait on the bot |
| 2026-10-24 | Overlapping absences are refused, not merged | an explicit edit beats a silent merge; the reply names the overlapping id |
| 2026-10-24 | Ids are small integers, max + 1, never reused | typeable in a chat; a deleted id does not come back under a new meaning |
| 2026-10-24 | `dd.mm` without a year means the next occurrence from today | the common case is "next month"; pinned across the year boundary |
| 2026-10-24 | `allocate_id(absences, *, last_issued=0)` takes the highest id ever issued beside the absences (BEAD-01) | max + 1 over the absences held alone reuses the id of a deleted absence that held the highest one, so "never reused" needs the high-water mark; the store (BEAD-04) keeps it and the service (BEAD-07) passes it |
| 2026-10-24 | The calendar line is one full-line key per source (`report.calendar.calendar`, `.weekday_fallback`, `.not_asked`) instead of a `report.calendar` frame around a `report.source.*` phrase (BEAD-03) | the Russian phrase for the calendar source would be `isdayoff.ru` alone, which holds no Cyrillic and fails the catalogue test that every `ru` text is Russian. A whole line per source keeps that test meaningful |
| 2026-10-24 | The absence reasons are keyed `reason.on_vacation`, `reason.on_sick_leave`, `reason.on_day_off` (the `Reason` values), not the RFC's `report.reason.vacation/...` (BEAD-03) | every other reason is keyed `reason.<Reason value>` and `render` builds the key from the value, and a second scheme would need a lookup table of its own |
| 2026-10-24 | `RunReport` refuses an absence whose reason is not its kind's, whose outcome is not `SKIPPED` or whose `verdict_source` is set, and `is_day_level_skip` is a property of the report (BEAD-03) | BEAD-05 builds these reports and decides the morning-only notice by the same predicate the time line uses, so the two cannot disagree |
| 2026-10-24 | A one-day absence renders one day, `(05.11)`, a span crossing New Year renders without the year, `(28.12–09.01)`, and the English phrase for `DAY_OFF` is `day off taken` (BEAD-03) | `03.11–03.11` repeats itself, the reader knows the year, and `a day off` is already the holiday's reason, so the owner's own day off needs words of its own |
| 2026-10-24 | ruff's `allowed-confusables` admits the en dash only (BEAD-03) | the PRD's texts use `Mon–Fri` and `03.11–14.11` with an en dash, and every other confusable stays reported |
| 2026-10-24 | A yearless date is placed near its anchor (BEAD-02): a range's end is its next occurrence on or after today (or after a start written with its year), its start the latest occurrence on or before that end; a single date is the next occurrence from today, today included. This refines the RFC's "each yearless date from today" | read independently, `23.10-27.10` entered on 24.10 (a sick leave from yesterday) puts its start in 2027 and is refused as reversed, and `/edit` of a running vacation cannot keep its start; anchoring the start to the end keeps both, and `28.12-09.01` still crosses the New Year |
| 2026-10-24 | The parser ignores the words after `/list`, `/help` and `/start`, and in `/edit` the word after the id is a kind unless it starts with a digit (BEAD-02) | Telegram's `/start` carries a deep-link payload, and every date starts with a digit while no kind does, so the optional kind needs no lookahead |
| 2026-10-24 | The bot names a kind with `bot.kind.<AbsenceKind value>` (`day off` for `DAY_OFF`), not with the report's `reason.on_*`, and its replies give the days with the year through `bot.days.single` / `bot.days.span` (BEAD-02) | the reason phrases are worded for a notice line (`day off taken`), and the RFC's mitigation for a misread year is a reply that echoes the full dates; the Russian forms (`дни 03.11.2026–14.11.2026`, `день 05.11.2026`) avoid a standalone `с`, which ruff reports as a Latin look-alike |

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode)

## Current Phase

- **Phase:** Development
- **Current bead:** —
- **Blockers:** HT-010 must be merged first (the same working tree; the HT-012 scenarios would redden the gate on HT-010's branch)
