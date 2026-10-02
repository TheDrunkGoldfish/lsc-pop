# 0018. Outputs as a star schema for SQL/Databricks; no pre-built aggregate tables
Status: accepted, `variant` column superseded by ADR-0020 (supersedes brief §5.8 "aggregate to ICB / place / LA / trust" tables and ADR-0013's aggregate-CSV bullet)
Date: 2026-10-01

## Context
The brief planned aggregate tables for ICB, sub-ICB, LA and trust. The user (2026-10-01) will load the outputs into
SQL/Databricks and aggregate in the BI layer, so pre-built aggregates aren't needed. They chose a star schema, the
cohort variant only, and full single-year × 19-group CSVs split by ICB (ADR-0013).

## Decision
Each run writes `outputs/<run_id>/tables/`:

| Table | Grain | Rows (mid-2024) | Purpose |
|---|---|---|---|
| `fact_population` | LSOA × sex × single year × eth19 | 116,724,790 | `population` (float64), plus a `reference_year` column so later years can be appended (`variant` column removed by ADR-0020) |
| `dim_lsoa` | LSOA | 33,755 | Current NHS/admin geography (ICB, sub-ICB, LAD, NHS region; vintage), Census-era MSOA21/LTLA21/region, IoD 2025 (IMD + domains: score, rank, decile; IMD quintile), `core20`, within-ICB population-weighted IMD quintile, flags |
| `dim_ethnicity` | eth19 | 19 | 19 → 6 → 5 group codes and labels |
| `dim_age` | single year | 91 | 5-year and 10-year band labels, RM032 band |
| `dim_trust` | acute trust | 134 + 1 | ODS code, name, OHID trust type, `is_focus` (OneLSC), plus a `UNASSIGNED` member |
| `bridge_lsoa_trust` | LSOA × trust | ~300k | `proportion_published`, `proportion_rescaled` (ADR-0019) |

- Parquet is canonical. CSVs are written for every table. `fact_population` CSVs are split by ICB (`fact_population_csv/icb=<ICB code>.csv`).
- `schema.sql` holds `CREATE TABLE` statements and example queries (ICB × 6 groups × 5-year bands; trust catchment ×
  ethnicity; IMD quintile × ethnicity).
- Every table has a `.metadata.json` sidecar (ADR-0009) carrying the not-official-statistics statement.
- No aggregate tables are produced. Validation still aggregates internally to check reconciliation (every
  footprint and trust total reconciles to its LSOAs) and to compare with OHID.

## Consequences
Analysts must join and aggregate, so `schema.sql` and `data_dictionary.md` give the joins. Small cells are
exposed at full detail, which is acceptable for an internal analyst audience (ADR-0013). Disclosure guidance is in
`limitations.md`.

## Related
`lsc_pop.outputs`, ADR-0005, ADR-0013, ADR-0019.
