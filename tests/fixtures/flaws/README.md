# Fixtures: FLAW regression cases

Cases distilled from `add/arafix_flaws_and_failures_report.md`, adjusted where
the report string mixed multiple bugs.

| ID | Phase | Status (0.9.3) |
|----|-------|----------------|
| FLAW_01 | C (page ranges) | **pass** |
| FLAW_02 | B (lexicon) | **pass** |
| FLAW_03 | C (currency LTR) | **pass** |
| FLAW_04 | D (hybrid mojibake) | **pass** |
| FLAW_07 | B (PF tatweel) | **pass** |
| FLAW_08 | C (terminal punct) | **pass** |

`manifest.json` is the source of truth for automated tests.

**All documented FLAWs are green as of 0.9.3.**
