# Updating the pipeline: new data releases and geography changes

> **Abbreviations on this page:** ADR = architecture decision record; ICB = Integrated Care Board; IoD = English Indices of Deprivation; IPF = iterative proportional fitting; L&SC = Lancashire and South Cumbria; LAD = local authority district; LSOA = Lower layer Super Output Area; LTLA = lower-tier local authority; MSOA = Middle layer Super Output Area; NHSER = NHS England region; ODS = NHS Organisation Data Service (code); OHID = Office for Health Improvement and Disparities; ONS = Office for National Statistics; SICBL = sub-ICB location. Full definitions: [glossary](glossary.md).

A runbook for maintainers. It covers the routine updates this pipeline is designed to absorb **without code
changes**, plus the ones that need more work. The same pattern applies every time:

1. **Register** the new file in [`config/sources.yaml`](../config/sources.yaml): URL, release date, edition, quirks.
2. **Download**: `uv run lsc-pop download -s <ID>`. Existing raw files are never touched; the new file gets its own
   manifest entry and SHA-256.
3. **Point config at it**: edit [`config/config.yaml`](../config/config.yaml). The config hash changes, so every
   output records that something changed.
4. **Record the decision**: add an ADR in [`decisions/`](decisions/) and a [`CHANGELOG`](CHANGELOG.md) entry.
5. **Re-run and review**: `uv run lsc-pop run`, then check `outputs/<run_id>/validation.jsonl` and compare the key
   totals with the previous run.
6. **Refresh docs**: `uv run lsc-pop docs`, which regenerates `data_sources.md`. Check `limitations.md` and
   `methodology.md` for text that names a year or vintage.

> Keep the old source entry in `sources.yaml` (set `enabled: false` if you no longer want it downloaded) so older
> runs stay traceable. Never edit or delete files in `data/raw/` to "update" them. Register new ones instead.

---

## A. Moving to a new mid-year: e.g. mid-2025 LSOA estimates

**Status (checked 2026-10-01):** ONS has not yet published mid-2025 LSOA estimates. The release calendar lists
*"Population estimates by output areas, electoral, health and other geographies, England and Wales: mid-2025"* as
provisional for **December 2026 to January 2027**. Check the
[dataset page](https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareamidyearpopulationestimates)
for a new edition.

> This is different from the **provisional mid-2025 variant** (Stage E, `mid2025.enabled`), which would scale mid-2024
> LSOA figures to the mid-2025 *local authority* totals (S6). That variant is out of scope (ADR-0006). Once official
> mid-2025 LSOA estimates exist it isn't needed. Follow this section instead.

### Steps

1. **Inspect the release.** Download the single-year-of-age LSOA file by hand into the scratchpad (not `data/raw/`)
   and confirm:
   - it is still on **LSOA 2021** boundaries (if not, see section D);
   - the sheet name for the new year (previous pattern: `Mid-2024 LSOA 2021`);
   - the header row (previously Excel row 4, i.e. `header_row: 3`) and the column names: `LSOA 2021 Code`, `Total`,
     `F0`…`F90`, `M0`…`M90`, with 90 meaning 90+;
   - whether earlier years were revised. A new edition usually re-issues earlier years, and that's worth noting in the
     CHANGELOG.

2. **Register it** in `config/sources.yaml`. Either add a new file under the existing `S5` entry and update its
   `release_date`/`edition`/`quirks`, or (preferred) add a new source so both editions stay traceable side by side.
   Source IDs must match `S<number><optional letter>`, e.g. `S5c`. Example:

   ```yaml
   - id: S5c
     title: "ONS LSOA population estimates by single year of age and sex, mid-2025"
     role: "Current-year totals (roll-forward target)"
     publisher: "ONS"
     landing_page: "https://www.ons.gov.uk/.../lowersuperoutputareamidyearpopulationestimates"
     release_date: "2027-01-XX"
     edition: "<as shown on the dataset page>"
     reference_date: "2025-06-30"
     geography: "LSOA 2021, England and Wales"
     status: supporting information
     files:
       - name: <file name>.xlsx
         url: "<exact file URL>"
   ```

   Do the same for the accredited broad-age file (S5b), which validation uses.

3. **Download:** `uv run lsc-pop download -s S5c`.

4. **Edit `config/config.yaml`:**

   ```yaml
   reference_year: 2025
   cohort_shift_years: null        # leave null: derived as reference_year - 2021 = 4
   mye:
     source: S5c
     file: <file name>.xlsx
     edition: "<edition>"
     sheet_template: "Mid-{year} LSOA 2021"   # change if ONS renamed the sheets
     header_row: 3                            # change if the header moved
   ```

   - **Cohort shift:** Census day (21 Mar 2021) to 30 Jun 2025 is about 4.3 years, so the default shift becomes 4.
     Ages 0–3 in mid-2025 were born after the Census, so they take the age-0 proxy (ADR-0004, assumption A03).
   - Leave `mid2025.enabled: false`.

5. **ADR:** add `NNNN-reference-year-2025.md`, superseding ADR-0006. Include the new edition, any revisions to earlier
   years, the new shift, and whether the post-Census cohort (ages 0–3) changes anything.

6. **Re-run everything:** `uv run lsc-pop run`. Stages B–C (the 2021 base) don't change. Stage D onwards will.
   Review:
   - every mid-year check (the output sums exactly to S5 per LSOA × sex × age);
   - England / ICB / L&SC totals compared with the mid-2024 run;
   - the sensitivity comparison between cohort and static variants, which widens as the gap from 2021 grows.

7. **Docs:** update `limitations.md` (the migration-drift caveat grows each year), `methodology.md` (worked example
   year), README status, and the CHANGELOG. Run `uv run lsc-pop docs`.

**Other sources to recheck at the same time:** the NHS geography lookup (section B), OHID catchments (section C) and
IoD (section E). Each is independent and optional.

---

## B. NHS geography changes: ICB / sub-ICB mergers, new LAD codes

ONS publishes a new **LSOA (2021) → Sub-ICB location → ICB → NHS region → LAD** lookup when NHS structures change,
usually each April. Example: April 2026 merged 42 ICBs into 36. These changes only affect **aggregation**: no
population figure changes, but ICB / sub-ICB / LAD totals regroup.

The lookup is fully config-driven (ADR-0014). Pipeline columns are vintage-free (`icb_cd`, `sicbl_cd`, `lad_cd`,
…), and the vintage is stored in `nhs_geog_vintage` and the output metadata.

### Steps

1. **Find the new lookup** on the [Open Geography Portal](https://geoportal.statistics.gov.uk/). Search for
   *"LSOA (2021) to SICBL to ICB to … to LAD (<Month Year>) Lookup in EN"* and note the **item ID**. The CSV download
   URL pattern is:
   `https://hub.arcgis.com/api/v3/datasets/<item id>_0/downloads/data?format=csv&spatialRefId=4326`

2. **Register it** as a new source in `config/sources.yaml`, e.g. `S7d`, with item ID, release date, edition and
   quirks. Note which ICBs merged and how many LSOAs moved. Set the old `S7` to `enabled: false`, or leave it enabled
   to keep it downloadable.

3. **Download:** `uv run lsc-pop download -s S7d`.

4. **Edit `config/config.yaml` → `geography.nhs`:**

   ```yaml
   geography:
     nhs:
       source: S7d
       file: <file name>.csv
       vintage: "2027-04"
       columns:            # raw column -> standard name. Raw names carry the year suffix.
         LSOA21CD: lsoa21cd
         LSOA21NM: lsoa21nm
         SICBL27CD: sicbl_cd
         SICBL27CDH: sicbl_ods
         SICBL27NM: sicbl_nm
         ICB27CD: icb_cd
         ICB27CDH: icb_ods
         ICB27NM: icb_nm
         NHSER27CD: nhser_cd
         NHSER27CDH: nhser_ods
         NHSER27NM: nhser_nm
         LAD27CD: lad_cd
         LAD27NM: lad_nm
   ```

   - If ONS adds or drops a level (e.g. Cancer Alliance in place of NHS region), map only the columns listed above. Every
     standard name must be produced; the config fails validation if one is missing.
   - **Focus ICB:** if L&SC's code changes (e.g. after a merger), update `footprint.focus_icb_codes` and any
     `footprint.icb_codes`. Unknown codes stop the run.

5. **Run Stage A:** `uv run lsc-pop run -s geography`. Review the checks in `outputs/<run_id>/validation.jsonl`:
   - GEO-01 to GEO-09 must pass (coverage, uniqueness, nesting of sub-ICB → ICB → region);
   - GEO-10 lists LADs split across ICBs, which is informational. A change here is expected after mergers or LAD
     reorganisations;
   - GEO-12 summarises the focus ICB (LSOAs, sub-ICBs, LADs).

6. **ADR + CHANGELOG:** record the new vintage and which aggregates change. Then re-run the downstream stages
   (`uv run lsc-pop run`).

**What does *not* change:** the Census-era lookups `geography.census` (S7b: LSOA21 → MSOA21 → LTLA 2021) and
`geography.ltla_region` (S7c). They describe 2021 Census geography, which the IPF seed (S3) and OHID catchments
(MSOA 2021) are keyed on. Leave them alone unless the Census base changes (section D).

---

## C. Hospital trust catchments (OHID) and trust mergers

OHID says the catchment populations publication *"will be updated annually"*.

1. Register the new ODS as a new file/edition under `S9` (or a new source ID), with release date and quirks. Check
   whether the geography is still MSOA 2021 and whether the sheet names and headers changed (`lsc_pop.catchments`
   reads sheets `All_admissions`, `Trust_analysis`, `Ethnicity`, `Deprivation` and `Trust_area_lookup`, with the
   header on the third row). Then update `config.yaml → catchments.{source, file, catchment_year}`.
2. **Trust mergers or new ODS codes:** update `focus_trusts` in `config/config.yaml`. For example, if a OneLSC trust
   merges and gets a new code, swap the old code for the new one and note it in an ADR.
3. Re-run (`uv run lsc-pop run`) and review checks CAT-01 to CAT-10 and the trust comparisons in
   `validation_report.md`.

---

## D. LSOA boundary changes (major: not a routine update)

LSOAs are redrawn only after a Census (next: Census 2031). Moving to new LSOAs changes the **base geography**
(ADR-0001) and every Census input, so it is a project-level change and not a config edit. It would need:
- a new ADR superseding ADR-0001;
- either a full rebuild on 2031 Census tables, or an LSOA 2021 → 2031 conversion with its own error analysis;
- updates to `geography.expected_lsoa_count` and every lookup.

If ONS publishes a mid-year estimate on new LSOAs before you're ready, stay on the last edition published on LSOA 2021.

---

## E. Other periodic inputs

| Input | Where | How to update |
|---|---|---|
| IoD (next edition) | `sources.yaml` + `config.yaml → deprivation.{source, file, edition}` | Register, download and point config at the new file. Check it's on LSOA 2021 and that File 7's headers still map (`lsc_pop.deprivation.IOD_PREFIXES`; unrecognised headers fail loudly). ADR, because deprivation deciles and Core20 membership change. |
| Ethnicity mapping (19 → 6) | `config/mappings/ethnicity_19_to_6.csv` | Edit the CSV. It's validated on load (19 unique codes, one label per group code). The config hash changes automatically. ADR if the grouping changes. |
| Age bands | `config/mappings/age_bands.csv` + `age.band_sets` | Add rows for a new `band_set` (must tile 0–90 with no gaps or overlaps; validated on load), then list it in `age.band_sets`. |
| Census tables (S1–S4) | `sources.yaml` | Fixed for the life of the 2021 base. Only re-download if ONS re-issues a table, and record it as a new edition, because the base changes. |

---

## Checklist after any update

- [ ] New source registered in `config/sources.yaml` with release date, edition and quirks
- [ ] `uv run lsc-pop download -s <ID>` done and the manifest entry present
- [ ] `config/config.yaml` updated; `uv run pytest` passes
- [ ] ADR written; CHANGELOG entry added
- [ ] `uv run lsc-pop run` completes; all hard checks pass; key totals compared with the previous run
- [ ] `uv run lsc-pop docs` run; README status and any year/vintage text in docs updated
