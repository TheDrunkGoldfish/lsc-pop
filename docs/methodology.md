# Methodology

> **Modelled estimates, not official statistics.** Covers every stage (A–G). Results of every check are in
> [`validation_report.md`](validation_report.md); each step's row counts and totals are in
> [`transformations.md`](transformations.md).
>
> **Abbreviations on this page:** ADR = architecture decision record; FPTP = first past the post (OHID method); ICB = Integrated Care Board; IMD = Index of Multiple Deprivation; IoD = English Indices of Deprivation; IPF = iterative proportional fitting; L&SC = Lancashire and South Cumbria; LSOA = Lower layer Super Output Area; LTLA = lower-tier local authority; MSOA = Middle layer Super Output Area; OHID = Office for Health Improvement and Disparities; ONS = Office for National Statistics. Full definitions: [glossary](glossary.md).

## 1. In plain English

We want to know how many people of each sex, single year of age and ethnic group live in each LSOA (Lower layer
Super Output Area: one of 33,755 small areas in England of about 1,500 people) in mid-2024. No
published table gives that, so we build it in four steps.

1. **Start from Census 2021.** For every LSOA it tells us how many people of each sex are in each of 19 ethnic groups
   within five broad age bands (≤24, 25–34, 35–49, 50–64, 65+; table RM032). Separately, it tells us how many people of
   each sex are at each single year of age (RM200). It never gives ethnicity and single year together. The two tables
   were each slightly "blurred" by ONS to protect confidentiality, so we first make them agree on each band's total.
2. **Fill in the detail (iterative proportional fitting, IPF).** Inside each LSOA, sex and broad band we build the
   ethnic group × single-year table that adds up to both published sets of totals. To decide *which* ages each group's
   people are likely to be, we borrow the age pattern each ethnic group has in the LSOA's 2021 local authority
   district (the "seed"). For example, Pakistani women aged 25–34 in Blackburn with Darwen skew slightly older within
   the band than White British women. The result is the **2021 base**.
3. **Move forward to mid-2024 (cohort ageing).** People get older but keep their ethnic group. So the ethnic mix of
   30-year-olds in mid-2024 is taken from the people who were 27 at the 2021 Census, in the same LSOA and sex. We apply
   that mix to ONS's official mid-2024 count of people of that age and sex in the LSOA. The output therefore always
   adds up exactly to ONS's mid-2024 population estimates. Children born after the Census (aged 0–2 in 2024) take the
   ethnic mix of the LSOA's 2021 babies.
4. **Add deprivation and hospital catchments.** Each LSOA gets its English Indices of Deprivation 2025 ranks and
   deciles (and Core20 and local-quintile flags), and its share of patients for each acute trust (from OHID).
   The outputs are a set of tables for SQL/Databricks (a "star schema"), so analysts can add up any combination:
   ICB, place, local authority, trust catchment, deprivation quintile.

**What this can't do.** It can't see changes in an area's ethnic mix since 2021 from people moving in or out
(limitations §1). And very small cells (one LSOA, one year of age, one ethnic group) are estimates with a lot of
uncertainty, best used only as building blocks for larger totals.

## 2. Worked example: Blackburn with Darwen 002A (E01012581), women aged 30 in mid-2024

This LSOA in NHS Lancashire and South Cumbria ICB had 1,357 usual residents at the 2021 Census. We follow the women who
will be **aged 30 in mid-2024**. In 2021 they were aged 27, in RM032's 25–34 band. The six groups shown are the largest
here (19 are modelled).

| Step | What happens | White British | Pakistani | Indian | Bangladeshi | All 19 groups |
|---|---|---|---|---|---|---|
| 1 | RM032, women 25–34 (raw) | 17 | 27 | 43 | 3 | **92** |
| 2 | RM200, women by single year 25–34: 4, 6, **4** (age 27), 13, 9, 10, 12, 4, 13, 9 | | | | | **84** |
| 3 | Reconcile (ADR-0015): RM032 scaled by 84/92 = 0.913 so both tables total 84 | 15.52 | 24.65 | 39.26 | 2.74 | 84 |
| 4 | Seed: Blackburn with Darwen women by age, e.g. White British 484…521 and Pakistani 177…246 across ages 25–34, + floor 0.5 | | | | | |
| 5 | IPF → 2021 base, women **aged 27** | 0.752 | 1.108 | 1.982 | 0.101 | 4.000 (= RM200) |
| 6 | Ethnic shares at 2021 age 27 | 18.8% | 27.7% | 49.6% | 2.5% | 100% |
| 7 | ONS mid-2024 (S5): women **aged 30** | | | | | **6** |
| 8 | Estimate = 6 × share | 1.128 | 1.662 | 2.973 | 0.151 | **6.000** |

The estimates are fractional, and for a single LSOA × age they're very uncertain. They're meant to be added up
(e.g. to ICB × 5-year band), where the noise largely cancels. The same calculation runs for every LSOA (33,755) × sex
× age (0–90+) × ethnic group (19) in England.

## 3. Technical annex
### 3.1 Geography (Stage A)
Stage A builds a single England-wide lookup with one row per 2021 LSOA (33,755). It joins three ONS lookups on the
LSOA code. Which files and columns are used is set in `config.geography` (ADR-0014):

- **Current NHS/admin geography** (S7, April 2026): sub-ICB location, ICB, NHS region and local authority district. Used
  for aggregation. It's updated when NHS structures change (`docs/updating.md` §B).
- **Census-era geography** (S7b, December 2021): MSOA 2021, which OHID catchments are published on, and the 2021 lower-tier
  local authority (LTLA), which the ethnicity age-shape seed is published on. These differ from current LADs where
  councils have since merged. In L&SC, Barrow-in-Furness and South Lakeland are now part of Westmorland and Furness.
- **Region of each 2021 LTLA** (S7c), for the seed fallback (ADR-0011).

The footprint is every England LSOA (`in_footprint`). L&SC LSOAs are flagged `in_focus_icb`. Checks GEO-01 to GEO-12
confirm:
- both lookups cover the same LSOAs, the count is 33,755 and every code is unique;
- every LSOA has every geography level;
- sub-ICBs nest in ICBs and ICBs in NHS regions;
- MSOAs nest in 2021 LTLAs, and 2021 LTLAs nest in current LADs and regions.

LADs are *not* required to nest in ICBs. Five don't in April 2026, e.g. North Yorkshire, which has 3 LSOAs in L&SC.
L&SC has 1,060 LSOAs in 8 sub-ICB locations, 17 current LADs, 18 LTLAs on 2021 boundaries and 216 MSOAs.
### 3.2 Census ingest & margin reconciliation (Stage B)
**Ingest.** Each Census table is tidied to long format with standard codes (sex `F`/`M`, ethnic group 1–19,
single year 0–90, RM032 band 1–5; see `config/mappings/census_age_classifications.csv`). Integrity checks:
- CEN-01: RM032's all-groups total equals the sum of the 19 groups. This is the "Does not apply = 0" check, because
  Nomis omits that category.
- CEN-03 and CEN-05: RM200 and TS021 totals equal the sum of their parts.
- CEN-02, CEN-04, CEN-06: every table covers exactly the 33,755 LSOAs with a complete grid.
- CEN-07 and CEN-08: seed "Does not apply" = 0, and every LTLA is either returned or recorded as blocked by disclosure
  control.

**Comparison.** Census tables are perturbed independently, so they don't agree exactly (ADR-0015 has the full
table). RM032 and RM200 LSOA × sex × band totals differ by a mean of 2 people (max 16), and no band is zero in one
table but not the other.

**Reconciliation.** IPF needs the ethnic margin (RM032) and the single-year margin (RM200) of each LSOA × sex × band
to have the same total. RM200 sets that total (`reconciliation.margin_source: rm200`), and RM032's ethnic counts in
the band are scaled proportionally. This preserves the band's ethnic mix and shifts its size by the perturbation gap.
Checks: CEN-10 (the margins agree to 1e-6 after reconciliation), CEN-11 (non-negative and finite) and the soft CEN-12
(adjustments above max(10 people, 5%) flagged: 153 of 337,550 bands).

*Why the choice of table doesn't change the mid-2024 result:* scaling both margins of a band to the same total scales
the IPF solution by one constant, so the ethnic share at each age is the same whichever table sets the total
(verified to 1e-11). Only the absolute 2021 base differs.
### 3.3 IPF base 2021 (Stage C)
**Seed** (ADR-0011, `lsc_pop.base.build_seed`): an array of LTLA 2021 × sex × ethnic group × single year counts from S3.
- 301 English LTLAs are used as published.
- The 7 LTLAs blocked at single year use their own 23-category counts. They are Allerdale, Copeland and Eden
  (Cumbria), Torridge and West Devon (Devon), and Richmondshire and Ryedale (North Yorkshire). Of these, only Copeland
  touches L&SC, through 6 LSOAs. Each category is split into single years by the region's single-year shape for the same ethnic
  group × sex.
- The Isles of Scilly (blocked at all fine ages) uses Cornwall's seed.

`ipf.seed_floor` (0.5; ADR-0016, proposed) is added to every cell. 26% of seed cells are zero, mostly in small groups.

**Fit** (ADR-0003, `lsc_pop.ipf.ipf_fit`). For each RM032 band, all 67,510 LSOA × sex tables are fitted in one
vectorised batch: ethnic groups × single years, with row margins = reconciled RM032 and column margins = RM200.
Rows and columns are alternately scaled to their margins until every row error is below `ipf.tolerance` (1e-6 people).
- Inputs are checked first: equal totals, and no positive margin without seed support. A failure in either raises an
  error.
- Non-convergence within `ipf.max_iter` is an error.
- Zero margins give structural zeros.
- England converges in at most 18/24/19/32/19 iterations for bands 1–5.

**Validation** (BAS-01 to BAS-09):
- The base reproduces the reconciled RM032 to 8.8 × 10⁻⁷ and RM200 to 2 × 10⁻¹³ people, with total 56,489,042.
- Against **TS021** (independent), England ethnic totals differ by at most +1,093 (White British, 0.003%). Every other
  group is within ±510.
- At LSOA × ethnic group: mean absolute difference 0.86, max 32 (perturbation).
- Aggregated to LTLA and compared with the S3 seed at LTLA × sex × ethnic group × single year: mean absolute difference
  1.0 (L&SC 0.64).
- Sensitivity to the floor and to a uniform seed: `docs/sensitivity.md` §4.

### 3.4 Roll-forward (Stage D)
(ADR-0004 and ADR-0017, `lsc_pop.rollforward`.)

**Inputs.** The mid-year LSOA estimates (S5, `config.mye`) are read for the reference year's sheet.
- ROL-01 to ROL-03: coverage, `Total` = sum of cells, non-negative integers.
- ROL-04: they match the accredited broad-age file S5b exactly.
- Mid-2024 England total: 58,620,101.

**Shares.** For target age a, with shift k = `reference_year − 2021` (3), the share is taken from the 2021 base:
- target age a uses 2021 age a − k;
- target 90+ pools 2021 ages 87–90+;
- targets 0–2 use the 2021 age-0 shares (`rollforward.newborn_proxy_ages`).

The `static` variant uses 2021 age a.

Where an LSOA × sex had nobody at the source ages in 2021, the shares fall back in this order:
1. the LSOA × sex pooled over the RM032 band (0.22% of mid-2024 people);
2. the LSOA × sex, all ages (7 people);
3. the LSOA, all ages;
4. the LTLA.

The level used is stored per cell (`share_fallback_level`).

**Estimates** = S5 × shares. ROL-05: they sum to S5 for every LSOA × sex × age (max gap 2 × 10⁻¹³). ROL-06: shares lie
in [0, 1] and sum to 1. ROL-07: the total equals S5.

**Sensitivity** (`docs/sensitivity.md`, regenerated each run):
- **Static vs cohort.** Static shares give 8.6% fewer people of Mixed ethnicity in England (8.3% in L&SC) and 1–2%
  fewer Asian, Black and Other, offset by +0.6% White British. Static ignores that young, more diverse 2021 cohorts are
  three years older by 2024.
- **Newborn proxy.** Using ages 0–4 for the newborn proxy changes 6-group totals by at most 0.5% in L&SC (ages 0–9:
  −2.3% to +3.2%).
- **Seed floor.** Floors of 0.01 or 2 change L&SC 6-group totals by at most 0.5%.

### 3.5 Deprivation (Stage F)
(ADR-0008, `lsc_pop.deprivation`.)

**Inputs.** IoD 2025 File 7 (S8) joins 1:1 to every LSOA (DEP-01). The ranks are a permutation of 1–33,755 (DEP-02).
All IMD, domain, supplementary-index and sub-domain scores, ranks and deciles are kept under short names.

**Derived fields:**
- `imd_quintile` = national quintile from deciles.
- `core20` = deciles 1–2: 6,751 LSOAs, 20.3% of England's mid-2024 population and 29.6% of L&SC's.
- `imd_local_quintile`: within each ICB, LSOAs are ordered by national IMD rank (most deprived first) and assigned
  to the quintile containing the midpoint of their population on the ICB's cumulative mid-2024 population scale.
  Each local quintile holds 20% ± 0.3 pp of its ICB's population (DEP-03).

### 3.6 Trust catchments and aggregation (Stage G)
(ADR-0018, ADR-0019, `lsc_pop.catchments`.)

There are no pre-built aggregates. All aggregation happens in SQL/BI over the star schema, and the pipeline checks
that it reconciles:
- ICB totals equal the sum of their LSOAs (OUT-03);
- trusts plus `UNASSIGNED` equal England exactly (CAT-07, OUT-04).

**Catchments.** OHID's MSOA × trust shares (all admissions, catchment year 2024) are applied to every LSOA in the
MSOA (A06). The ~2% that OHID suppressed or rounded away goes to an explicit `UNASSIGNED` row
(`proportion_published`). `proportion_rescaled` instead spreads it pro rata over the listed trusts.

**Comparison with OHID** (`validation_report.md`):
- **Totals.** Our mid-2024 totals are 1–4% above OHID's T1, which uses mid-2022 populations. For example, RXL
  publishes 303,969 and rescales to 308,817, against OHID's 299,904.
- **Ethnicity.** Under OHID's first-past-the-post assignment, modelled 5-group percentages match OHID's T5 closely
  (median |difference| ≈ 0.1 pp; Figure 3).
- **Deprivation.** Mean IMD scores match OHID's T6 to within 0.9 points for the OneLSC trusts.
- **Not comparable.** OHID's "All (5% and above)" ethnicity figures differ markedly for some trusts. A built-in
  hypothesis test (CAT-11) shows they move towards OHID's when the ethnic mix is smoothed over ICBs, but no geography
  reproduces them. OHID's method for that table isn't published, so we validate against FPTP (ADR-0019).

### 3.7 Outputs, rounding and disclosure
Outputs are a star schema of unrounded floats (ADR-0005, ADR-0018), described in `data_dictionary.md`. They're
for internal analysts (ADR-0013). For guidance on publishing anything derived from them, see `limitations.md` §8.

### 3.8 Reproducibility
Every run records its config, code and `uv.lock` hashes (ADR-0009), and every table records a `data_hash`.
`lsc-pop compare-runs <run A> <run B>` compares two runs. A run from a clean copy of the repository (fresh
`uv sync`, fresh download, full run) is compared in `validation_report.md`.

**Result (2026-10-01):** a clean copy (no `.venv`, no data, only the committed `data/manifest.json`) re-downloaded
all 13 raw files with SHA-256s identical to the manifest (19 min). Its full run (2 min) produced the same
`data_hash` for all 6 output tables as the main run `20261001T224131Z_e30e42c2`, including the 116.7M-row fact table.
The clean copy predated a final edit to an error message and the report generator, neither of which is on the data
path. Later runs (`20261002T081145Z_282797bf`, which added the CAT-11 diagnostic, and `20261002T132502Z_282797bf`, which dropped the
constant `variant` column; ADR-0020) produce the same table hashes.
