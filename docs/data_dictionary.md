# Data dictionary

> Every table and column: type, allowed values and provenance. **Modelled estimates, not official statistics.**
> Analysts should start with **Output tables** (the star schema loaded into SQL/Databricks). Interim tables are
> pipeline internals.
>
> **Abbreviations on this page:** ADR = architecture decision record; ICB = Integrated Care Board; IMD = Index of Multiple Deprivation; IoD = English Indices of Deprivation; IPF = iterative proportional fitting; L&SC = Lancashire and South Cumbria; LAD = local authority district; LSOA = Lower layer Super Output Area; LTLA = lower-tier local authority; MSOA = Middle layer Super Output Area; ODS = NHS Organisation Data Service (code); OHID = Office for Health Improvement and Disparities; ONS = Office for National Statistics. Full definitions: [glossary](glossary.md).

## Mapping files (`config/mappings/`)

### `ethnicity_19_to_6.csv`
| Column | Type | Values | Notes |
|---|---|---|---|
| `code_19` | int | 1–19 | Census 2021 `ethnic_group_tb_20b` tick-box code, excluding "Does not apply" (−8). **Code order to be verified against RM032 in Phase 2.** |
| `label_19` | str | 19 labels | Census 2021 label |
| `code_5` | str | A, B, M, W, O | Census 2021 high-level group (Asian, Black, Mixed, White, Other) |
| `label_5` | str | | |
| `code_6` | str | A, B, M, WB, WO, O | 5 groups with White split into White British / Other White (A05, confirmed) |
| `label_6` | str | | |

### `age_bands.csv`
| Column | Type | Values | Notes |
|---|---|---|---|
| `band_set` | str | `5yr`, `10yr` | Selected in `config.age.band_sets` |
| `band_label` | str | e.g. `0-4`, `90+` | |
| `age_min`, `age_max` | int | 0–90 | Inclusive. 90 = open-ended 90+. Each set must tile 0–90 exactly (validated on load). |

## Interim tables

### `data/interim/geography/lsoa_lookup` (Stage A; `.parquet` + `.csv` + `.metadata.json`)
One row per England LSOA 2021 (33,755), sorted by `lsoa21cd`. Built by `lsc_pop.geography`.

| Column | Type | Values / example | Provenance |
|---|---|---|---|
| `lsoa21cd` | str | `E01012392` | S7 `LSOA21CD` (join key) |
| `lsoa21nm` | str | `Halton 001A` | S7 `LSOA21NM` |
| `msoa21cd`, `msoa21nm` | str | `E02…` | S7b. MSOA 2021, used for OHID catchments (S9) |
| `ltla21cd`, `ltla21nm` | str | `E07000031` (South Lakeland) | S7b `LAD22CD/NM`. 2021 LTLA (pre-2023 reorganisation), used for the IPF seed S3 (ADR-0011) |
| `rgn21cd`, `rgn21nm` | str | `E12000002` North West | S7c. ONS region of the LTLA, used for the seed fallback |
| `lad_cd`, `lad_nm` | str | `E06000064` Westmorland and Furness | S7 `LAD26CD/NM` (current vintage; ADR-0014) |
| `sicbl_cd`, `sicbl_ods`, `sicbl_nm` | str | `E38000050`, `01A` | S7 sub-ICB location |
| `icb_cd`, `icb_ods`, `icb_nm` | str | `E54000048`, `QE1`, NHS Lancashire and South Cumbria ICB | S7 ICB |
| `nhser_cd`, `nhser_ods`, `nhser_nm` | str | `E40000010`, `Y62`, North West | S7 NHS England region |
| `nhs_geog_vintage` | str | `2026-04` | `config.geography.nhs.vintage` |
| `in_footprint` | bool | | `config.footprint` (England → all True; ADR-0002) |
| `in_focus_icb` | bool | 1,060 True (L&SC) | `config.footprint.focus_icb_codes` |

### `data/interim/census/*` (Stage B; `.parquet` + `.metadata.json`)
All England, sorted by key columns. `sex` ∈ {`F`, `M`}, `eth19` ∈ 1–19 (`config/mappings/ethnicity_19_to_6.csv`),
`age` ∈ 0–90 (90 = 90+), `band` ∈ 1–5 (RM032: ≤24, 25–34, 35–49, 50–64, 65+).

| Table | Columns | Rows | Source / notes |
|---|---|---|---|
| `rm032` | lsoa21cd, sex, band, eth19, population (int) | 6,413,450 | S1 RM032, as published |
| `rm200` | lsoa21cd, sex, age, population (int) | 6,143,410 | S2 RM200, as published (age = Nomis code − 1) |
| `ts021` | lsoa21cd, eth19, population (int) | 641,345 | S4 TS021, validation only |
| `seed_age91` | ltla21cd, eth19, sex, age, population (int) | 1,040,858 | S3, 301 returned LTLAs × 19 × 2 × 91 |
| `seed_age23` | ltla21cd, eth19, sex, age23 (1–23), population (int) | 269,192 | S3 23-category fallback, 308 LTLAs × 19 × 2 × 23 |
| `seed_blocked` | ltla21cd, classification (`age_91a`/`age_23a`) | 9 | LTLAs blocked by ONS disclosure control |
| `margins` | lsoa21cd, sex, band, kind (`eth19`/`age`), key, population (float) | 12,556,860 | IPF margins after reconciliation (ADR-0015). Within each lsoa × sex × band, Σ eth19 = Σ age. |

### `data/interim/base2021/*` (Stage C)
| Table | Columns | Rows | Notes |
|---|---|---|---|
| `base` | lsoa21cd, sex, age, eth19, population (float64) | 116,724,790 | 2021 base cube (33,755 × 2 × 91 × 19), Census-day population (sums to RM200: 56,489,042). Row order = C order of dims; `provenance.read_cube` restores the array. |
| `seed_source` | ltla21cd, seed_source | 309 | `age91` · `age23_region_split` · `substitute:<ltla>` (ADR-0011) |
| `ltla_comparison` | ltla21cd, eth19, sex, age, seed, base | 1,040,858 | Base aggregated to LTLA vs the S3 seed (BAS-06) |

## Processed tables

### `data/processed/mid2024_cohort/estimates` (Stage D; `.parquet` + `.metadata.json`)
**Modelled mid-2024 population, LSOA × sex × single year × ethnic group.** Modelled estimates, not official statistics.

| Column | Type | Values | Notes |
|---|---|---|---|
| `lsoa21cd` | dictionary string | 33,755 England LSOA 2021 codes | Sorted |
| `sex` | dictionary string | `F`, `M` | |
| `age` | int16 | 0–90 | 90 = 90 and over |
| `eth19` | int16 | 1–19 | `config/mappings/ethnicity_19_to_6.csv` (code_19) |
| `population` | float64 | ≥ 0, unrounded | Σ over `eth19` = ONS mid-2024 (S5) for the LSOA × sex × age, exactly up to float error |

116,724,790 rows; total 58,620,101. The directory name carries the reference year and variant (`mid{year}_{variant}`).
Banded and 6-group outputs, deprivation and geography columns are added in Phases 7–8.

### `data/processed/mid2024_cohort/share_fallback_level`
| Column | Type | Values |
|---|---|---|
| `lsoa21cd`, `sex`, `age` | as above | |
| `fallback_level` | int16 | 0 direct · 1 LSOA × sex × RM032 band · 2 LSOA × sex all ages · 3 LSOA all · 4 LTLA × sex × age (ADR-0017) |

## Output tables: `outputs/<run_id>/tables/` (ADR-0018)

A star schema. Parquet is canonical; each table also has a `.csv`, and `fact_population` has one CSV per ICB in
`fact_population_csv/icb=<icb_cd>.csv`. Each file has a `.metadata.json` sidecar: run id, config/code/lock hashes,
reference date, variant, sources, the not-official-statistics statement and `data_hash`. `schema.sql` has the DDL
and example queries. **There are no aggregate tables**; aggregate in SQL/BI with the joins below.

```
dim_age ─┐            ┌─ dim_ethnicity
         └ fact_population ┘
                 │ lsoa21cd
              dim_lsoa ── bridge_lsoa_trust ── dim_trust
```

### `fact_population`: one row per LSOA × sex × single year × ethnic group (116,724,790 rows)
| Column | Type | Values | Notes |
|---|---|---|---|
| `lsoa21cd` | string | 33,755 England LSOA 2021 codes | FK → `dim_lsoa` |
| `sex` | string | `F`, `M` | |
| `age` | smallint | 0–90 | 90 = 90 and over. FK → `dim_age` |
| `eth19` | smallint | 1–19 | FK → `dim_ethnicity` |
| `population` | double | ≥ 0, unrounded | Σ over `eth19` = ONS mid-year estimate (S5) for the LSOA × sex × age. England total 58,620,101 (mid-2024). Small cells are highly uncertain (`limitations.md`). |
| `reference_year` | smallint | 2024 | Mid-year (30 June). Lets future years be appended. The roll-forward variant (`cohort`) isn't a column: it's in each table's `.metadata.json` and `audit`/run metadata (ADR-0020). |

### `dim_lsoa`: one row per LSOA (33,755 rows, 76 columns)
| Column(s) | Type | Notes / provenance |
|---|---|---|
| `lsoa21cd`, `lsoa21nm` | string | Key; S7 |
| `msoa21cd`, `msoa21nm` | string | MSOA 2021 (S7b), used by OHID catchments |
| `ltla21cd`, `ltla21nm`, `rgn21cd`, `rgn21nm` | string | 2021 local authority (pre-2023 reorganisation) and region (S7b, S7c); the IPF seed geography |
| `lad_cd`, `lad_nm` | string | Current LAD (April 2026 lookup) |
| `sicbl_cd`, `sicbl_ods`, `sicbl_nm` | string | Sub-ICB location (current) |
| `icb_cd`, `icb_ods`, `icb_nm` | string | ICB (current; 36 in April 2026). L&SC = `E54000048` / `QE1` |
| `nhser_cd`, `nhser_ods`, `nhser_nm` | string | NHS England region |
| `nhs_geog_vintage` | string | `2026-04` (ADR-0014) |
| `in_footprint`, `in_focus_icb` | bool | Footprint (all England) and L&SC flag (1,060 LSOAs) |
| `imd_score`, `imd_rank`, `imd_decile` | double, int, int | IoD 2025 IMD. Rank 1 / decile 1 = most deprived (national) |
| `<domain>_score`, `_rank`, `_decile` | | Domains: `income`, `employment`, `education`, `health`, `crime`, `barriers`, `living_env`; supplementary indices `idaci`, `idaopi`; sub-domains `sub_children_young_people`, `sub_adult_skills`, `sub_geographical_barriers`, `sub_wider_barriers`, `sub_indoors`, `sub_outdoors` (S8 File 7) |
| `iod_edition` | string | `IoD 2025` |
| `imd_quintile` | int | National quintile from deciles (1–2 → 1 … 9–10 → 5); 1 = most deprived |
| `core20` | bool | National IMD decile 1–2 (`deprivation.core20_max_decile`) |
| `imd_local_quintile` | int | 1–5, population-weighted within the LSOA's ICB (ADR-0008); 1 = most deprived. Each holds ~20% of the ICB's mid-year population (max deviation 0.3 pp) |
| `imd_local_quintile_within` | string | `icb` |
| `population_mid2024` | double | LSOA total from `fact_population` (= ONS S5) |

### `dim_ethnicity` (19 rows)
`eth19`, `label_19`, `code_5`/`label_5` (Census 5 high-level groups: A, B, M, W, O), `code_6`/`label_6` (A, B, M,
WB, WO, O; White split into White British / Other White incl. Irish, Gypsy or Irish Traveller, Roma; ADR-0007),
`sort_order`.

### `dim_age` (91 rows)
`age` (0–90), `age_label` (`90+` for 90), `age_5yr` (`0-4` … `85-89`, `90+`) with `age_5yr_sort`, `age_10yr`
(`0-9` … `80-89`, `90+`) with `age_10yr_sort`, `census_band_rm032` (the Census band used in IPF).

### `dim_trust` (135 rows)
`trust_code` (ODS), `trust_name`, `trust_type`, `commissioning_region`, `site_lsoa21cd` (OHID T7), `is_focus`
(OneLSC acute trusts: RXL, RXR, RXN, RTX). Includes `UNASSIGNED` (OHID suppressed and rounded flows; ADR-0019).
Lancashire & South Cumbria NHS FT (RW5) isn't an acute trust and isn't included.

### `bridge_lsoa_trust` (337,059 rows)
| Column | Type | Notes |
|---|---|---|
| `lsoa21cd`, `msoa21cd` | string | Each LSOA inherits its MSOA's OHID proportions (assumption A06) |
| `trust_code` | string | FK → `dim_trust`, incl. `UNASSIGNED` |
| `proportion_published` | double | OHID T2 share (all admissions, catchment year 2024). With `UNASSIGNED` = 1 − Σ, sums to 1 per LSOA |
| `proportion_rescaled` | double | Published ÷ Σ for the MSOA, so everyone is assigned to a listed trust. `UNASSIGNED` = 0. Sums to 1 |
| `fptp` | bool | OHID first-past-the-post trust for the MSOA |

Trust catchment = Σ `population × proportion_published` (conservative) or `× proportion_rescaled` (full). Both are
documented in ADR-0019 and `schema.sql` query 2.

### Run-level files in `outputs/<run_id>/`
`metadata.json` (run metadata + full config), `run_log.jsonl` (→ `transformations.md`), `validation.jsonl`
(→ `validation_report.md`), `output_hashes.json`, `sensitivity_variants.csv`, `sensitivity_seed_floor.csv`,
`trust_comparison_{totals,ethnicity,imd,ethnicity_diagnostic}.csv`.
