# 0020. Drop the `variant` column from `fact_population`
Status: accepted (user, 2026-10-02; supersedes the `variant` column in ADR-0018)
Date: 2026-10-02

## Context
ADR-0018 gave `fact_population` `reference_year` and `variant` columns so later releases could be appended to one
table. The user chose to publish the cohort variant only (static stays a documented sensitivity), so `variant` was
`cohort` on all 116.7M rows. In Parquet/Delta that costs nothing, but it adds ~0.8 GB to the per-ICB CSVs and nothing
for analysts.

## Options considered
- Keep it (harmless in Parquet; useful only if variants are ever mixed in one table).
- **Drop `variant`, keep `reference_year`.** Appending mid-2025 is a realistic plan; mixing variants isn't.
- Replace both with an `estimate_id` key and a `dim_estimate` table (cleanest if many releases are held together).

## Decision
Drop `variant` from `fact_population` (Parquet, CSVs and `schema.sql`). Keep `reference_year`. The variant stays
recorded in every table's `.metadata.json` (`variant` field), the run's `metadata.json` (full config) and the
processed directory name (`data/processed/mid2024_cohort/`).

## Consequences
If a non-default variant is ever loaded alongside the default, either reintroduce a column or adopt the
`estimate_id` / `dim_estimate` design (a good fit for the Databricks build). `data_hash` for `fact_population` is
unchanged, because constant columns aren't part of the cube hash; the population values are identical.

## Related
`lsc_pop.outputs`, `src/lsc_pop/templates/schema.sql`, `docs/data_dictionary.md`, ADR-0018.
