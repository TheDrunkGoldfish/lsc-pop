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
One row per England LSOA 2021 (33,755), sorted by `lsoa21_code`. Built by `lsc_pop.geography`.

| Column | Type | Values / example | Provenance |
|---|---|---|---|
| `lsoa21_code` | str | `E01012392` | S7 `LSOA21CD` (join key) |
| `lsoa21_name` | str | `Halton 001A` | S7 `LSOA21NM` |
| `msoa21_code`, `msoa21_name` | str | `E02…` | S7b. MSOA 2021, used for OHID catchments (S9) |
| `ltla21_code`, `ltla21_name` | str | `E07000031` (South Lakeland) | S7b `LAD22CD/NM`. 2021 LTLA (pre-2023 reorganisation), used for the IPF seed S3 (ADR-0011) |
| `rgn21_code`, `rgn21_name` | str | `E12000002` North West | S7c. ONS region of the LTLA, used for the seed fallback |
| `lad_code`, `lad_name` | str | `E06000064` Westmorland and Furness | S7 `LAD26CD/NM` (current vintage; ADR-0014) |
| `sicbl_code`, `sicbl_ods_code`, `sicbl_name` | str | `E38000050`, `01A` | S7 sub-ICB location |
| `icb_code`, `icb_ods_code`, `icb_name` | str | `E54000048`, `QE1`, NHS Lancashire and South Cumbria ICB | S7 ICB |
| `nhser_code`, `nhser_ods_code`, `nhser_name` | str | `E40000010`, `Y62`, North West | S7 NHS England region |
| `nhs_geog_vintage` | str | `2026-04` | `config.geography.nhs.vintage` |
| `in_footprint` | bool | | `config.footprint` (England → all True; ADR-0002) |
| `in_focus_icb` | bool | 1,060 True (L&SC) | `config.footprint.focus_icb_codes` |

### `data/interim/census/*` (Stage B; `.parquet` + `.metadata.json`)
All England, sorted by key columns. `sex` ∈ {`F`, `M`}, `eth19` ∈ 1–19 (`config/mappings/ethnicity_19_to_6.csv`),
`age` ∈ 0–90 (90 = 90+), `band` ∈ 1–5 (RM032: ≤24, 25–34, 35–49, 50–64, 65+).

| Table | Columns | Rows | Source / notes |
|---|---|---|---|
| `rm032` | lsoa21_code, sex, band, eth19, population (int) | 6,413,450 | S1 RM032, as published |
| `rm200` | lsoa21_code, sex, age, population (int) | 6,143,410 | S2 RM200, as published (age = Nomis code − 1) |
| `ts021` | lsoa21_code, eth19, population (int) | 641,345 | S4 TS021, validation only |
| `seed_age91` | ltla21_code, eth19, sex, age, population (int) | 1,040,858 | S3, 301 returned LTLAs × 19 × 2 × 91 |
| `seed_age23` | ltla21_code, eth19, sex, age23 (1–23), population (int) | 269,192 | S3 23-category fallback, 308 LTLAs × 19 × 2 × 23 |
| `seed_blocked` | ltla21_code, classification (`age_91a`/`age_23a`) | 9 | LTLAs blocked by ONS disclosure control |
| `margins` | lsoa21_code, sex, band, kind (`eth19`/`age`), key, population (float) | 12,556,860 | IPF margins after reconciliation (ADR-0015). Within each lsoa × sex × band, Σ eth19 = Σ age. |

### `data/interim/base2021/*` (Stage C)
| Table | Columns | Rows | Notes |
|---|---|---|---|
| `base` | lsoa21_code, sex, age, eth19, population (float64) | 116,724,790 | 2021 base cube (33,755 × 2 × 91 × 19), Census-day population (sums to RM200: 56,489,042). Row order = C order of dims; `provenance.read_cube` restores the array. |
| `seed_source` | ltla21_code, seed_source | 309 | `age91` · `age23_region_split` · `substitute:<ltla>` (ADR-0011) |
| `ltla_comparison` | ltla21_code, eth19, sex, age, seed, base | 1,040,858 | Base aggregated to LTLA vs the S3 seed (BAS-06) |

## Processed tables

### `data/processed/mid2024_cohort/estimates` (Stage D; `.parquet` + `.metadata.json`)
**Modelled mid-2024 population, LSOA × sex × single year × ethnic group.** Modelled estimates, not official statistics.

| Column | Type | Values | Notes |
|---|---|---|---|
| `lsoa21_code` | dictionary string | 33,755 England LSOA 2021 codes | Sorted |
| `sex` | dictionary string | `F`, `M` | |
| `age` | int16 | 0–90 | 90 = 90 and over |
| `eth19` | int16 | 1–19 | `config/mappings/ethnicity_19_to_6.csv` (code_19) |
| `population` | float64 | ≥ 0, unrounded | Σ over `eth19` = ONS mid-2024 (S5) for the LSOA × sex × age, exactly up to float error |

116,724,790 rows; total 58,620,101. The directory name carries the reference year and variant (`mid{year}_{variant}`).
Banded and 6-group outputs, deprivation and geography columns are added in Phases 7–8.

### `data/processed/mid2024_cohort/share_fallback_level`
| Column | Type | Values |
|---|---|---|
| `lsoa21_code`, `sex`, `age` | as above | |
| `fallback_level` | int16 | 0 direct · 1 LSOA × sex × RM032 band · 2 LSOA × sex all ages · 3 LSOA all · 4 LTLA × sex × age (ADR-0017) |

## Output tables: `outputs/<run_id>/tables/` (ADR-0018)

A star schema. Parquet is canonical; each table also has a `.csv`, and `fact_population` has one CSV per ICB in
`fact_population_csv/icb=<icb_code>.csv`. Each file has a `.metadata.json` sidecar: run id, config/code/lock hashes,
reference date, variant, sources, the not-official-statistics statement and `data_hash`. `schema.sql` has the DDL
and example queries. **There are no aggregate tables**; aggregate in SQL/BI with the joins below.

```
dim_age ─┐            ┌─ dim_ethnicity
         └ fact_population ┘
                 │ lsoa21_code
              dim_lsoa ── bridge_lsoa_trust ── dim_trust
        ┌────────┼─────────┬─────────┐            │ host_icb_code
    dim_msoa  dim_lad  dim_sub_icb    │            │
        │                  │         │            │
    dim_ltla               └───── dim_icb ─────────┘
        │                           │
    dim_region                 dim_nhs_region
```
Geography is snowflaked (ADR-0025): each level's names live once in its own table. `dim_lsoa` holds the keys
`msoa21_code`, `ltla21_code`, `lad_code`, `sicbl_code` and `icb_code`, and the levels above them (region, NHS region)
are reached through `dim_ltla` and `dim_icb`. Column names end in `_code` / `_name` (ODS codes `_ods_code`).
To split `fact_population` by ICB: `JOIN dim_lsoa USING (lsoa21_code) JOIN dim_icb USING (icb_code)`.

### `fact_population`: one row per LSOA × sex × single year × ethnic group (116,724,790 rows)
| Column | Type | Values | Notes |
|---|---|---|---|
| `lsoa21_code` | string | 33,755 England LSOA 2021 codes | FK → `dim_lsoa` |
| `sex` | string | `F`, `M` | |
| `age` | smallint | 0–90 | 90 = 90 and over. FK → `dim_age` |
| `eth19` | smallint | 1–19 | FK → `dim_ethnicity` |
| `population` | double | ≥ 0, unrounded | Σ over `eth19` = ONS mid-year estimate (S5) for the LSOA × sex × age. England total 58,620,101 (mid-2024). Small cells are highly uncertain (`limitations.md`). |
| `reference_year` | smallint | 2024 | Mid-year (30 June). Lets future years be appended. The roll-forward variant (`cohort`) isn't a column: it's in each table's `.metadata.json` and `audit`/run metadata (ADR-0020). |

### `dim_lsoa`: one row per LSOA (33,755 rows, 62 columns)
| Column(s) | Type | Notes / provenance |
|---|---|---|
| `lsoa21_code`, `lsoa21_name` | string | Key; S7 |
| `msoa21_code` | string | FK → `dim_msoa` (MSOA 2021, S7b; used by OHID catchments) |
| `ltla21_code` | string | FK → `dim_ltla` (2021 local authority, pre-2023 reorganisation; the IPF seed geography). Shortcut: also reachable through `dim_msoa` |
| `lad_code` | string | FK → `dim_lad` (current LAD, April 2026 lookup) |
| `sicbl_code` | string | FK → `dim_sub_icb` (sub-ICB location) |
| `icb_code` | string | FK → `dim_icb`. Shortcut: also reachable through `dim_sub_icb`; check OUT-07 verifies they agree. L&SC = `E54000048` |
| `nhs_geog_vintage` | string | `2026-04` (ADR-0014) |
| `imd_score`, `imd_rank`, `imd_decile` | double, int, int | IoD 2025 IMD. Rank 1 / decile 1 = most deprived (national) |
| `<domain>_score`, `_rank`, `_decile` | | Domains: `income`, `employment`, `education`, `health`, `crime`, `barriers`, `living_env`; supplementary indices `idaci`, `idaopi`; sub-domains `sub_children_young_people`, `sub_adult_skills`, `sub_geographical_barriers`, `sub_wider_barriers`, `sub_indoors`, `sub_outdoors` (S8 File 7) |
| `iod_edition` | string | `IoD 2025` |
| `imd_quintile` | int | National quintile from deciles (1–2 → 1 … 9–10 → 5); 1 = most deprived |
| `core20` | bool | National IMD decile 1–2 (`deprivation.core20_max_decile`) |
| `imd_local_quintile` | int | 1–5, population-weighted within the LSOA's ICB (ADR-0008); 1 = most deprived. Each holds ~20% of the ICB's mid-year population (max deviation 0.3 pp) |
| `imd_local_quintile_within` | string | `icb` |
| `population_mid2024` | double | LSOA total from `fact_population` (= ONS S5) |

### Geography dimensions (ADR-0025)
Each is one row per code, built from the geography lookup. Parent keys are FKs to the next level up.
| Table (rows) | Columns | Notes |
|---|---|---|
| `dim_icb` (36) | `icb_code`, `icb_ods_code`, `icb_name`, `nhser_code`, `is_footprint`, `is_focus` | ICB (April 2026). `is_focus` = L&SC (1,060 LSOAs); `is_footprint` = in the configured footprint (all England). L&SC = `E54000048` / `QE1` |
| `dim_sub_icb` (106) | `sicbl_code`, `sicbl_ods_code`, `sicbl_name`, `icb_code` | Sub-ICB location → ICB |
| `dim_nhs_region` (7) | `nhser_code`, `nhser_ods_code`, `nhser_name` | NHS England region |
| `dim_lad` (296) | `lad_code`, `lad_name` | Current local authority district (April 2026) |
| `dim_msoa` (6,856) | `msoa21_code`, `msoa21_name`, `ltla21_code` | MSOA 2021 → LTLA 2021 |
| `dim_ltla` (309) | `ltla21_code`, `ltla21_name`, `rgn21_code` | Lower-tier local authority 2021 → region |
| `dim_region` (9) | `rgn21_code`, `rgn21_name` | ONS region |

### `dim_ethnicity` (19 rows)
`eth19`, `label_19`, `code_5`/`label_5` (Census 5 high-level groups: A, B, M, W, O), `code_6`/`label_6` (A, B, M,
WB, WO, O; White split into White British / Other White incl. Irish, Gypsy or Irish Traveller, Roma; ADR-0007),
`sort_order`.

### `dim_age` (91 rows)
`age` (0–90), `age_label` (`90+` for 90), `age_5yr` (`0-4` … `85-89`, `90+`) with `age_5yr_sort`, `age_10yr`
(`0-9` … `80-89`, `90+`) with `age_10yr_sort`, `census_band_rm032` (the Census band used in IPF).

### `dim_trust` (135 rows)
`trust_code` (ODS), `trust_name`, `trust_type`, `commissioning_region`, `site_lsoa21_code` (OHID T7), `is_focus`
(OneLSC acute trusts: RXL, RXR, RXN, RTX), `host_icb_code`. Includes `UNASSIGNED` (OHID suppressed and rounded flows;
ADR-0019), whose `host_icb_code` is NULL. Lancashire & South Cumbria NHS FT (RW5) isn't an acute trust and isn't
included.

**`host_icb_code`** (FK → `dim_icb`) is the one ICB whose geography the trust is located in: the active NHS ODS
relationship "is located in the geography of" (S10, snapshot 2026-10-03; ADR-0025). It is **not a reporting line**.
NHS trusts are independent bodies and ODS has no "reports to" relationship. It differs from the *catchment*: a trust's
patients live in many ICBs (`bridge_lsoa_trust` × `dim_lsoa.icb_code`). Use whichever you mean; `schema.sql` query 4
shows both. All 134 trusts have exactly one host ICB (CAT-12), and it matches the ICB of the trust's main-site LSOA
(CAT-13).

### `bridge_lsoa_trust` (337,059 rows)
| Column | Type | Notes |
|---|---|---|
| `lsoa21_code`, `msoa21_code` | string | Each LSOA inherits its MSOA's OHID proportions (assumption A06) |
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

## Databricks tables (`databricks/`; ADR-0022)
The gold tables match the star schema above: same columns, plus `reference_year` on `fact_population`. One
difference: `dim_lsoa.population_mid_year` here is `population_mid<year>` locally.

| Schema | Tables |
|---|---|
| bronze | `rm032_raw`, `rm200_raw`, `seed_raw`, `seed_blocked_raw` (Auto Loader streaming tables); `seed_requested_raw`, `ts021_raw`, `lookup_nhs_raw`, `lookup_census_raw`, `lookup_ltla_region_raw`, `iod_raw`, `mye_raw`, `mye_broad_raw`, `ohid_t1_raw`, `ohid_t2_raw`, `ohid_t5_raw`, `ohid_t6_raw`, `ohid_t7_raw`. Each row carries `_source_file` and `_ingested_at` |
| silver | `params` (one row of config settings + hashes), `map_ethnicity`, `map_age`, `source_age_map`, `lsoa_geography`, `rm032`, `rm200`, `ts021`, `seed_age91`, `seed_age23`, `seed_blocked`, `mye`, `census_band_totals`, `census_margins`, `base_2021`, `iod`, `ohid_shares` |
| gold | `fact_population`, `dim_lsoa`, `dim_ethnicity`, `dim_age`, `dim_trust`, `bridge_lsoa_trust` (private: `rf_level0`, `rf_shares`) |
| audit | `validation` (all checks), `checks_geography`, `checks_census`, `checks_model`, `checks_outputs`, `ohid_checks`, `run_metadata`, `source_manifest`, `sensitivity`, `share_fallback`, `ohid_comparison_{totals,ethnicity,imd,ethnicity_diagnostic}`, `parity` (parity job) |

