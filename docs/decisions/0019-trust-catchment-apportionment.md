# 0019. Trust catchments: MSOA proportions applied to LSOAs; published shares plus "unassigned", with rescaled column
Status: accepted (user, 2026-10-01)
Date: 2026-10-01

## Context
OHID (S9) publishes, for each MSOA 2021 × acute trust, the proportion of the MSOA's admitted patients treated at the
trust (all ages, 3-year pooled HES). Each MSOA's proportions sum to a mean of 0.978 (England min 0.881, max 0.997; L&SC
0.961–0.993), because trust–MSOA cells under 8 patients are suppressed and proportions are rounded to 3 dp. OHID's
own trust totals are 1–4% above the sum of their published MSOA rows (RXL +3.0%, RXR +1.1%, RXN +1.7%, RTX +3.9%),
which confirms the gap is mostly real, suppressed flows.

## Decision
- **Admission type:** all admissions only. **Catchment year:** 2024, the latest (HES FY2022/23–2024/25).
- **Geography:** each LSOA takes its MSOA 2021's proportions (S7b). Every LSOA, sex, age and ethnic group within an
  MSOA is assumed to use each trust in the same proportion (assumption A06). OHID's age/sex-specific proportions
  aren't published.
- **`bridge_lsoa_trust`** carries both:
  - `proportion_published`, as OHID publishes it, **plus a `UNASSIGNED` row** holding 1 − Σ. This sums to 1 per
    LSOA, so trust totals plus unassigned reconcile exactly to the population (option C);
  - `proportion_rescaled` = published ÷ Σ for that MSOA, so every resident is assigned to a listed trust
    (UNASSIGNED = 0; option B). Use it to compare with OHID's headline totals or for "full" denominators.
- `fptp` (first past the post) is carried from OHID for reference.
- **Comparators:** trust totals vs OHID T1 (mid-2022 populations, so expect ~1–3% growth); trust ethnicity (5
  groups) vs OHID T5 under **both** OHID selection methods (FPTP is the valid comparator; see the finding below) ("All (5% and above)" and "First past the post"); mean
  IMD 2025 score vs OHID T6. These are reported in `validation_report.md` and aren't pass/fail.

## Finding: OHID's "All (5% and above)" ethnicity isn't comparable (2026-10-02)
| % Asian | RXL | RXR | RXN | RTX |
|---|---|---|---|---|
| FPTP: modelled / OHID | 1.9 / 1.8 | 22.2 / 21.3 | 9.2 / 8.8 | 2.0 / 2.1 |
| All (5% and above): modelled / OHID | 2.0 / 8.5 | 22.7 / 10.8 | 8.9 / 8.8 | 2.0 / 3.8 |

- FPTP agrees for all trusts (median |diff| ≈ 0.1 pp), so our MSOA-level ethnicity matches OHID's inputs.
- The "All (5% and above)" figures don't agree, yet the same 5%-threshold, share-weighted method reproduces OHID's
  T6 IMD scores to within 1 point.
- Whole-MSOA (unweighted) counting doesn't explain the gap either.
- The pipeline therefore tests whether OHID used a coarser ethnic mix (check CAT-11,
  `trust_comparison_ethnicity_diagnostic.csv`, `validation_report.md`). Mean |diff| across 128 trusts × 5 groups:

| Ethnic mix taken at | LSOA (ours) | MSOA | LTLA | upper-tier LA | sub-ICB | **ICB** | NHS region |
|---|---|---|---|---|---|---|---|
| Mean |diff| (pp) | 2.47 | 2.47 | 2.29 | 2.24 | 2.11 | **1.90** | 2.63 |

Smoothing to large areas moves the figures towards OHID, and ICB-level smoothing explains RXL, RXR and RXN, but no
single geography reproduces the table (RTX in particular). OHID's method for this table is unpublished. **Decision:**
validate trust ethnicity against OHID **FPTP** only, and treat "All (5% and above)" as not comparable. Users comparing
our trust ethnicity with OHID's dashboard should expect large gaps for some trusts (e.g. RXR). It may be worth raising
with OHID.

## Consequences
Trust totals from `proportion_published` undercount OHID-style catchments by about 2%. `proportion_rescaled` slightly
favours each area's main trusts. The docs explain both, and analysts choose the column.

## Related
`lsc_pop.catchments`, `bridge_lsoa_trust`, `dim_trust`, assumptions A06, A08, checks CAT-01 onward.
