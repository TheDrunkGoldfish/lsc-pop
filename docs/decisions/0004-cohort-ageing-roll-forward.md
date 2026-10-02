# 0004. Cohort-ageing roll-forward (3-year shift) as default; static shares as sensitivity
Status: accepted
Date: 2026-10-01

## Context
The 2021 base must be rolled forward to mid-2024 LSOA SYOA × sex totals (S5). There's no current LSOA ethnicity source.

## Options considered
- **Cohort ageing**: ethnicity follows the person, so the share at age *a* in 2024 = the 2021 share at *a − 3*. It reflects
  the ageing of the 2021 population, and minority groups' younger profiles move up the age range.
- **Static shares**: the 2021 share at age *a* applies at age *a* in 2024. Simpler, but it ignores cohort ageing.
- **Admin-based ethnicity (ONS research)**: experimental, not at the needed detail. Context only.

## Decision
Default `variant: cohort` with `cohort_shift_years: 3` (Census day 21 Mar 2021 → 30 Jun 2024 ≈ 3.3 years).
Ages 0–2 in 2024 (born after the Census) take the LSOA's 2021 age-0 shares unless a better proxy is agreed (A03).
The 90+ group is handled explicitly: 2024 shares at 90+ pool the 2021 cohorts aged 87+ (weighted by their 2021
counts). `variant: static` is implemented as a sensitivity, and the difference is reported. Shares are applied to S5
so the outputs sum **exactly** to S5 per LSOA × sex × age.

## Note (2026-10-01, Phase 3)
`cohort_shift_years` now defaults to `null`, meaning `reference_year − 2021` (= 3 for 2024). That keeps the shift right
when the reference year moves (mid-2025 → 4; see `docs/updating.md` §A). Setting an explicit integer overrides it. The
decision itself is unchanged.

## Consequences
Can't capture post-2021 migration-driven change in composition (prominent limitation). Rounding the shift down to
three years misaligns about a quarter-year for some births.

## Related
Stage D, `config.variant`, `config.cohort_shift_years`, assumptions A01–A03. Phase 6 tests and sensitivity report.
