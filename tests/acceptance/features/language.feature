@wip @bead:ht-bsc @node:domain @node:cli
Feature: Language of the notifications and the CLI output (HT-007)
  Human-readable texts come from a message catalogue selected by HT_LANGUAGE.

  These scenarios are named by PRD HT-007, which is approved and not built yet. Until
  BEAD-03 of HT-007 lands their steps SKIP with that reason.

  Scenario: A notification is rendered in the configured language
    Given the message catalogue of HT-007 is not built yet
    Then the scenario is skipped until HT-007 BEAD-03 lands

  Scenario: The default language is English
    Given the message catalogue of HT-007 is not built yet
    Then the scenario is skipped until HT-007 BEAD-03 lands

  Scenario: Every message key has a text in every supported language
    Given the message catalogue of HT-007 is not built yet
    Then the scenario is skipped until HT-007 BEAD-03 lands

  Scenario: An unknown language is refused when the settings load
    Given the message catalogue of HT-007 is not built yet
    Then the scenario is skipped until HT-007 BEAD-03 lands
