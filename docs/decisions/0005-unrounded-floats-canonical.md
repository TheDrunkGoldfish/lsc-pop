# 0005. Unrounded floats are canonical; no integerised output for now
Status: accepted
Date: 2026-10-01

## Context
Modelled cells are fractional. Rounding each cell independently breaks additivity. The user confirmed that
integerised output is **not** needed for now (Phase 1 review).

## Options considered
- **Floats only**: exact reconciliation to S5 and additive aggregation. Users round at presentation time.
- **Floats + controlled-rounding integers**: friendlier for some users, but it needs an algorithm, a seed and extra validation.

## Decision
Canonical outputs are unrounded float64. `rounding.integerise` stays in config (default `false`). Setting it to
`true` currently fails validation with "not implemented", so nobody gets integer output by accident. If it's needed
later, a new ADR will specify controlled rounding that preserves LSOA × sex × age totals, with a fixed `rounding.seed`.

## Consequences
Outputs show fractional people. Docs and limitations explain this and give suppression and rounding guidance for
published tables.

## Related
`config.rounding`, `limitations.md`.
