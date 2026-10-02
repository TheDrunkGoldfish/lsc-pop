# 0011. IPF seed: LTLA ethnicity × sex × single year of age, with fallbacks for blocked LTLAs
Status: accepted
Date: 2026-10-01

## Context
Within each LSOA × sex × RM032 band, IPF needs a seed giving each ethnic group's relative age shape across the single
years in that band (ADR-0003). Brief §4 S3 asked for the finest geography with ethnicity × sex × finer age that isn't
heavily blanked. ONS custom-dataset API results (England, 20 ethnic groups × sex × age):

| Geography | single year (91a) | 23 bands | 18 bands | 8 bands | 6 bands | RM032 5 bands |
|---|---|---|---|---|---|---|
| LTLA (2021) | 8 blocked of 309 | 1 blocked | 1 | 1 | 1 | 0 |
| MSOA (sample of 686) | ~all blocked | 41% | 31% | 8.6% | 1.3% | 0% |
| LSOA | refused | – | – | – | 84% | 0% |

The API blocks **whole areas**, not cells. No published RM-series LTLA table gives ethnicity × single year.

## Options considered
- **LTLA × single year**: exact single years 0–90+, near-complete coverage. Coarse geography: every LSOA in an LTLA
  shares the same within-band shape for each ethnic group (the counts still come from the LSOA's own RM032/RM200).
- **MSOA × 8 bands**: finer geography, but 8 bands are no finer than RM032 for most adults.
- **Hybrid** (MSOA 8-band refined by the LTLA single-year shape): more complex and harder to explain, for a small gain.

## Decision
The user chose LTLA × single year (2026-10-01).
- **Primary seed:** `resident_age_91a` at LTLA 2021 (S3 file `ltla21_eth20_sex_age91.jsonl.gz`).
- **Fallback 1:** for the 7 English LTLAs blocked at 91a but returned at 23 bands (E07000026, E07000029, E07000030,
  E07000046, E07000047, E07000166, E07000167), use the LTLA's own 23-band counts. Split each band into single years
  using the single-year shape **for the same ethnic group × sex in the LTLA's region**, summed over the region's
  returned LTLAs. The 23 bands nest inside the RM032 bands (breaks at 24/25, 34/35, 49/50, 64/65), and the top band is
  85+, which is split to 85–89 and 90+ the same way.
- **Fallback 2:** Isles of Scilly (E06000053) is blocked at every level finer than RM032, so it uses Cornwall
  (E06000052)'s single-year seed.
- A seed cell that is 0 where both margins are positive gets a small floor (value set in Phase 5 and recorded in
  config), so IPF can place people the margins require. Structural zeros from zero margins stay zero (ADR-0003).
- Seed source and fallback are recorded per LSOA (`seed_source` column in the interim base).
- The LTLA 2021 code for each LSOA comes from S7b (OA21 → LSOA21 → MSOA21 → LAD Dec 2021 exact fit), **not** S7. S7
  carries LAD 2026, where Cumbria, North Yorkshire and Somerset districts have been merged. S7b's 309 English LAD codes
  match the API's LTLA 2021 list exactly. In L&SC this matters for Barrow-in-Furness (E07000027) and South Lakeland
  (E07000031), which are now part of Westmorland and Furness.

## Consequences
The within-band age shape is homogeneous across an LTLA's LSOAs (assumption A04). Fallback LTLAs are rural and have
small minority populations, so the effect is small; it will be quantified in Phase 5. The same data supports the
brief §10 check of the 2021 base aggregated to LA against LA ethnicity × age × sex.

## Related
S3 in `config/sources.yaml`, Stage C (`ipf.py`), assumption A04, Phase 5 validation.
