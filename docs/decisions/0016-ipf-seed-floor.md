# 0016. IPF seed floor of 0.5 (continuity correction)
Status: accepted (user, 2026-10-01)
Date: 2026-10-01

## Context
The seed (ADR-0011) is the LTLA's published count for each ethnic group × sex × single year. Minority groups in
small LTLAs have many zero cells (26% of all seed cells are zero) (e.g. no Roma women aged 47 in a district). A zero seed cell stays zero under IPF,
so a zero can make a table **infeasible**: an LSOA whose RM032 margin has, say, 2 Roma women aged 35–49 when the LTLA
seed has none in the band. With a floor of 0, the unit test `test_zero_floor_with_sparse_seed_can_be_infeasible` and
real L&SC tables fail. A small floor added to every seed cell avoids that, and also smooths noise in the small,
perturbed LTLA counts.

## Evidence (Stage C sensitivity; focus ICB refitted; `docs/sensitivity.md` §1 and §4)
| Floor | MAE vs S3 at LTLA × eth × sex × age | Max change in any 2021 share vs 0.5 | Effect on mid-2024 L&SC 6-group totals vs 0.5 |
|---|---|---|---|
| 0.01 | 1.35 | 0.55 | ≤ 0.17% (Black −19 people) |
| **0.5** | 1.48 | – | – |
| 2.0 | 1.68 | 0.23 | ≤ 0.50% (Black +57 people) |
| uniform seed (no LTLA shape) | 2.55 | 0.53 | not run |

- The MAE column is **partly circular**: the seed *is* the S3 table, so a smaller floor reproduces it more closely
  by construction. That doesn't show it's more accurate for LSOAs.
- The uniform seed is clearly worse (MAE 2.55), so the LTLA age shape adds real information.
- At the aggregates people will use (ICB × 6 groups), the floor choice moves totals by at most 0.5%. Individual
  LSOA × single-year cells can change a lot (share changes up to 0.55), but those cells are already flagged as
  unreliable (limitations §3).

## Options considered
- **0.01**: almost no smoothing, so it follows the noisy LTLA zeros and small counts closely.
- **0.5**: the standard half-count continuity correction (Jeffreys-type). Measured on the seed (LTLA × sex × single
  year), the median cell is 614 for White British and 28 for Other White, but only 0–8 for every other group.
  26% of all seed cells are zero, including 52% for Gypsy or Irish Traveller and 56% for Roma. So the floor mainly
  matters for small groups, where 0.5 is comparable to the data.
- **2.0**: heavier smoothing that pulls minority age shapes toward uniform within a band.

## Decision
`ipf.seed_floor: 0.5`, added to every seed cell before fitting. `ipf.sensitivity_floors: [0.01, 0.5, 2.0]` reruns the
comparison on every run (Stage C `sensitivity_seed_floor.csv`; Stage D focus-ICB roll-forward).

## Consequences
Every table is feasible: 0 infeasible tables and at most 32 iterations to tolerance 1e-6 across England. A minority
group with zero LTLA seed in a band is spread across the band in proportion to the other groups' age shape, modified by
the floor. What would change our mind: an independent finer-age source (e.g. an MSOA single-year table) showing a
different floor fits better.

## Related
`config.ipf.seed_floor`, `config.ipf.sensitivity_floors`, `lsc_pop.base`, `tests/test_base.py`, assumption A13.
