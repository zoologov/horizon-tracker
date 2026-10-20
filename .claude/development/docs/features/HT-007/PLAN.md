# PLAN: HT-007 — Language of the notifications and the CLI output (i18n)

> **Status:** Approved
> **Created:** 2026-10-20

---

**Parent bead:** ht-7a0

## Epic Description

The message catalogue in the domain, `HT_LANGUAGE` in the settings, the language in the notifier and the CLI, the four
PRD scenarios, review, documentation, a live check of a Russian notification by the owner.

## Dependency DAG

```mermaid
graph TD
    B01[BEAD-01 P1 domain: messages + render(language)] --> B02[BEAD-02 P1 settings, notifier, probe keys, cli]
    B02 --> B03[BEAD-03 P1 test: 4 scenarios]
    B03 --> B04[BEAD-04 P1 review]
    B04 --> B05[BEAD-05 P2 tech-writer]
    B05 --> B06[BEAD-06 P2 live: ru notification]
```

**Critical path:** 01 → 02 → 03 → 04 → 05 → 06

## Beads

| ID | Tracker | Name | Priority | Depends On |
|----|---------|------|----------|------------|
| BEAD-01 | ht-7kx | Domain: `messages.py` (Language, the catalogue, text, completeness), `render(report, language)` | P1 | HT-004 ht-bm9 |
| BEAD-02 | ht-1yu | `HT_LANGUAGE` in Settings; the language in TelegramNotifier; probe/dry-run hand out keys; the CLI translates the output and ConfigError | P1 | 01 |
| BEAD-03 | ht-bsc | Test: the four PRD scenarios, coverage | P1 | 02 |
| BEAD-04 | ht-m1h | Review | P1 | 03 |
| BEAD-05 | ht-zyh | Tech-writer: SPEC `messages`, `run-report`, `settings`; cli.md; graph node | P2 | 04 |
| BEAD-06 | ht-1rh | Live check: `HT_LANGUAGE=ru` on the VPS, a notification in Russian | P2 | 05 |

## Bead Details

### BEAD-01
**What to do:** `Language` (StrEnum en/ru), `MESSAGES` with keys for every `render` text, the probe lines (`settings`, `portal`, `calendar`, `chrome`, `schedule`), the dry-run steps, the reasons (`Reason`) and the configuration errors; `text(key, language, **params)`; `missing_translations() -> list`; `render(report, language)`. Tests: every key in both languages, `render` under `ru` reproduces the current texts (their tests become parametrised by language), the password gets through none of the fields.
**Done when:** the tests are green and bite; domain mutations: the catalogue excluded with a reason.

### BEAD-02
**What to do:** `HT_LANGUAGE` → `Language` in Settings (an error with the variable's name); `TelegramNotifier(..., language)`; `DryRun`/`Probe` return keys and parameters; the CLI translates the output lines and the `ConfigError` messages; `horizon --help` stays English (click).
**Done when:** CLI tests in both languages; the BDD fixtures updated.

### BEAD-03 … BEAD-06
As in HT-003/HT-004.
