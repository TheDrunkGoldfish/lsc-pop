# 0003. IPF within LSOA × sex × broad age band, implemented in-house in numpy
Status: accepted
Date: 2026-10-01

## Context
No public table gives LSOA × sex × single year × ethnicity. RM032 gives LSOA × sex × ethnicity (20 categories) × 5
broad bands (≤24, 25–34, 35–49, 50–64, 65+). RM200/TS009 gives LSOA × sex × single year. Inside each LSOA × sex ×
RM032 band, the unknown is a 2-D table, ethnic group × single years in that band, with known row margins (RM032) and
column margins (RM200).

## Options considered
- **IPF / raking with an informative seed** (ethnicity-specific age shape from S3): a standard, transparent method.
  The solution is the minimum-information adjustment of the seed that matches both margins.
- **Uniform seed**: assumes every ethnic group has the same within-band age shape. That's clearly wrong for ≤24, where
  minority groups are much younger.
- **Regression / microsimulation**: more assumptions, harder to explain, and no better data to support it.
- **Third-party IPF package**: an opaque dependency for a ~50-line algorithm.

## Decision
Raking within each LSOA × sex × band, seeded by S3 (the choice of S3 source and its interpolation to single years
gets its own ADR in Phase 2/5). Implemented as a small, vectorised numpy function (`ipf.py`) with unit tests on toy
tables, an explicit convergence tolerance and iteration cap (`config.ipf`), logging of iterations and max margin
error, and a loud failure on non-convergence. Zero margins give structural zeros.

## Consequences
The 2021 base reproduces the reconciled RM032 and RM200 margins within tolerance. The within-band age split relies
on the seed (assumption A04). Margins must be reconciled first, since IPF can't fit inconsistent totals (Phase 4 ADR).

## Related
Stage C, `config.ipf.tolerance`, `config.ipf.max_iter`, `tests/test_ipf.py` (Phase 5).
