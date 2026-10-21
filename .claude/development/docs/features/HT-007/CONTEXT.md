# CONTEXT: HT-007 — Language of the notifications and the CLI output (i18n)

> **Status:** Approved
> **Created:** 2026-10-20
> **Last updated:** 2026-10-20

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

- **Phase:** Development (wave 2)
- **Current bead:** BEAD-02 (ht-1yu)
- **Blockers:** —
- **BEAD-01 departures from the documents:** the catalogue in `domain`, not in `infrastructure` (the RFC outranks CONTEXT); `text()` raises `KeyError` on an unknown key rather than returning the key with a log line (a test/production switch and logging in the domain are not needed — the completeness tests make the case unreachable); `render(report, language)` without a default value, so a forgotten argument does not silently give English
