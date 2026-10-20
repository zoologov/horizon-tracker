# PRD: HT-007 — Language of the notifications and the CLI output (i18n)

> **Status:** Approved
> **Created:** 2026-10-20

---

## Problem

The Telegram notification texts and the CLI lines (probe, dry-run, configuration errors) are written
in Russian right in the code. The project is becoming impersonal and English-language (the repository clean-up), while the owner
wants to read the notifications in their own language. The language needs to be a setting.

## Impact

Any adopter gets English messages by default; the owner sets `HT_LANGUAGE=ru`
and sees the previous Russian texts. The language does not affect the behaviour of the service.

## Goals

- [ ] Every text a person sees (the notifications, the `probe` lines, the `--dry-run` plan,
      the configuration error messages) comes from the message catalogue, not from literals in the logic.
- [ ] The language is set by `HT_LANGUAGE` (`en` by default, `ru` supported); an unknown language
      is refused when the settings load, with the variable's name.
- [ ] Every catalogue key has a text in both languages; a test checks completeness.
- [ ] The logs (stderr, journald) stay English and do not depend on the language.

## Non-goals

- Translating the repository documentation (the repository clean-up), translating the logs, picking the language from the system locale,
  languages other than `en` and `ru` in this work (the catalogue is extensible).

## User Stories

### US-1: The owner's language
**As** the owner, **I want** to receive the notifications in Russian with `HT_LANGUAGE=ru`,
**so that** I can read them as before.

**Acceptance criteria** (each references a scenario in `tests/acceptance/features/`):
- [ ] Scenario: `A notification is rendered in the configured language`
- [ ] Scenario: `The default language is English`

### US-2: A complete catalogue
**As** an adopter, **I want** no message to fall through into another language,
**so that** the output is uniform.

**Acceptance criteria**:
- [ ] Scenario: `Every message key has a text in every supported language`
- [ ] Scenario: `An unknown language is refused when the settings load`

## Acceptance Criteria (overall)

Behaviour-bearing criteria are scenarios; the suite holds their text and this list references
them by name. `beadloom lint` reports a referenced scenario the suite does not contain.

- [ ] Scenario: `A notification is rendered in the configured language`
- [ ] Scenario: `The default language is English`
- [ ] Scenario: `Every message key has a text in every supported language`
- [ ] Scenario: `An unknown language is refused when the settings load`

**Non-behavioural criteria** stay checkboxes and are labelled, so the absence of a scenario is
a stated decision rather than a gap:

- [ ] `git grep` over `src/` finds no Cyrillic outside the message catalogue — non-behavioural: a property of the tree.
