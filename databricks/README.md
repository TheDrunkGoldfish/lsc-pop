# lsc-pop on Databricks

A Databricks-native implementation of the lsc-pop pipeline. It runs **alongside** the local pipeline, which stays the
reference ([ADR-0022](../docs/decisions/0022-databricks-native-implementation.md)). It produces the same star schema
in Unity Catalog, plus bronze/silver/audit layers, expectations and lineage. **Modelled estimates, not official
statistics.**

```
Lakeflow Job  lsc_pop_<target>
 ├─ ingest    Python wheel task   download (or verify) raw files into the Volume; manifest SHA-256 checks
 ├─ pipeline  Lakeflow Declarative Pipeline (serverless)
      bronze  Python  Auto Loader streaming tables (Nomis CSV, ONS JSON) + parsed xlsx/ODS/zip/lookups
      silver  SQL     geography, tidy Census, margin reconciliation, IoD, OHID shares, params/mappings
      model   Python  2021 base: IPF distributed by LTLA (applyInPandas, same numpy code as local)
      gold    SQL     roll-forward + star/snowflake schema: fact_population, dim_lsoa/ethnicity/age/trust, geography dims, bridge_lsoa_trust
      audit   SQL+Py  checks (expectations), validation, sensitivity, share fallback, run metadata
 └─ audit     Python task         OHID trust comparisons -> audit.ohid_comparison_*, audit.ohid_checks
```

## 1. Prerequisites (one-off)

1. **Databricks CLI** (v0.294+). Install it, then sign in to your workspace:
   ```bash
   brew tap databricks/tap && brew install databricks     # or see docs.databricks.com/dev-tools/cli
   databricks auth login --host https://<your-workspace>.cloud.databricks.com
   ```
2. **uv** (builds the lsc-pop wheel during deploy) and the repo checked out.
3. **Unity Catalog objects, created by you or an admin.** The bundle never creates them. For each target you need:
   - a **catalog** (defaults: `lsc_pop_dev`, `lsc_pop_test`, `lsc_pop`);
   - four **schemas** in it (defaults `bronze`, `silver`, `gold`, `audit`);
   - a **Volume** for raw files (default `<catalog>.bronze.landing`, i.e. `/Volumes/<catalog>/bronze/landing`).

   For example, in a SQL editor:
   ```sql
   CREATE CATALOG IF NOT EXISTS lsc_pop_dev;
   CREATE SCHEMA IF NOT EXISTS lsc_pop_dev.bronze;  CREATE SCHEMA IF NOT EXISTS lsc_pop_dev.silver;
   CREATE SCHEMA IF NOT EXISTS lsc_pop_dev.gold;    CREATE SCHEMA IF NOT EXISTS lsc_pop_dev.audit;
   CREATE VOLUME IF NOT EXISTS lsc_pop_dev.bronze.landing;
   ```
   Different names? Override the bundle variables (section 3).

## 2. Deploy and run

All commands run from this `databricks/` folder.

```bash
databricks bundle validate -t dev              # checks config against the workspace
databricks bundle deploy   -t dev              # builds the wheel (uv build) and deploys job + pipeline
databricks bundle run      -t dev lsc_pop_job  # ingest, then pipeline update
```

Targets:

| Target | Mode | Default catalog | Notes |
|---|---|---|---|
| `dev` | development | `lsc_pop_dev` | Resources prefixed `[dev <you>]`, schedule paused, pipeline in development mode |
| `test` | (default) | `lsc_pop_test` | Shared folder `/Workspace/Shared/.bundle/lsc_pop/test` |
| `prod` | production | `lsc_pop` | Runs as a service principal: `--var prod_service_principal=<application-id>` |

## 3. Variables

Override with `--var name=value`, or set them per target in `databricks.yml`:

| Variable | Default (dev) | Meaning |
|---|---|---|
| `catalog` | `lsc_pop_dev` | Existing catalog |
| `schema_bronze` / `schema_silver` / `schema_gold` / `schema_audit` | `bronze` / `silver` / `gold` / `audit` | Existing schemas |
| `volume_path` | `/Volumes/lsc_pop_dev/bronze/landing` | Existing Volume. Raw files go to `<volume_path>/raw/<source_id>/`, the manifest to `<volume_path>/manifest.json` |
| `ingest_mode` | `download` | `download` fetches from the publishers (needs internet access); `verify` only checks files you uploaded |
| `prod_service_principal` | — | prod only |

Settings that change the numbers (reference year, IPF, roll-forward, mappings, sources) are **not** bundle
variables. They come from `config/config.yaml`, which is built into the wheel, so Databricks and local runs share one
config and one config hash ([ADR-0023](../docs/decisions/0023-config-hash-excludes-paths.md)). To change one, edit
`config/config.yaml`, then redeploy.

## 4. If the workspace can't reach the publishers (e.g. Free Edition)

Databricks Free Edition limits outbound internet to "a limited set of trusted domains". Download locally, then
upload:

```bash
cd ..   && uv run lsc-pop download                       # local data/raw/, verified against the manifest
databricks fs cp -r data/raw dbfs:/Volumes/lsc_pop_dev/bronze/landing/raw
cd databricks && databricks bundle deploy -t dev --var ingest_mode=verify
databricks bundle run -t dev lsc_pop_job
```

`ingest_mode` is a bundle variable, so it's set at deploy time (or per target in `databricks.yml`). `verify` checks
every file's SHA-256 against the committed manifest, so a truncated or altered upload fails the job.

**Other Free Edition limits:**
- serverless only (which this bundle uses);
- one active pipeline per pipeline type (this bundle has one);
- 5 concurrent job tasks (this job runs 2 in sequence);
- **non-commercial use only**. Use an organisational workspace for NHS production.

## 5. Results

| Where | What |
|---|---|
| `<catalog>.gold.fact_population`, `dim_lsoa`, `dim_ethnicity`, `dim_age`, `dim_trust`, `bridge_lsoa_trust`, `dim_icb`, `dim_sub_icb`, `dim_nhs_region`, `dim_lad`, `dim_msoa`, `dim_ltla`, `dim_region` | The star/snowflake schema (same as `outputs/<run_id>/tables/`; `dim_lsoa.population_mid_year` = local `population_mid<year>`) |
| `<catalog>.audit.validation` | Every check with the same ids as the local validation report. A failed hard check fails the update before anything is published |
| `<catalog>.audit.run_metadata` | Config/code hashes, git commit, bundle target, refresh time |
| `<catalog>.audit.sensitivity`, `share_fallback`, `ohid_comparison_*`, `source_manifest` | Sensitivity variants, fallback usage, OHID comparisons (incl. the CAT-11 diagnostic), raw-file provenance |
| Pipeline UI → **Data quality** / Catalog Explorer → **Lineage** | Expectation results per table; lineage from raw file to gold |

Example queries are in `../src/lsc_pop/templates/schema.sql`. Use `<catalog>.gold.` as the table prefix.

### Things to know about runs

- **No automatic retries.** Job tasks have `max_retries: 0`, and the pipeline has
  `pipelines.numUpdateRetryAttempts: 0`. Failures here are deterministic (code or data), so a retry only repeats them
  and spends compute. Fix the cause, redeploy, then rerun, or repair just the failed task:
  `databricks jobs repair-run --json '{"run_id": <id>, "rerun_tasks": ["<task>"]}'`.
- **Runs aren't code snapshots.** A run fixes its task list and parameters when it starts, but each task reads its
  code (workspace files, the pipeline source, the wheel path) when it starts. Deploying while a run is in progress can
  therefore mix code versions within one run. `audit.run_metadata.code_hash` records what the pipeline actually used.
  Don't deploy to a target with a run in progress. `test` and `prod` keep the bundle's deployment lock; `dev` mode
  turns it off.
- **Pipeline dataset functions must be lazy.** Databricks calls them while analysing the graph, before upstream tables
  have data. The local harness fails any dataset function that runs a Spark job while defining its result.

## 6. Parity with the local reference (optional)

```bash
cd .. && uv run lsc-pop run                                   # local reference outputs/<run_id>/tables
databricks fs cp -r outputs/<run_id>/tables dbfs:/Volumes/lsc_pop_dev/bronze/landing/reference
cd databricks && databricks bundle run -t dev lsc_pop_parity
```

The results land in `<catalog>.audit.parity`. Requirement: fact cells within 1e-6 persons; dims and bridge identical
([ADR-0024](../docs/decisions/0024-databricks-parity-tolerances.md)).

## 7. Developing and testing locally (no workspace needed)

`tests/harness.py` runs the **real** pipeline files in local Spark. It emulates materialized views, streaming tables
and expectations.

```bash
brew install openjdk@17                                    # Spark needs Java 17+
uv sync --group databricks
uv run --group databricks pytest databricks/tests          # static checks + synthetic end-to-end parity
```

- `test_pipeline_parity.py` builds a synthetic copy of every raw source in its real format, runs the local pipeline
  and the Databricks pipeline on it, and asserts parity.
- `test_harness_and_bundle.py` validates the bundle YAML against Databricks' published JSON schema
  (`tests/bundle_schema.json`).
- CI runs both (`.github/workflows/tests.yml`, job `databricks`).

**Changing the method?** Change it in both implementations (`src/lsc_pop/` and `databricks/src/pipeline/`). The
parity test fails otherwise.

## Layout

```
databricks.yml                 bundle: variables, targets dev/test/prod, wheel artifact (path: ..)
resources/lsc_pop.job.yml      ingest → pipeline
resources/lsc_pop.pipeline.yml serverless pipeline, configuration keys lsc_pop.*
resources/lsc_pop_parity.job.yml   optional parity job
src/pipeline/transformations/  pipeline source: NN_<layer>_*.py / .sql (prefix = dependency order)
src/pipeline/lsc_pop_dbx/      helpers (bronze readers, reference tables, IPF model, audit, parity)
src/parity_task.py             parity job entry point
tests/                         harness, synthetic data, tests, bundle_schema.json
```

## 8. After renaming columns of a streaming table: full refresh

Bronze Census and seed tables are Auto Loader streaming tables. An update doesn't re-read files it has already
processed, so renaming a column there (as in ADR-0025, `ltla21cd` → `ltla21_code`) leaves the old rows with the new
column empty, and the pipeline fails later (e.g. `seed incomplete for LTLAs ...`). Run a one-off full refresh, then the
normal job:

```bash
databricks bundle run -t dev lsc_pop_pipeline --full-refresh-all
databricks bundle run -t dev lsc_pop_job
```
