# 0015. Margin reconciliation: RM200 defines each LSOA × sex × band total
Status: accepted
Date: 2026-10-01

## Context
IPF (ADR-0003) fits ethnic group × single year of age inside each LSOA × sex × RM032 band. Its row margins (RM032
ethnic counts) and column margins (RM200 single-year counts) must have the **same band total**. Census tables are
perturbed independently (cell key perturbation, targeted record swapping), so they don't. Phase 4 analysis on all
England LSOAs (`outputs/<run_id>/run_log.jsonl`, step `census.compare_tables`):

| Comparison | Cells | Identical | Mean abs | p95 abs | Max abs | Net |
|---|---|---|---|---|---|---|
| RM032 vs RM200, LSOA × sex | 67,510 | 6.8% | 4.8 | 12 | 29 (3.8%) | +1,531 |
| RM032 vs RM200, LSOA × sex × band | 337,550 | 17.2% | 2.0 | 5 | 16 | +1,531 |
| same, L&SC only | 10,600 | 18.3% | 1.9 | 5 | 13 | +527 |
| RM032 vs TS021, LSOA × ethnic group | 641,345 | 60.4% | 0.6 | 3 | 11 | +465 |
| S3 seed vs RM032, LTLA × eth × sex × band | 57,190 | 24.3% | 2.6 | 9 | 37 | −815 |

England totals: RM032 56,490,573 · RM200 56,489,042 · TS021 56,490,108.
**No band is zero in one table and positive in the other** (0 of 337,550), so neither fallback path is triggered.

**Key finding: the choice doesn't affect the mid-2024 output.** Scaling both margins of a band to any common total T
scales the IPF solution by a constant, so the ethnic share at each single year of age is unchanged. Stage D carries
these shares forward and applies them to S5. Tested on 300 L&SC LSOA × sex × band tables with the LTLA seed: the
maximum difference in any share between the RM200, RM032 and mean options was 9 × 10⁻¹² (floating-point noise). Only
the absolute **2021 base** cube depends on the choice.

## Options considered
- **RM200 defines T**: the base reproduces RM200 sex × single year exactly, and RM032's ethnic counts are rescaled
  within each band (median 2 people). Age is the dimension rolled forward to S5, so its 2021 structure stays exact.
- **RM032 defines T**: the base reproduces RM032 ethnicity × sex × band exactly. Its total is closer to TS021.
- **Mean**: symmetric (about 1 person per band each way), but the base reproduces neither table.

## Decision
The user chose **RM200** (2026-10-01): `reconciliation.margin_source: rm200`. Both margins are scaled to
T = Σ RM200 single years in the band. RM200 is unchanged; RM032 ethnic counts are multiplied by T / Σ RM032.

Defined fallbacks for zero-inconsistent bands (none occur in the current data, but unit-tested):
- RM032 band = 0, T > 0: use the LSOA × sex ethnic mix pooled over all bands. If that's empty too, use the LTLA
  seed's ethnic mix for the sex × band.
- RM200 band = 0, T > 0 (only possible with `rm032`/`mean`): spread T over the band's single years using the LTLA seed's
  all-ethnicity age shape.
- T = 0 with RM032 > 0: those RM032 people are dropped, and the count is reported (`persons_dropped_rm032_zeroed`; 0 now).

Soft check **CEN-12** flags bands where |adjustment| > max(10 persons, 5% of the band total) (`warn_abs`,
`warn_rel`; chosen by the user). It flags 153 of 337,550 bands (0.05%), listed in `validation.jsonl`. It's a
warning only.

## Consequences
- The 2021 base sums to the RM200 total (56,489,042), 1,066 below TS021. Ethnic totals in the base differ from RM032
  and TS021 by perturbation-sized amounts. Phase 5 reports these as differences, not failures (brief §10).
- Mid-2024 outputs are invariant to this choice (above).
- If ONS re-issues RM032 or RM200, rerun the comparison. A band that's zero in one table but not the other would
  trigger the fallbacks and show up in the summary.

## Related
Stage B (`census.reconcile_margins`), `config.reconciliation.*`, checks CEN-10 to CEN-12, `tests/test_census.py`.
