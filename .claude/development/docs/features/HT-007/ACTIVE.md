# ACTIVE: HT-007 — i18n

> **Last updated:** 2026-10-20
> **Phase:** Development

---

## Current Bead

**Bead:** BEAD-02 (ht-1yu) — `HT_LANGUAGE` in Settings, the language in the notifier, probe/dry-run keys, the CLI translates
**Goal:** the language of the notifications and of the CLI output comes from a setting (en by default)
**Done when:** `telegram._LANGUAGE` is replaced by a constructor argument, `HT_LANGUAGE` is validated, the CLI prints through the catalogue; the tests bite

## Progress

- [x] The documents are approved by the owner's standing decision (2026-10-20); the beads are created, parent ht-7a0
- [ ] BEAD-01 → BEAD-02 → BEAD-03 → BEAD-04 → BEAD-05 → BEAD-06

## Results

| Bead | Status | Details |
|------|--------|---------|
| BEAD-01 | Done | ht-7kx, 9070895: `domain/messages.py` (`Language`, 75 keys en/ru, `text`, `missing_translations`), `render(report, language)`; 282 tests, 1058 passed / 4 skipped, coverage 99 %, mutations 301/303 (99.3 %; the survivors — `schedule._pick`), 13 sabotages bite; a temporary constant `_LANGUAGE = RU` in the notifier until BEAD-02 |
| BEAD-02 | Open | — |
| BEAD-03 | Open | — |
| BEAD-04 | Open | — |
| BEAD-05 | Open | — |
| BEAD-06 | Open | — |

## Notes

- The four PRD scenarios need to be put into the suite as SKIP stubs until BEAD-03 (as with HT-003/HT-004), otherwise `scenario-coverage` keeps the gate red.
