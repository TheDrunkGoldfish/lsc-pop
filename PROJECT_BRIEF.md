> **Historical document.** This is the original kick-off brief the project was built from (2026-10-01). Several
> scope decisions were changed during the build, and those records take precedence over this text. The main ones:
> - England-wide footprint, not the ICB only (ADR-0002);
> - mid-2024 only (ADR-0006);
> - floats only (ADR-0005);
> - a star schema with no aggregate tables (ADR-0018).
>
> See [`docs/decisions/`](docs/decisions/) and [`README.md`](README.md) for the current design.

# Project brief: LSOA population by sex, age and ethnicity — Lancashire & South Cumbria

> **For Claude Code.** This is the kick-off brief for this repository. Read it in full before doing anything.
> Work in the phases set out in §8 and **stop for review at the end of each phase**. Treat the methodology in §5
> as the agreed starting point, not as settled fact: where the data turns out to differ from what's described here,
> record it, propose an alternative and ask before you deviate.

---

## 1. Purpose

Build a reproducible Python pipeline that produces **modelled population estimates by LSOA × sex × age × ethnic group**
for the Lancashire and South Cumbria (L&SC) health footprint. It should be enriched with the **English Indices of Deprivation
2025** and support aggregation to NHS footprints: ICB, sub-ICB/place, local authority, and acute trust catchments for the
OneLSC provider trusts.

No single public source publishes this cross-tabulation for a current year, so we combine several and model the gaps.
The outputs are **modelled estimates, not official statistics**. Make that clear in every output and document.

**Documentation is a first-class deliverable.** A health-intelligence analyst who has never seen the code should be able to
read `docs/` and understand every source, every decision, every assumption and every transformation, including what it did
to the numbers. A reviewer should be able to rerun the pipeline and get identical outputs.

## 2. Scope

| Item | Decision / default | Notes |
|---|---|---|
| Base geography | 2021 LSOAs (England) | Same as Census 2021 outputs, ONS small area population estimates and IoD 2025, so no boundary conversion is needed. |
| Footprint | LSOAs in **NHS Lancashire and South Cumbria ICB**, taken from the ONS LSOA21 → Sub-ICB → ICB lookup | Must be **configurable** (see §6.2). Don't hard-code LA lists. |
| Reference date | **Mid-2024** (latest official LSOA estimates, released Nov 2025) | Optional provisional **mid-2025** variant, scaled to the mid-2025 LA estimates (released 29 Jul 2026). Check whether ONS has since published mid-2025 LSOA estimates; if so, use them and update the docs. |
| Sex | Female / Male | As published. |
| Age | Single year of age 0–90+ internally | Output both single year and standard bands (configurable, e.g. 5-year bands and broad NHS bands). |
| Ethnicity | Census 2021 19 tick-box groups (`ethnic_group_tb_20b` minus "Does not apply") | Also output the 5/6-group aggregation via a mapping file in `config/`. |
| Deprivation | IoD 2025 (IMD plus domains) at LSOA | National rank, decile and quintile; a Core20 flag (national IMD deciles 1–2); and an optional local quintile ranked within the footprint. |
| Countries | England only | L&SC is wholly in England. |

### Provider catchments
Provider catchments don't follow the ICB boundary. For example, West Lancashire residents largely use an acute trust outside
OneLSC (Ormskirk/Southport), and some trust catchments may extend into neighbouring ICBs. Trust-level aggregation must use
catchment proportions, not ICB membership. The footprint may need to include LSOAs outside the ICB (see §6.2).

## 3. Ground rules for working in this repo

1. **Verify, don't trust.** URLs, dataset IDs, file layouts and release dates in this brief come from desk research and may be
   out of date. Check each against the live source, and record what you actually used (URL, release date, file name, checksum)
   in the source register.
2. **No silent methodology changes.** Any choice that affects the numbers gets an ADR in `docs/decisions/` (format in §7.2)
   *before* or *alongside* the code that implements it. This includes choices between plausible options, tolerances,
   category mappings, handling of edge cases and fallbacks.
3. **Every transformation is logged** through the step logger (§7.3), which records row counts and population totals in and out.
4. **Ask before deciding** anything listed in §9 (open questions), and anything that is expensive to undo.
5. **Reproducibility.** Pin dependencies (lock file), fix random seeds, keep pipeline stages deterministic and record each run's
   git commit and config hash in the output metadata.
6. **Raw data is immutable.** Write to `data/raw/` once, via the download stage, and never edit it. All cleaning happens downstream.
   Don't commit raw or large data. Do commit the source manifest (checksums).
7. Keep `CLAUDE.md` short and up to date with the standing conventions (commands, layout, rules above), so future sessions
   start with the right context. Put the narrative in `docs/`, not in `CLAUDE.md`.

## 4. Data sources (to verify in Phase 2)

All are ONS / MHCLG / OHID, published under the Open Government Licence v3.0. Record the exact versions used.

| # | Role | Source | Expected content | Notes |
|---|---|---|---|---|
| S1 | Ethnicity seed (core) | Census 2021 **RM032** *Ethnic group by sex by age* (ONS; bulk CSVs also on UK Data Service) | LSOA × 20 ethnic categories × sex × 5 age bands (≤24, 25–34, 35–49, 50–64, 65+) | The ≤24 band is the main weakness: minority groups have much younger age structures. Drop "Does not apply" (should be 0 for usual residents; assert it). |
| S2 | Fine age, 2021 | Census 2021 **RM200** / **TS009** *Sex by single year of age* | LSOA × sex × single year | Used as the age margin in the IPF. |
| S3 | Ethnicity-specific age shape (seed) | Census 2021 *Ethnic group by age and sex* at **LA** level (ONS / UKDS workbook), **or** a finer custom dataset from the ONS *Create a custom dataset* tool/API at MSOA (ethnicity × sex × finer age) | Ethnicity × sex × age finer than RM032 | Investigate both. Prefer the **finest geography** that gives ethnicity × sex × age finer than RM032, without heavy disclosure-control blanking. Write an ADR on the choice. The ONS custom-dataset API (used by the `ukcensus` R package) may support area filtering. |
| S4 | Validation | Census 2021 **TS021** *Ethnic group* (LSOA) | LSOA × ethnicity | Check the 2021 base totals. |
| S5 | Current-year totals | ONS *Lower layer Super Output Area population estimates* (supporting information, **single year of age and sex**), mid-2024; also the accredited broad-age version | LSOA × sex × single year | Released 7 Nov 2025. Single-year LSOA data is "supporting information", not accredited official statistics. Note this in the docs. |
| S6 | Provisional mid-2025 (optional) | ONS mid-2025 MYE for local authorities (29 Jul 2026) | LA × sex × single year | Only if the mid-2025 variant is in scope (§9). |
| S7 | Geography lookup | ONS Open Geography Portal: **LSOA (2021) → Sub-ICB location → ICB → LAD** (latest vintage) | Lookup | Keep the vintage in the file name. |
| S8 | Deprivation | MHCLG **English Indices of Deprivation 2025** (released Oct 2025), on LSOA 2021 | Ranks, deciles and scores for IMD and domains | File 1 (IMD) at minimum; ideally all domains + scores. |
| S9 | Trust catchments | OHID **NHS acute (hospital) trust catchment populations**, April 2026 release (data tables, ODS) | Trust catchment proportions/populations by small area; the May 2026 update added ethnicity and deprivation | (a) Find out what geography the catchment proportions are given at (MSOA or LSOA) and use them to apportion. (b) Use their published ethnicity/deprivation figures as an **external validation comparator** for trust-level outputs. |
| S10 | Boundaries (optional, later) | ONS Open Geography Portal LSOA 2021 boundaries (generalised) | Polygons | Only for maps; not needed for the core pipeline. |

OneLSC trusts (confirm with the user): Blackpool Teaching Hospitals, East Lancashire Hospitals, Lancashire Teaching
Hospitals, University Hospitals of Morecambe Bay, and Lancashire & South Cumbria NHS FT (mental health/community, ICB-wide,
so not in the OHID acute catchments).

## 5. Methodology (agreed starting point)

### 5.1 Overview
```
Census 2021 (RM032, RM200, seed S3) ──► 2021 base cube by IPF ──► roll forward to mid-2024 LSOA SYOA×sex (S5)
                                                                        │
                                                       (optional) scale to mid-2025 LA totals (S6)
                                                                        │
                                         join IoD 2025 (S8) ──► aggregate: ICB / place / LA / trust (S7, S9)
```

### 5.2 Stage A — Geography
- Build the footprint LSOA list from S7 (filter by ICB code/name; assert the count is plausible and log it).
- Attach LAD, sub-ICB and ICB.
- If trust catchments need LSOAs beyond the ICB, extend the footprint as in §6.2 and flag `in_icb` per LSOA.

### 5.3 Stage B — Ingest & harmonise census margins
- Load S1, S2 (and S4) for footprint LSOAs (plus any LSOAs needed for later scaling; see 5.5). Tidy to long format with
  standard codes.
- **Margin reconciliation.** Census tables are independently perturbed (cell key perturbation, record swapping), so
  LSOA × sex totals differ slightly between RM032 and RM200. Quantify the discrepancy (log the distribution), then rescale both to a
  common LSOA × sex total before IPF. Choose which table defines the total, and record the choice in an ADR.

### 5.4 Stage C — 2021 base cube: ethnicity × sex × single year of age, per LSOA
- Within each LSOA × sex × RM032 broad band, the problem is a 2-D table (ethnic group × single years in that band) with
  known row margins (RM032) and column margins (RM200). Fit it with **IPF / raking**, seeded by the ethnicity-specific age
  distribution from S3 (interpolated to single years as needed; document the interpolation).
- Implement IPF in vectorised numpy in-house (small, transparent, unit-tested) rather than as an opaque dependency. Log the
  iterations and maximum margin error per cell group, and fail loudly if it doesn't converge.
- Handle zero margins and structural zeros explicitly (e.g. an ethnic group with 0 in the band → all cells 0).
- **Result:** 2021 base as a float cube. It should reproduce RM032 and RM200 margins to within tolerance (after reconciliation).

### 5.5 Stage D — Roll forward to mid-2024
- Convert the base to **ethnic shares** within each LSOA × sex × single year.
- **Cohort ageing (default):** ethnicity follows the person, so the share for age *a* in mid-2024 = the 2021 share at age
  *a − 3* (Census day 21 Mar 2021 → 30 Jun 2024 ≈ 3.3 years; use a 3-year shift and document it). Ages 0–2 in 2024 (born
  after the census) take the 2021 age-0 shares unless a better proxy is agreed. Treat the 90+ open-ended group explicitly.
- Also implement **static shares** (no ageing) as a sensitivity variant. Make the variant a config option and report the difference.
- Apply the shares to S5 (LSOA × sex × single year, mid-2024). The output must sum **exactly** to S5 for every LSOA × sex × age.
- **Known limitation, to be documented prominently:** held-constant shares cannot capture post-2021 migration-driven change in
  ethnic composition. No official LSOA-level source corrects for this. Note ONS admin-based ethnicity research outputs as
  context only; don't use them as inputs.

### 5.6 Stage E (optional) — Provisional mid-2025
- For each LA (2025 boundaries), scale the mid-2024 LSOA single-year × sex estimates by the ratio
  `LA mid-2025 / Σ LA's LSOAs mid-2024` per sex × age. Label the outputs `provisional`.

### 5.7 Stage F — Deprivation
- Join IoD 2025 at LSOA: IMD rank, score, decile, quintile and domain deciles. Add `core20` (national IMD deciles 1–2) and an
  optional footprint-local quintile (population-weighted; document the method).

### 5.8 Stage G — Aggregation
- Aggregate to ICB, sub-ICB/place, LA, and acute trust catchments (apportion with S9
  proportions; if S9 is at MSOA, apply the MSOA proportion to each child LSOA and document that assumption).
- Every aggregate must reconcile to the sum of its LSOAs (or to the apportioned total for trusts).

### 5.9 Rounding & disclosure
- Keep unrounded floats as the canonical output. Provide an optional integerised output using controlled rounding that
  preserves LSOA × sex × age totals (document the algorithm and seed).
- Most single-year × 19-group cells at LSOA will be <5. Include a short note on appropriate use and suggested suppression
  rules for any published tables.

## 6. Technical design

### 6.1 Stack
Python 3.11+, managed with **uv** (lock file committed). pandas + pyarrow (Parquet for interim/outputs), numpy, pyyaml +
pydantic (config validation), requests, openpyxl / odfpy (xlsx/ods), typer (CLI), pytest, ruff. Optional later: geopandas,
matplotlib for QA charts.

### 6.2 Configuration (`config/config.yaml`)
Everything that changes the numbers lives here, not in code: reference year, variant (`cohort` / `static`), optional mid-2025
toggle, footprint definition (ICB code(s), plus an optional `extra_lsoas_from_trust_catchments: [trust codes]`), output age bands,
ethnicity mapping file, IPF tolerance and max iterations, rounding on/off. Hash the config into the run metadata.

Mapping/lookup CSVs live in `config/mappings/` (e.g. `ethnicity_19_to_6.csv`, `age_bands.csv`) and are documented in the data
dictionary.

### 6.3 Suggested layout
```
CLAUDE.md                     # short standing conventions for Claude Code
README.md                     # what this is, quick start, how to run, where outputs go
pyproject.toml / uv.lock
config/
  config.yaml
  mappings/
data/                         # gitignored except manifests
  raw/        <source_id>/... # immutable downloads
  interim/
  processed/
  manifest.json               # committed: url, release date, retrieved_at, sha256, size per raw file
docs/
  methodology.md              # narrative method for analysts (non-technical first, technical annex after)
  data_sources.md             # source register (S1..Sn) — generated from manifest + hand-written notes
  decisions/                  # ADRs: 0001-*.md, 0002-*.md ...
  assumptions.md              # assumptions register with impact + sensitivity tested?
  transformations.md          # generated from the run log: each step, inputs, outputs, totals, diffs
  data_dictionary.md          # every output column, type, allowed values, provenance
  validation_report.md        # generated: all checks, pass/fail, tolerances, key metrics
  limitations.md              # plain-English caveats for end users
  CHANGELOG.md
src/lsc_pop/
  cli.py                      # `lsc-pop run [--stage X]`, `lsc-pop docs`, `lsc-pop validate`
  config.py
  provenance.py               # step logger, run metadata, output sidecars
  download.py
  geography.py
  census.py                   # ingest + harmonise
  ipf.py
  rollforward.py
  deprivation.py
  aggregate.py
  validate.py
  report.py                   # renders transformations.md / validation_report.md
tests/
outputs/
  <run_id>/ ... parquet + csv + metadata.json
```

## 7. Documentation & provenance requirements (most important)

### 7.1 Source register (`docs/data_sources.md`)
For each source: ID, title, publisher, URL, release date, version/edition, reference date, geography vintage, licence,
retrieved-at timestamp, file name(s), SHA-256, row count, and **known quirks** (perturbation, suppression, category
differences, supporting-info vs accredited status). Generate the mechanical fields from `data/manifest.json`.

### 7.2 Decision log (`docs/decisions/NNNN-title.md`)
Use a lightweight ADR format:
```
# NNNN. <Decision title>
Status: proposed | accepted | superseded by NNNN
Date:
Context: what problem / what the data showed
Options considered: (with pros/cons, and evidence such as numbers from exploratory checks)
Decision:
Consequences: effect on outputs, limitations introduced, what would change our mind
Related: stages, config keys, tests
```
Seed the log with ADRs for decisions already made in this brief (LSOA base geography, footprint via ICB lookup, IPF approach,
cohort ageing default, unrounded canonical output). Add new ones as you go.

### 7.3 Transformation log (machine-generated)
- Wrap every pipeline step in a `@logged_step` decorator / context manager that records: step name, timestamp, parameters, input
  datasets (+hash), output dataset (+hash), row counts in/out, **population totals in/out** (overall and by sex), rows
  dropped/added and why, and free-text notes the step emits (e.g. "rescaled 312 LSOA×sex margins; max adj 0.8%").
- Write one JSONL per run (`outputs/<run_id>/run_log.jsonl`) and render it into `docs/transformations.md` as a readable
  table plus per-step narrative.

### 7.4 Output metadata
Every output file gets a sidecar `*.metadata.json` with run_id, git commit, config hash, reference date, variant, source IDs
and versions, a "modelled estimates – not official statistics" statement, and a pointer to the docs.

### 7.5 Methodology & limitations
`docs/methodology.md` explains the method in plain English first, with a worked example for one LSOA, followed by a
technical annex. `docs/limitations.md` lists caveats for users (migration drift, perturbation, small numbers, the
supporting-info status of single-year LSOA estimates, catchment apportionment assumptions).

## 8. Phases (stop and summarise for review at the end of each)

1. **Scaffold.** Repo layout, uv project, ruff/pytest, config schema, `CLAUDE.md`, README, docs skeletons, provenance module
   with the step logger, and the initial ADRs from §7.2.
2. **Source discovery & download.** Verify every source in §4, implement `download.py` with the manifest, and fill the source register.
   **Report back:** what was actually available, especially (a) seed options for S3 and their granularity, (b) whether mid-2025
   LSOA estimates now exist, and (c) the geography level of the OHID catchment proportions.
3. **Geography.** Footprint list and lookups, with tests (counts, uniqueness, every LSOA mapped).
4. **Census ingest & harmonisation.** Tidy tables, margin-reconciliation analysis and the resulting ADR.
5. **IPF base 2021.** `ipf.py` with unit tests on toy tables (known solutions, zero handling, convergence), the full run, and validation
   against RM032/RM200/TS021 and LA-level ethnicity × age × sex.
6. **Roll-forward.** Cohort and static variants, exact reconciliation to S5, and a sensitivity comparison (written into the docs).
   Optional mid-2025 variant if agreed.
7. **Deprivation & aggregation.** IoD join, Core20, place/LA/trust aggregation, and comparison with OHID trust-level figures.
8. **Outputs & docs.** Final datasets, data dictionary, generated transformations and validation reports, methodology,
   limitations, and README quick start. End-to-end `lsc-pop run` from a clean checkout.

## 9. Open questions — ask the user (don't assume)
- Reference date: mid-2024 official only, or also provisional mid-2025?
- Output age bands needed (5-year? NHS-specific bands?) and ethnicity levels (19 and 6?).
- Integerised output needed, or floats only?
- Which trusts for catchment aggregation (confirm the OneLSC list) and whether the footprint should extend beyond the ICB to
  cover full catchments.
- Any local data (e.g. GP-registered population with ethnicity) the user may want to compare against later? Out of scope
  for now, but design the validation module so comparators can be added.

## 10. Validation checklist (all automated, reported in `validation_report.md`)
- [ ] Footprint LSOA count matches the lookup; no duplicates; every LSOA has ICB/sub-ICB/LA/IoD records.
- [ ] RM032 "Does not apply" = 0 for all footprint LSOAs.
- [ ] Margin reconciliation adjustments are within the stated tolerance (and the distribution is logged).
- [ ] 2021 base reproduces RM032 (eth × sex × band) and RM200 (sex × age) margins within the IPF tolerance.
- [ ] 2021 base ethnic totals vs TS021 (report differences; these come from perturbation, not a failure).
- [ ] 2021 base aggregated to LA vs the LA-level ethnicity × age × sex tables (report and chart).
- [ ] Mid-2024 output sums exactly to S5 for every LSOA × sex × age.
- [ ] No negative or NaN values; all shares within [0, 1] and summing to 1.
- [ ] Aggregates reconcile to their constituent LSOAs; trust totals are compared with OHID catchment totals.
- [ ] Cohort vs static variant differences summarised by ethnic group and age.
- [ ] Re-running from a clean checkout reproduces identical output hashes.