# Changelog

All notable changes to the pipeline and its outputs. Changes that affect the numbers reference an ADR.

## [Unreleased]

### 2026-10-02: run ids with code hash; command reference; glossary
- Run ids are now `<UTC time>_<config hash[:8]>_<code hash[:8]>`, so code changes are visible in the folder name.
- README **Command reference**: every command, option and stage, generated from the CLI by `lsc-pop docs`. A test
  fails if it's stale. CLI help text expanded.
- New `docs/glossary.md`. Acronyms are spelled out on first use in the README, and each hand-written doc has an
  "Abbreviations on this page" line. Generated docs link to the glossary.

### 2026-10-02: `lsc-pop clean`
- New `lsc-pop clean` command (`lsc_pop.housekeeping`). By default it's a dry run, and `--yes` deletes. It removes
  old runs' `tables/` but keeps their provenance files and the latest run; options `--keep N`, `--include-latest`,
  `--whole-runs`. The README explains the run-id format (timestamp + config-hash prefix).

### 2026-10-02: drop `variant` column (ADR-0020)
- `fact_population` no longer carries the constant `variant` column (Parquet, CSVs, `schema.sql`). The variant
  remains in metadata. Fact CSVs shrink by ~0.8 GB. Population values and table hashes are unchanged.

### 2026-10-02: OHID ethnicity diagnostic and usage docs
- CAT-11 diagnostic (`catchments.ohid_5pct_diagnostic`): tests which geography's ethnic mix reproduces OHID's
  "All (5% and above)" T5. ICB smoothing fits best (mean |diff| 1.90 vs 2.47 pp), but none reproduces it. Conclusion
  recorded in ADR-0019: compare with OHID FPTP only. Added source S7d (LAD→county/unitary lookup; diagnostic only).
- `python -m lsc_pop` entry point; README "How to use" section. Output data unchanged (hashes identical).

### Phase 8: Outputs & docs (2026-10-01)
- `lsc_pop.outputs`: star schema in `outputs/<run_id>/tables/` (`fact_population` 116,724,790 rows, `dim_lsoa`,
  `dim_ethnicity`, `dim_age`, `dim_trust`, `bridge_lsoa_trust`). Parquet + CSV, with fact CSVs per ICB, plus
  `schema.sql` with DDL and example queries (verified to run in DuckDB). Checks OUT-01 to OUT-06.
- Generated docs: `transformations.md`, `validation_report.md` (brief §10 checklist), `sensitivity.md`, and
  figures in `docs/figures/`, all via `lsc-pop docs`. New `lsc-pop validate` and `lsc-pop compare-runs`.
- Data dictionary, methodology §3.5–3.8, limitations §8–10 (disclosure guidance, catchments), README quick start.
- ADR-0018 (star schema; no aggregate tables) and ADR-0019 (trust apportionment), both user decisions.
- Reproducibility verified: a clean checkout re-downloaded byte-identical raw data and reproduced identical hashes
  for all 6 output tables.

### Phase 7: Deprivation & catchments (2026-10-01)
- Stage F (`lsc_pop.deprivation`): IoD 2025 (all indices, domains and sub-domains), national quintile, Core20,
  population-weighted within-ICB quintile. Checks DEP-01 to DEP-04.
- Stage G (`lsc_pop.catchments`): streaming ODS reader (`lsc_pop.ods`), MSOA→LSOA catchment bridge with
  `UNASSIGNED` and rescaled proportions, `dim_trust`, comparison with OHID T1/T5/T6. Checks CAT-01 to CAT-10.
- ADR-0016 and ADR-0017 accepted.

### Phase 6: Roll-forward (2026-10-01)
- Stage D (`lsc_pop.rollforward`): reads S5 for `reference_year` (checked against accredited S5b, which matches exactly),
  computes cohort or static ethnic shares with pooled source ages and a 4-level fallback, and applies them to S5.
  Output `data/processed/mid2024_cohort/estimates` (116.7M rows; sums exactly to S5, total 58,620,101).
- Sensitivity: static vs cohort, newborn proxy (0 vs 0–4), seed floor (0.01/0.5/2) → `outputs/<run>/sensitivity_variants.csv`,
  rendered to `docs/sensitivity.md` by `lsc-pop docs`.
- ADR-0017 (proposed): source-age pooling, share fallbacks, newborn proxy.
- Worked example (Blackburn with Darwen 002A) and plain-English method in `methodology.md`.
- `mid2025` stage is skipped when disabled, not reported as unimplemented.

### Phase 5: IPF base 2021 (2026-10-01)
- `lsc_pop.ipf.ipf_fit`: vectorised batch IPF with validation of totals and feasibility, structural zeros, and loud
  non-convergence. 13 unit tests (closed-form 2×2, odds-ratio preservation, zeros, infeasible, batch = separate,
  scaling invariance).
- Stage C (`lsc_pop.base`): LTLA seed with ADR-0011 fallbacks (301 single-year, 7 regional split, Scilly → Cornwall),
  seed floor, a fit per band. England converges in ≤ 32 iterations. Max error 8.8e-7 vs RM032, 2e-13 vs RM200.
  Checks BAS-01 to BAS-09.
- Dense-cube provenance (`provenance.Cube`, `write_cube`, `read_cube`): array hashing and chunked long-format Parquet.
- ADR-0016 (proposed): seed floor 0.5, with sensitivity.

### Phase 4: Census ingest & harmonisation (2026-10-01)
- Stage B (`lsc_pop.census`): tidy RM032, RM200, TS021 and the S3 seeds (single year + 23-band) into
  `data/interim/census/`. Integrity checks CEN-01 to CEN-08 all pass on the real data.
- Cross-table discrepancy analysis (CEN-09; ADR-0015 table): RM032 vs RM200 band totals differ by a mean of 2 people
  (max 16), and no zero-inconsistent bands.
- Margin reconciliation to RM200 totals (ADR-0015, user decision), with defined fallbacks and the soft check CEN-12
  (max(10 persons, 5%); 153 bands flagged). Shown to leave the mid-2024 ethnic shares unchanged (max diff 9e-12).
- `config/mappings/census_age_classifications.csv` (RM032 bands, 23-category ages). `reconciliation.warn_abs` and
  `warn_rel` replace `max_adjustment_warn`.

### Phase 3: Geography (2026-10-01)
- Stage A (`lsc_pop.geography`): England LSOA 2021 lookup with current NHS/admin geography (S7, April 2026),
  Census-era MSOA21/LTLA21 (S7b) and LTLA region (S7c), plus footprint and focus flags. Output
  `data/interim/geography/lsoa_lookup`.
- Validation checks GEO-01 to GEO-12, recorded in `outputs/<run_id>/validation.jsonl`. Hard failures stop the run.
- Lookups are config-driven with vintage-free column names (ADR-0014, partly superseding ADR-0012).
- Added S7c (LAD Dec 2022 → region) for the ADR-0011 seed fallback.
- `mye` config section (S5 file/sheet), and `cohort_shift_years` now derived from `reference_year` by default.
- New runbook `docs/updating.md`, linked from the README: new mid-year estimates, NHS geography changes, trust
  catchments, LSOA boundary changes, mappings.

### Phase 2: Source discovery & download (2026-10-01)
- Every source verified against the live publisher. The source register is `config/sources.yaml`, rendered to
  `docs/data_sources.md`.
- `download.py`: `http`, `nomis_paged` and `ons_api_batched` fetchers; immutable raw files (SHA-256 manifest,
  read-only, refuses to overwrite); row-count checks against Nomis `RECORD_COUNT`.
- Added S5b (accredited broad-age LSOA estimates) and S7b (OA21 → LSOA21 → MSOA21 → LAD Dec 2021 lookup).
- ADRs 0010 (Census acquisition via Nomis/ONS API), 0011 (LTLA single-year seed with fallbacks), 0012 (April 2026
  geography), 0013 (output formats and audience). ADR-0006 updated: mid-2025 LSOA estimates not yet published.
- 6-group ethnicity definition confirmed (ADR-0007).

### Phase 1: Scaffold (2026-10-01)
- Project scaffold: uv project (Python 3.12), ruff, pytest, typer CLI (`lsc-pop`).
- Config schema (`config/config.yaml`, pydantic, strict) with a hash that covers the mapping files.
- Mapping files: `ethnicity_19_to_6.csv` (19 → 5 → 6 groups) and `age_bands.csv` (5yr, 10yr).
- Provenance module: run context, `logged_step` (JSONL run log), dataframe hashing, output sidecars.
- Docs skeletons and ADRs 0001–0009.
- Scope widened from the L&SC ICB to all of England, with L&SC as the focus (ADR-0002).
