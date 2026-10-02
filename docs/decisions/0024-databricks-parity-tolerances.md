# 0024. Parity tolerances between the Databricks and local implementations
Status: accepted (2026-10-02)
Date: 2026-10-02

## Context
The Databricks pipeline (ADR-0022) reimplements the method in SQL and distributed Python. Bit-identical results aren't
achievable:
- IPF fitted LTLA by LTLA converges in a different number of iterations than one national batch. Each table stops once
  within tolerance.
- Spark sums floats in a different order from numpy.

## Decision
`lsc_pop_dbx.parity` (used by CI and by the optional parity job) requires:

| Table | Requirement |
|---|---|
| `fact_population` | Every (lsoa21cd, sex, age, eth19) cell present in both; \|difference\| ≤ 1e-6 persons (the IPF tolerance) |
| `dim_lsoa`, `dim_ethnicity`, `dim_age`, `dim_trust`, `bridge_lsoa_trust` | Same rows and columns; text identical, numbers within 1e-6 |

`dim_lsoa.population_mid_year` (Databricks) is compared with `population_mid<year>` (local).

## Evidence (full real data, local Spark, 2026-10-02)
- reconciled margins: 12,556,860 identical (max diff 0.0);
- 2021 base: 116,724,790 cells, max diff 6.8e-7;
- fact: 116,724,790 cells, max diff 6.4e-7, totals 58,620,101 both;
- dims and bridge: identical;
- share-fallback counts: identical.

## Related
ADR-0022, `databricks/src/pipeline/lsc_pop_dbx/parity.py`, `databricks/tests/test_pipeline_parity.py`.
