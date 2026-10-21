# CONTEXT: HT-007 — Language of the notifications and the CLI output (i18n)

> **Status:** Done
> **Created:** 2026-10-20
> **Last updated:** 2026-10-21

---

## Goal

All human-readable texts come from the domain catalogue, the language by `HT_LANGUAGE` (`en` by default, `ru`).

## Key Constraints

- The catalogue is plain data in the domain; completeness across languages is pinned by a test.
- The logs stay English.
- Starts after HT-004 BEAD-03 (shared BDD step files), before the final clean-up.
- Standards — as in the project layer of CLAUDE.md; TDD, BDD over the four scenarios, domain
  mutations (the data catalogue is excluded from the mutation scope as equivalent noise — the decision
  is to be recorded in `[tool.mutmut]`/`flow.yml` with its reason).

## Architectural Decisions

| Date | Decision | Reason |
|------|----------|--------|
| 2026-10-20 | A catalogue in code, not gettext | two languages, ~40 keys, typing |
| 2026-10-20 | The use cases hand out keys, the CLI/notifier translates | the domain and application do not know the output language |
| 2026-10-20 | The logs are not translated | the operator reads them, not the owner |
| 2026-10-20 | Approved by the owner's standing decision («carry the tasks on yourself») | the owner delegated running the tasks to the coordinator; no separate «Approved» is required |
| 2026-10-21 | BEAD-02: the use cases and the settings hand out a `Message(key, fields)` from `domain/messages.py`, not a string; the CLI picks the language | so application and `Settings` do not know the output language (Q2 of the RFC), and a typo in a key fails when the message is created, not when it is printed |
| 2026-10-21 | BEAD-02: a configuration error is always an English log line, plus an echo to stderr in the reader's language, only if it is not English | the PRD requires English logs, the RFC requires `ConfigError` to be translated; an echo under `en` would duplicate the log line. The language is read separately (`language_from_env`), because `Settings` did not load |
| 2026-10-21 | BEAD-02: `HT_LANGUAGE` in the deployment is an optional variable of the `horizon-vps` environment (`vars.HT_LANGUAGE`), not a secret and not a manual edit of `.env` | the deployment rewrites `.env` on every roll-out, a manual edit would live until the next push to `main`; without the variable the service speaks English |
| 2026-10-21 | ht-7a0.1: a domain refusal that a setting's value reaches is a `ScheduleError(reason: Message)` with `schedule.*` keys; `Message.in_language` translates a message field into the same language; `config.*` keep the `{error}` field | the English `ValueError` text in the `{error}` field gave a Russian line with an English tail (PRD US-2); a message as the reason requires neither the domain to know the language nor the adapter to know the domain's rules. Refusals that only code reaches (an empty seed, seconds, a negative extra) stay `ValueError`: they have no reader, and keys without a reader would be dead |
| 2026-10-21 | BEAD-02: the acceptance scenes from before HT-007 pin the notification language `ru`, the CLI output follows `HT_LANGUAGE` (`en`) | the scenario «A check-out past the end of its range is clipped» checks a Russian notification and English output in one run; one setting cannot express both. The scene with `notification_language=None` builds the notifier from `HT_LANGUAGE` through `cli.build_notifier` — for the BEAD-03 scenarios |

## Code Standards

### Language and Environment
- Python 3.12, `uv`; the code, docstrings and logs in English; the flow documents in English (`language: en`).

### Methodologies
- Clean Architecture: `cli` → `infrastructure` → `application` → `domain`; the message catalogue lives in `domain` (plain data and `text()`), the use cases hand out keys.
- Cohesion-driven: the catalogue module has one responsibility — translating a key into the text in the configured language.
- TDD: the catalogue and rendering tests first; mutations over the domain only (`flow.yml`).

### Testing
- pytest + pytest-bdd; the `language.feature` scenarios replace the stubs in BEAD-03 (ht-bsc).
- Coverage ≥ 80 % over `src/`.

### Code Quality
- ruff, mypy --strict; no `Any` and no `# type: ignore` without a reason.

### Restrictions
- The logs are not translated; secrets do not get into the messages; `HT_LANGUAGE` outside `{en, ru}` is refused at start-up.

## Related Files

- `src/horizon_tracker/domain/messages.py` — the catalogue (new; per the RFC — in the domain, without I/O)
- `src/horizon_tracker/infrastructure/telegram_notifier.py`, `src/horizon_tracker/cli.py` — the consumers
- `src/horizon_tracker/infrastructure/config.py` — `HT_LANGUAGE`
- `tests/acceptance/features/language.feature` — the PRD scenarios

## Current Phase

- **Phase:** Done
- **Current bead:** BEAD-06 (ht-1rh)
- **Blockers:** —
- **BEAD-01 departures from the documents:** the catalogue in `domain`, not in `infrastructure` (the RFC outranks CONTEXT); `text()` raises `KeyError` on an unknown key rather than returning the key with a log line (a test/production switch and logging in the domain are not needed — the completeness tests make the case unreachable); `render(report, language)` without a default value, so a forgotten argument does not silently give English
