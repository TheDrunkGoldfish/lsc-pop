# 0022. Databricks-native implementation alongside the local pipeline
Status: accepted (user, 2026-10-02)
Date: 2026-10-02

## Context
The user wants the pipeline to use Databricks architecture properly: Unity Catalog, medallion layers, Lakeflow
Declarative Pipelines with expectations, lineage, and a bundle with dev/test/prod. Wrapping the local CLI in job tasks
isn't enough. The local pandas pipeline must remain the reference.

## Options considered
- **Thin wrapper** (Python wheel tasks running `lsc-pop run` against a Volume): least work, but no Databricks-native
  tables, expectations, lineage or incremental refresh.
- **Native pipeline, alongside the local reference** (chosen): bronze/silver/gold/audit tables in Unity Catalog,
  built by one Lakeflow Declarative Pipeline. A parity check against the local outputs proves equivalence.
- **Replace the local pipeline**: no Databricks-free way to reproduce, and the documented, tested reference is lost.

## Decision
`databricks/` holds a Databricks Asset Bundle (targets dev/test/prod):
- **Job** `lsc_pop_<target>`:
  1. `ingest` (Python wheel task: `lsc-pop download --mode download|verify` into the Volume, checked against the
     committed manifest);
  2. `pipeline` (the Lakeflow Declarative Pipeline).
- **Pipeline** (serverless, triggered, default publishing mode, so tables go to several schemas). By layer, with
  mixed style per the user:
  - **bronze (Python):** Auto Loader streaming tables for the Nomis CSVs and ONS-API JSON lines. Materialized views
    for xlsx, ODS, the zipped CSV and the lookups, parsed by the *same* `lsc_pop` code as locally;
  - **silver (SQL):** geography, tidy Census tables, margin reconciliation, IoD, OHID shares. Parameters come from a
    one-row `silver.params` built from the bundled `config.yaml`;
  - **model (Python):** seed on the driver (`lsc_pop.base.seed_array`), then IPF distributed with
    `groupBy(ltla21cd).applyInPandas(lsc_pop.base.fit_arrays)`;
  - **gold (SQL):** roll-forward with the ADR-0017 fallback chain; the star schema (ADR-0018);
  - **audit (SQL + Python):** checks as tables with `expect ... ON VIOLATION FAIL UPDATE` (same ids as locally);
    OHID comparisons via `lsc_pop.catchments`; run metadata; sensitivity; share fallback; source manifest.
- **Configuration:** `config/`, mappings, `sources.yaml` and `data/manifest.json` ship **inside the lsc-pop wheel**.
  The pipeline loads the same config and gets the same config hash as a local run (ADR-0023). Bundle variables set
  only *where* things live: catalog, four schemas, Volume. The catalog, schemas and Volume **must already exist**;
  the bundle never creates them.
- **Optional parity job** `lsc_pop_parity_<target>` compares gold tables with a local run's `tables/` uploaded to the
  Volume (ADR-0024).
- **Testing without a workspace:** `databricks/tests/harness.py` runs the real pipeline files in local Spark. It
  emulates materialized views, streaming tables and expectations. CI runs an end-to-end synthetic test that compares
  the two implementations, and the bundle YAML is validated against Databricks' published JSON schema.

## Consequences
- The method now has two implementations. Parity tests (synthetic in CI, real data via the parity job) keep them in
  step. **Any method change must be made in both**, and the parity test fails otherwise.
- Expectations make every hard check fail the pipeline update before bad tables are published.
- Validated locally on the full real dataset:
  - bronze → gold parity: fact max |diff| 6.4e-7 persons, dims and bridge identical;
  - all 34 Databricks checks pass;
  - the same CEN-12 soft warning as the local run.
- Not yet run on a real workspace when written. Deployment details to verify there:
  - wheel dependency paths in the pipeline `environment`;
  - Auto Loader on Volumes;
  - `applyInPandas` on serverless pipelines;
  - Free Edition quotas.

## Related
`databricks/` (README runbook), ADR-0018, ADR-0023, ADR-0024, `.github/workflows/tests.yml`.
