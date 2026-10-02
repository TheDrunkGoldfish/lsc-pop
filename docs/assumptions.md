# Assumptions register

> **Abbreviations on this page:** ADR = architecture decision record; IMD = Index of Multiple Deprivation; L&SC = Lancashire and South Cumbria; LSOA = Lower layer Super Output Area; LTLA = lower-tier local authority; MSOA = Middle layer Super Output Area; OHID = Office for Health Improvement and Disparities. Full definitions: [glossary](glossary.md).

Every assumption that affects the numbers, its likely impact, and whether a sensitivity test exists.

| ID | Assumption | Where | Impact | Sensitivity tested? | ADR |
|---|---|---|---|---|---|
| A01 | Ethnicity follows the person: a cohort's 2021 ethnic mix carries forward unchanged with ageing | Stage D | High where post-2021 migration changed composition | Yes: static variant, e.g. Mixed −8.6% England (`sensitivity.md` §1–3) | 0004 |
| A02 | 3-year age shift (`reference_year − 2021`) approximates Census day (21 Mar 2021) → mid-2024 (30 Jun 2024), ≈ 3.3 years | Stage D | Low–moderate (one-year misalignment for ~30% of the cohort) | No (shift is integer by design) | 0004 |
| A03 | Ages 0–2 in mid-2024 (born after the Census) take the 2021 age-0 ethnic shares of their LSOA | Stage D | Moderate for young, fast-changing areas | Yes: ages 0–4 proxy changes L&SC ages 0–9 by −2.3% to +3.2% by group | 0004, 0017 (proposed) |
| A04 | Within each RM032 band, an LSOA's ethnic group × sex age shape is that of its 2021 LTLA (S3) | Stage C | Moderate, highest in the 0–24 band | Yes: uniform seed is much worse (MAE 2.55 vs 1.48 at LTLA; `sensitivity.md` §4) | 0003, 0011 |
| A05 | "6-group" ethnicity = Census 5 high-level groups with White split into White British / Other White (incl. Irish, Gypsy/Traveller, Roma) | Outputs | Presentation only (no effect on 19-group numbers) | n/a | 0007 (confirmed) |
| A06 | OHID MSOA 2021 all-age catchment proportions apply unchanged to every LSOA, sex, age and ethnic group within the MSOA | Stage G | Moderate: OHID's own proportions vary by age/sex but only all-age ones are published | No (no age-specific OHID data) | 0019 |
| A08 | Handling of the ~2% of each MSOA not assigned to any of the 134 trusts (suppressed cells and rounding): leave unassigned vs renormalise to 1 | Stage G | ~2% on trust totals | Both provided: `proportion_published` (+ UNASSIGNED) and `proportion_rescaled` | 0019 |
| A07 | Within-ICB local IMD quintiles are population-weighted, using mid-2024 total population | Stage F | Defines local quintile membership | n/a | 0008 |

| A09 | For the 7 English LTLAs blocked at single year of age, within-band single-year shape = region's shape for the same ethnic group × sex, applied to the LTLA's own 23-band counts; Isles of Scilly uses Cornwall's seed | Stage C | Low (small rural LTLAs; 6 L&SC LSOAs in former Copeland) | No | 0011 |
| A10 | Census RM032 "Does not apply" is checked as total − Σ(19 groups) = 0, because Nomis omits the −8 category | Stage B | None if the check passes | n/a | 0010 |
| A11 | Census perturbation noise is the only reason RM032 and RM200 band totals differ. Rescaling RM032 ethnic counts within each band to the RM200 total keeps the ethnic mix | Stage B | Base levels only (median 2 people per band); mid-2024 shares unaffected (ADR-0015 invariance test) | Yes: RM200 vs RM032 vs mean, max share diff 9e-12 | 0015 |
| A12 | Where an LSOA × sex had nobody at the source age in 2021, its ethnic shares come from the same LSOA × sex in the wider RM032 band (then all ages, LSOA, LTLA) | Stage D | 0.22% of mid-2024 people use the band fallback; 7 people use all ages | No | 0017 (proposed) |
| A13 | Seed floor 0.5 added to every LTLA seed cell | Stage C | ≤ 0.5% on L&SC 6-group totals between floors 0.01 and 2 | Yes (`sensitivity.md` §1, §4) | 0016 (proposed) |
| A14 | Local IMD quintiles weight LSOAs by mid-2024 total population and order them by national IMD rank | Stage F | Defines quintile membership near cut points | n/a | 0008 |

