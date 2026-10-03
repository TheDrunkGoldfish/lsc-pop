# CLAUDE.md

Modelled LSOA × sex × single-year-of-age × ethnicity population estimates. **England-wide**, with Lancashire & South
Cumbria (L&SC ICB + OneLSC trusts) as the reporting/validation focus. The full kick-off brief is `PROJECT_BRIEF.md`; the
narrative is in `docs/`. Keep this file short.

## Commands
- `uv sync` · `uv run pytest -q` · `uv run ruff check . && uv run ruff format --check .`
- `uv run lsc-pop run [--stage <key>]` · `uv run lsc-pop docs` · `uv run lsc-pop validate` · `uv run lsc-pop compare-runs A B` · `uv run lsc-pop clean [--yes]` (also `python -m lsc_pop`)

## Layout
`config/config.yaml` (+ `config/mappings/*.csv`) → `src/lsc_pop/` (one module per stage; `provenance.py` = step logger
+ sidecars; `config.py` = pydantic schema + hash) → `data/{raw,interim,processed}` (gitignored; `data/manifest.json`
kept) → `outputs/<run_id>/` → `docs/` (ADRs in `docs/decisions/`).

## Rules (brief §3)
1. Verify sources against the live publisher, then record URL, release, file and SHA-256 in the manifest / `docs/data_sources.md`.
2. Nothing that changes the numbers without an ADR (`docs/decisions/NNNN-*.md`). Values go in config, not code.
3. Every transformation runs inside `provenance.logged_step` (rows and population totals in/out, notes).
4. Ask the user before deciding the brief's §9 open questions or anything expensive to undo.
5. Deterministic stages, fixed seeds, `uv.lock` committed. Outputs sorted, so the hashes are stable.
6. `data/raw/` is written once by `download.py` and never edited.
7. Every output is labelled "modelled estimates, not official statistics" (sidecar via `provenance.write_output`).

## Project state
- Git repo, public at github.com/TheDrunkGoldfish/lsc-pop (ADR-0021). Never commit data/raw, outputs or secrets. CI runs lint + tests.
- Phases (brief §8): 1 scaffold ✅ · 2 sources ✅ · 3 geography ✅ · 4 census ✅ · 5 IPF ✅ · 6 roll-forward ✅ · 7 IoD/catchments ✅ · 8 outputs/docs ✅.
  Stop for review at the end of each phase.
- Settled: mid-2024 only; SYOA + 5yr + 10yr bands; ethnicity 19 + 6 (6 = 5 groups with White split WB/WO); floats only;
  local IMD quintile within ICB; margins reconciled to RM200 band totals (ADR-0015); internal audience; Parquet + CSV (LSOA cube CSV split by ICB).
- Sources: `config/sources.yaml` is the register. `uv run lsc-pop download [-s S5]` fetches, then `uv run lsc-pop docs`.
  Raw files are read-only. Census LSOA tables come via the Nomis API, the seed via the ONS API (ADR-0010/0011).
  Geography is April 2026 (S7) plus the Dec 2021 OA/LSOA/MSOA/LAD lookup (S7b) for MSOA21 and LTLA21, plus LTLA→region
  (S7c); S10 = ODS directory snapshot for the trust → host ICB link. Column names end `_code` / `_name`. Lookups are config-driven (`config.geography`) with vintage-free columns (`icb_code`, `lad_code`; ADR-0014).
- Stage outputs live in `data/interim/<stage>/` and are written with `provenance.write_output`. Checks go through
  `validate.check(ctx, ...)` into `outputs/<run_id>/validation.jsonl`. Read raw files with `download.raw_file`, which
  verifies the hash.
- Big arrays (LSOA × sex × age × eth) are `provenance.Cube`, written with `write_cube`/`read_cube`. Stage C = `base.py`
  (uses the pure `ipf.py`); Stage D = `rollforward.py`. Stage F = `deprivation.py`, G = `catchments.py`, outputs = `outputs.py` (star schema with snowflaked geography and `dim_trust.host_icb_code`; no aggregates; ADR-0018, ADR-0025).
- `uv run lsc-pop run` runs every stage (~2 min once data is downloaded). Then `uv run lsc-pop docs` regenerates
  `transformations.md`, `validation_report.md`, `sensitivity.md`, `data_sources.md` and figures.
- New releases or geography changes: follow `docs/updating.md`.
- Databricks implementation in `databricks/` (ADR-0022). **Method changes must be made in both** `src/lsc_pop/` and
  `databricks/src/pipeline/`. Test with `uv run --group databricks pytest databricks/tests` (needs Java 17; Homebrew
  `openjdk@17`). Files in `transformations/` run in numeric-prefix order in the local harness.
- After changing CLI commands or options, run `uv run lsc-pop docs` (regenerates the README command reference;
  `tests/test_docs.py` fails otherwise). Define new acronyms in `docs/glossary.md`.
