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

## Related Files

(discover via `beadloom ctx <ref-id>` — never hardcode)

## Current Phase

- **Phase:** Development
- **Current bead:** —
- **Blockers:** HT-010 must be merged first (the same working tree; the HT-012 scenarios would redden the gate on HT-010's branch)
