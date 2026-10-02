# lsc-pop: modelled LSOA population by sex, age and ethnic group

> **Modelled estimates, not official statistics.** These figures combine Census 2021 tables, Office for National
> Statistics (ONS) small-area population estimates and other public sources through statistical modelling. Small
> cells (one area × one year of age × one ethnic group) are highly uncertain. Read
> [`docs/limitations.md`](docs/limitations.md) before use.
>
> New to the terminology? See the **[glossary](docs/glossary.md)**.

A reproducible Python pipeline that produces **population estimates for every 2021 Lower layer Super Output Area
(LSOA, small areas of ~1,500 people) in England by sex × single year of age (0–90+) × ethnic group (Census 2021,
19 groups and a 6-group aggregation)** for mid-2024. It adds the English Indices of Deprivation (IoD) 2025 and NHS
acute trust catchment shares. Outputs are a **star schema** (one fact table plus lookup tables) for SQL/Databricks.
Any aggregation, e.g. to Integrated Care Board (ICB), sub-ICB, local authority, trust catchment or deprivation
quintile, is done in the business intelligence (BI) layer ([ADR-0018](docs/decisions/0018-star-schema-outputs-no-aggregates.md);
an ADR is an architecture decision record, see `docs/decisions/`).

**Lancashire and South Cumbria (L&SC)** is the priority footprint for reporting and validation: NHS L&SC ICB and the
OneLSC acute trusts. The worked examples and comparisons focus on it, but the model covers all of England
([ADR-0002](docs/decisions/0002-footprint-england-with-lsc-focus.md)).

**How the numbers are made, in one paragraph.** Census 2021 gives each LSOA's ethnic mix only in five broad age
bands, and its age structure only for all ethnic groups combined. *Iterative proportional fitting (IPF)* combines the
two into ethnic group × single year of age, using each ethnic group's age pattern in the local authority as a guide.
That 2021 mix is then carried forward with each age cohort and applied to ONS's mid-2024 estimates, so every output
adds up exactly to the official totals. The full method is in [`docs/methodology.md`](docs/methodology.md).

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Scaffold: tooling, config, provenance, docs, ADRs | done |
| 2 | Source discovery & download | done |
| 3 | Geography: LSOA lookup, footprint, checks | done |
| 4 | Census ingest & margin reconciliation | done |
| 5 | 2021 base by iterative proportional fitting (IPF) | done |
| 6 | Roll-forward to mid-2024 (cohort; static sensitivity) | done |
| 7 | Deprivation (IoD 2025, Core20 = most deprived 20%, local quintile) & acute trust catchments from the Office for Health Improvement and Disparities (OHID) | done |
| 8 | Star-schema outputs, generated docs, reproducibility check | done |
| 9 | Databricks-native implementation (`databricks/`): Lakeflow pipeline, Unity Catalog, bundle | built and verified locally; first workspace deploy pending |

## How to use

### How it works
- **This is a Python package with a command-line tool.** The code is in `src/lsc_pop/` (one module per pipeline
  stage), and `uv` installs it into a project virtual environment (`.venv/`) along with exact dependency versions from
  `uv.lock`.
- **You don't run individual scripts.** You run the `lsc-pop` command, which reads `config/config.yaml` and runs the
  stages in order:

```
download → geography → census → ipf → rollforward → (mid2025: off) → deprivation → catchments → outputs
 data/raw/   data/interim/…                           data/processed/                        outputs/<run_id>/tables/
```

- **Each stage reads the previous stage's saved files,** so you can rerun from any stage.
- **Every run writes a new `outputs/<run_id>/`** with its tables, logs and checks. Earlier runs are never overwritten.

### One-off setup
Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.12 itself.

```bash
git clone https://github.com/TheDrunkGoldfish/lsc-pop.git
cd lsc-pop
uv sync                     # creates .venv with the exact pinned versions
uv run pytest               # optional: unit tests (~2 s)
uv run lsc-pop download     # ~0.5 GB, ~20-40 min. Every file is checked against data/manifest.json
```

### Producing the outputs
```bash
uv run lsc-pop run          # all stages, ~2 min -> outputs/<run_id>/
uv run lsc-pop validate     # summary of that run's checks (exit code 1 if any hard check failed)
uv run lsc-pop docs         # regenerate docs/validation_report.md, transformations.md, sensitivity.md, figures
```

Then load `outputs/<run_id>/tables/*.parquet` into SQL/Databricks. `tables/schema.sql` has the table definitions
(`CREATE TABLE` statements) and example queries: ICB × ethnicity × age band, trust catchments, and Index of Multiple
Deprivation (IMD) quintile.

### Three ways to run it (all equivalent)
| Option | Commands | When to use |
|---|---|---|
| **`uv run`** (recommended) | `uv run lsc-pop run` | From the repo root. Uses `.venv` automatically; nothing to activate. From elsewhere: `uv run --project /path/to/lsc-pop lsc-pop run` |
| Activated virtual environment | `source .venv/bin/activate`, then `lsc-pop run` or `python -m lsc_pop run` | Interactive work in a terminal |
| Python | `from lsc_pop.config import load_config` … (see below) | Notebooks, or reading results in your own analysis |

All three work from any working directory. Paths are resolved from the repo root, not from where you run the command.

### Common tasks
Every command and option is listed in the [command reference](#command-reference) below.

| I want to… | Do this |
|---|---|
| Rerun everything after changing `config/config.yaml` | `uv run lsc-pop run` (downloads are skipped if already present) |
| Rerun one stage | `uv run lsc-pop run -s <stage>`, e.g. `-s ipf`. Later stages read its saved output, so run them too (or run everything) |
| See what will run | `uv run lsc-pop run --help`; the stage list prints at the start of every run |
| Check a run | `uv run lsc-pop validate`, or open `docs/validation_report.md` after `lsc-pop docs` |
| Prove a rerun is identical | `uv run lsc-pop compare-runs outputs/<run A> outputs/<run B>` |
| Free disk space from old runs | `uv run lsc-pop clean` (dry run), then `uv run lsc-pop clean --yes`. Removes `tables/` (~4.5 GB each) from every run except the latest, keeping logs, checks and hashes |
| Use a new mid-year estimates (MYE) release, new ICB lookup, new IoD | Follow [`docs/updating.md`](docs/updating.md) (config + source registry; no code changes) |
| Use a different config | `uv run lsc-pop run --config path/to/other.yaml` (keep it inside a `config/` folder of a repo copy, so relative paths resolve) |

### Using the results from Python
```python
from lsc_pop.config import load_config
from lsc_pop.report import latest_complete_run
import pandas as pd

cfg = load_config()  # config/config.yaml
tables = latest_complete_run(cfg) / "tables"  # newest outputs/<run_id>/tables
fact = pd.read_parquet(
    tables / "fact_population.parquet", filters=[("lsoa21cd", "==", "E01012581")]
)  # one LSOA (3,458 rows)
lsoa = pd.read_parquet(tables / "dim_lsoa.parquet")
eth = pd.read_parquet(tables / "dim_ethnicity.parquet")
lsc = (
    fact.merge(lsoa[lsoa.in_focus_icb][["lsoa21cd"]])  # L&SC only
    .merge(eth[["eth19", "label_6"]])
    .groupby("label_6")["population"]
    .sum()
)
```
The full England fact table is 116.7M rows, about 1 GB in memory as pandas. Filter on read (as above), or use
DuckDB/Databricks for full-table queries.

### Where things are
| Path | What |
|---|---|
| `config/config.yaml`, `config/mappings/`, `config/sources.yaml` | Every setting that affects the numbers; mapping tables; the source register |
| `data/raw/` | Downloaded files, read-only, never edited (`data/manifest.json` holds their SHA-256) |
| `data/interim/`, `data/processed/` | Stage outputs (rebuilt by `lsc-pop run`) |
| `outputs/<run_id>/` | Final tables + run log, checks, sensitivity and OHID comparisons |
| `docs/` | Methodology, decisions (ADRs), data dictionary, limitations, generated reports |
| `databricks/` | The Databricks implementation (bundle, pipeline source, local test harness) |

## Databricks

The same pipeline also runs **natively on Databricks**, alongside this local version (which stays the reference). It's
a Databricks Asset Bundle in [`databricks/`](databricks/README.md):
- a **Lakeflow Declarative Pipeline** with bronze (Python, Auto Loader), silver (SQL), the IPF model (Python,
  distributed by `applyInPandas`), gold (SQL star schema) and audit layers in Unity Catalog;
- every check as an **expectation** that fails the update before bad tables are published;
- **dev, test and prod** targets. The catalog, schemas and Volume are configurable and must already exist.

The settings that change the numbers come from the same `config/config.yaml` (bundled in the wheel). A parity check
holds the Databricks gold tables to the local outputs: cells within 1e-6 people; dimensions identical. See the
[runbook](databricks/README.md) and [ADR-0022](docs/decisions/0022-databricks-native-implementation.md).

## Command reference

<!-- cli-reference:start (generated by `lsc-pop docs`; don't edit by hand) -->

Run any command as `uv run lsc-pop <command> [options]` from the repo root, or `python -m lsc_pop <command>` inside the activated `.venv`. Every command accepts `--help`.

| Command | What it does |
|---|---|
| `lsc-pop run` | Run the pipeline: every stage in order, or just one with --stage. |
| `lsc-pop download` | Download raw source files into data/raw/ and record them in data/manifest.json. |
| `lsc-pop docs` | Regenerate the generated docs and figures from the latest complete run. |
| `lsc-pop validate` | Summarise the checks of the latest complete run (exit code 1 if any hard check failed). |
| `lsc-pop clean` | Free disk space by deleting previous runs' output tables (dry run unless --yes). |
| `lsc-pop compare-runs` | Check two runs produced identical output tables (compares their data hashes). |

#### `lsc-pop run`

Run the pipeline: every stage in order, or just one with --stage.

Each run writes a new outputs/<run_id>/ folder (tables, run log, checks). A failed hard
check stops the run. Stages read the previous stage's saved files, so a single stage can
be rerun, but later stages must then be rerun too.

| Option | Description | Default |
|---|---|---|
| `--stage`, `-s` | Run only this stage (one of: download, geography, census, ipf, rollforward, mid2025, deprivation, catchments, outputs). | – |
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

#### `lsc-pop download`

Download raw source files into data/raw/ and record them in data/manifest.json.

Files already present (with a matching SHA-256 hash) are skipped. Raw files are read-only
and never overwritten. A changed or tampered file stops with an error. With --mode verify,
nothing is downloaded and every file must already be in place (e.g. uploaded to a Volume).

| Option | Description | Default |
|---|---|---|
| `--source`, `-s` | Source id(s) from config/sources.yaml to fetch; repeat for several (-s S5 -s S7). Default: all enabled sources. | – |
| `--raw-dir` | Put raw files here instead of data/raw/ (e.g. a /Volumes/... path). | – |
| `--manifest` | Manifest file to use (seeded from the committed data/manifest.json if missing). | – |
| `--mode` | download: fetch missing files. verify: fetch nothing; check files already in place (e.g. uploaded to a Volume) against the manifest. | `download` |
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

#### `lsc-pop docs`

Regenerate the generated docs and figures from the latest complete run.

Writes docs/data_sources.md, sensitivity.md, transformations.md, validation_report.md,
docs/figures/*.png and the command reference in README.md.

| Option | Description | Default |
|---|---|---|
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

#### `lsc-pop validate`

Summarise the checks of the latest complete run (exit code 1 if any hard check failed).

The checks themselves run inside `lsc-pop run`; this only reports them.

| Option | Description | Default |
|---|---|---|
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

#### `lsc-pop clean`

Free disk space by deleting previous runs' output tables (dry run unless --yes).

By default removes outputs/<run_id>/tables/ from every run except the latest, and keeps each
run's small provenance files (metadata, run log, checks, hashes).

| Option | Description | Default |
|---|---|---|
| `--keep`, `-k` | Keep tables of the N most recent runs. | `1` |
| `--include-latest` | Also remove the latest run's tables (same as --keep 0). | off |
| `--whole-runs` | Delete entire run directories (logs, checks too), not just tables/. | off |
| `--yes`, `-y` | Actually delete. Without it: dry run. | off |
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

#### `lsc-pop compare-runs`

Check two runs produced identical output tables (compares their data hashes).

Exit code 0 if identical, 1 if any table differs. Writes outputs/reproducibility_check.json.

| Option | Description | Default |
|---|---|---|
| `RUN_A` (argument) | outputs/<run_id> directory | required |
| `RUN_B` (argument) | outputs/<run_id> directory (e.g. from a clean checkout) | required |
| `--config`, `-c` | Config file (must sit in a config/ folder). Default: the repo's config/config.yaml. | `config/config.yaml` |

**Stages** (for `lsc-pop run --stage`), in run order:

| Stage | Step |
|---|---|
| `download` | Download raw sources (skips files already present) & check manifest |
| `geography` | A. LSOA geography lookup (ICB, sub-ICB, LAD, MSOA) & footprint |
| `census` | B. Census 2021 tables: tidy, check, reconcile totals |
| `ipf` | C. 2021 base by iterative proportional fitting (IPF) |
| `rollforward` | D. Roll forward to the mid-year (cohort ageing) & sensitivity |
| `mid2025` | E. Provisional mid-2025 variant (disabled in config; ADR-0006) |
| `deprivation` | F. Indices of Deprivation 2025, Core20, local quintile |
| `catchments` | G. Acute trust catchments (OHID) & comparison |
| `outputs` | Write star-schema tables (Parquet + CSV) & schema.sql |

<!-- cli-reference:end -->

## Updating: new releases and geography changes

The step-by-step runbook is in **[`docs/updating.md`](docs/updating.md)**. In short:

- **Mid-2025 (and later) LSOA population estimates.** These aren't published yet; ONS lists them as provisional for
  Dec 2026 to Jan 2027. When they're released:
  1. register the new file in `config/sources.yaml` and run `uv run lsc-pop download -s <ID>`;
  2. set `reference_year: 2025` and update `mye.source`/`mye.file`/`mye.edition` in `config/config.yaml`. The
     cohort-ageing shift updates automatically (2025 − 2021 = 4 years);
  3. write an ADR superseding ADR-0006, then re-run.

  See [updating.md §A](docs/updating.md#a-moving-to-a-new-mid-year-eg-mid-2025-lsoa-estimates).
- **ICB / sub-ICB mergers, new local authority district (LAD) codes.** Register the new ONS LSOA21 → sub-ICB location
  (SICBL) → ICB → LAD lookup, then point
  `geography.nhs` in `config/config.yaml` at it, updating the raw column names (e.g. `ICB26CD` → `ICB27CD`). No code
  changes are needed. Re-run and review the geography checks (GEO-01 to GEO-12). See
  [updating.md §B](docs/updating.md#b-nhs-geography-changes-icb--sub-icb-mergers-new-lad-codes).
- **Trust catchments and trust mergers** ([§C](docs/updating.md#c-hospital-trust-catchments-ohid-and-trust-mergers)),
  **LSOA boundary changes** ([§D](docs/updating.md#d-lsoa-boundary-changes-major-not-a-routine-update)), and
  **IoD, ethnicity mapping and age bands** ([§E](docs/updating.md#e-other-periodic-inputs)).

## Outputs

Each run writes to `outputs/<run_id>/`.

### Run ids
Format: `YYYYMMDDTHHMMSSZ_<config8>_<code8>`, e.g. `20261002T140512Z_282797bf_9c1d04ab`.

| Part | Meaning | Changes when |
|---|---|---|
| `YYYYMMDDTHHMMSSZ` | Run start time in UTC (Coordinated Universal Time) | every run |
| `<config8>` | First 8 characters of the **config hash**, a SHA-256 fingerprint of `config/config.yaml`, the mapping files and `config/sources.yaml` | a setting, mapping or registered source changes |
| `<code8>` | First 8 characters of the **code hash**, a fingerprint of the package source (`src/lsc_pop/`) | the code changes (method, checks, bug fixes) |

Two runs with the same `<config8>_<code8>` used identical settings and code. Each run's `metadata.json` has the
full hashes, plus `uv_lock_hash` (exact dependency versions). Whether the *numbers* changed is shown by each table's
`data_hash` (`output_hashes.json`; compare with `lsc-pop compare-runs`). Runs before 2026-10-02 have only the
config part.


| Path | Contents |
|---|---|
| `tables/fact_population.parquet` | LSOA × sex × single year × 19 ethnic groups, mid-2024 (116.7M rows; unrounded; sums to ONS) |
| `tables/fact_population_csv/icb=<code>.csv` | The same, as one CSV per ICB |
| `tables/dim_lsoa`, `dim_ethnicity`, `dim_age`, `dim_trust`, `bridge_lsoa_trust` (`.parquet` + `.csv`) | Geography + IoD 2025, ethnicity 19→6→5, age bands, trusts, LSOA×trust catchment shares |
| `tables/schema.sql` | Table definitions (`CREATE TABLE`) + example queries |
| `*.metadata.json` (one per table) | run id, config/code/lock hashes, reference date, variant, sources, data hash, the not-official-statistics statement |
| `run_log.jsonl`, `validation.jsonl`, `metadata.json`, `output_hashes.json` | Step log (rows and population in/out), check results, run metadata + full config, table hashes |
| `sensitivity_*.csv`, `trust_comparison_*.csv` | Sensitivity runs and OHID comparisons |

Column definitions: [`docs/data_dictionary.md`](docs/data_dictionary.md). Disclosure guidance for anything published
from these tables: [`docs/limitations.md`](docs/limitations.md) §8.

## Documentation

| Doc | What's in it |
|---|---|
| [methodology](docs/methodology.md) | Method in plain English, worked example, technical annex |
| [glossary](docs/glossary.md) | Terms and acronyms (LSOA, ICB, IPF, OHID, Core20…) |
| [data_sources](docs/data_sources.md) | Source register (S1–S9, plus S5b, S7b, S7c, S7d) |
| [decisions/](docs/decisions/) | Architecture decision records (ADRs): one per decision that affects the numbers |
| [assumptions](docs/assumptions.md) | Assumptions register |
| [transformations](docs/transformations.md) | Generated from the run log |
| [data_dictionary](docs/data_dictionary.md) | Every output column |
| [validation_report](docs/validation_report.md) | Generated validation results |
| [limitations](docs/limitations.md) | Caveats for users |
| [sensitivity](docs/sensitivity.md) | Generated: cohort vs static, newborn proxy, seed floor |
| [updating](docs/updating.md) | Runbook: new mid-year estimates, lookup/boundary changes, mappings |
| [databricks/README](databricks/README.md) | Deploying and running the Databricks implementation |
| [CHANGELOG](docs/CHANGELOG.md) | Changes |

## Licence

- **Code:** MIT ([`LICENSE`](LICENSE)).
- **Documentation:** Open Government Licence (OGL) v3.0 ([`LICENSE-docs.md`](LICENSE-docs.md)).
- **Input data:** isn't included in the repository; `lsc-pop download` fetches it. It's published under the OGL
  v3.0 by ONS, the Ministry of Housing, Communities and Local Government (MHCLG) and OHID, and contains public sector
  information licensed under the OGL v3.0.
- **Outputs** are modelled estimates, not official statistics.
