# Data sources (source register)

> **Generated file.** Rendered by `lsc-pop docs` from `config/sources.yaml` and `data/manifest.json`.
> Edit those, not this file. Terms: [glossary](glossary.md).

Every source is published under the Open Government Licence v3.0 unless stated otherwise.

| ID | Role | Title | Release | Status | Enabled | Downloaded |
|---|---|---|---|---|---|---|
| S1 | Ethnicity margin (IPF row margins) | Census 2021 RM032 - Ethnic group by sex by age (LSOA 2021) | 2023-03-28 | census | yes | 1/1 |
| S2 | Single-year age margin (IPF column margins) | Census 2021 RM200 - Sex by single year of age (LSOA 2021) | 2023-03-28 | census | yes | 1/1 |
| S3 | Ethnicity-specific age-shape seed for IPF; LA-level validation | Census 2021 ethnic group (20) x sex x single year of age, LTLA 2021 (custom dataset) | 2023-03-28 | census | yes | 2/2 |
| S4 | Validation of 2021 ethnic totals | Census 2021 TS021 - Ethnic group (LSOA 2021) | 2022-11-29 | census | yes | 1/1 |
| S5 | Current-year totals (roll-forward target) | ONS LSOA population estimates by single year of age and sex, mid-2022 (revised) to mid-2024 | 2025-11-07 | supporting information | yes | 1/1 |
| S5b | Validation: accredited broad-age totals vs single-year file | ONS LSOA population estimates by broad age and sex, mid-2022 (revised) to mid-2024 (accredited) | 2025-11-07 | accredited official statistics | yes | 1/1 |
| S6 | Provisional mid-2025 scaling (out of scope; ADR-0006) | ONS mid-2025 population estimates for local authorities, England and Wales | 2026-07-29 | accredited official statistics | no | 0/1 |
| S7 | Geography lookup and footprint | LSOA (2021) to SICBL to ICB to NHSER to LAD (April 2026) Lookup in EN | 2026-04-20 | lookup | yes | 1/1 |
| S7b | LSOA21 -> MSOA21 (for S9 catchment apportionment) and LSOA21 -> LTLA 2021 (for the S3 seed) | Output Area (2021) to LSOA to MSOA to LAD (December 2021) Exact Fit Lookup in EW (V3) | 2023-03-20 | lookup | yes | 1/1 |
| S7c | LTLA 2021 -> ONS region (for the regional fallback seed, ADR-0011) | Local Authority District to Region (December 2022) Lookup in EN | 2022-12-31 | lookup | yes | 1/1 |
| S7d | LTLA 2021 -> upper-tier LA (diagnostic only: OHID T5 comparison, ADR-0019) | Local Authority District to County and Unitary Authority (December 2022) Lookup in EW | 2022-12-31 | lookup | yes | 1/1 |
| S8 | Deprivation (IMD and domains) | English Indices of Deprivation 2025 - File 7: all ranks, scores, deciles and population denominators | 2025-11-17 | accredited official statistics | yes | 1/1 |
| S9 | Trust catchment proportions (MSOA 2021) and trust-level validation comparators | OHID NHS acute (hospital) trust catchment populations, April 2026 - data tables | 2026-05-29 | official statistics | yes | 1/1 |

## S1: Census 2021 RM032 - Ethnic group by sex by age (LSOA 2021)

| Field | Value |
|---|---|
| Role | Ethnicity margin (IPF row margins) |
| Publisher | ONS (via Nomis, dataset NM_2132_1) |
| Landing page | <https://www.nomisweb.co.uk/datasets/c2021rm032> |
| Release date | 2023-03-28 |
| Edition | Census 2021, RM032 version 1 |
| Reference date | 2021-03-21 |
| Geography | LSOA 2021, England (E01*), 33,755 areas |
| Status | census |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `rm032_lsoa21_england.csv` | 2026-10-01T18:02:30Z | 172.1 MB | `87f8afdcba561e88918f3001b1aeb1d5be101a55ab6cb36078418a2e358672e2` | <https://www.nomisweb.co.uk/api/v01/dataset/NM_2132_1.data.csv?geography=2092957699TYPE151&c2021_eth_20=0...19&c2021_age_6=1...5&c_sex=1,2&measures=20100&select=geography_code,c2021_eth_20,c2021_age_6,c_sex,obs_value,record_count> |
| ↳ Long CSV: geography_code, c2021_eth_20 (0=total, 1-19), c2021_age_6 (1-5), c_sex (1=F, 2=M), obs_value. Pages joined; Nomis RECORD_COUNT column retained. | | | | |

**Known quirks**

- Ethnic group codes 1-19 follow ethnic_group_tb_20b order (1 Bangladeshi ... 13 White British ... 19 Any other); verified identical to config/mappings/ethnicity_19_to_6.csv.
- Nomis omits the 'Does not apply' (-8) category. We fetch the all-groups total (code 0) instead and check that it equals the sum of codes 1-19 per LSOA x sex x band. This is the same check as 'Does not apply' = 0 (brief §10).
- Age bands (c2021_age_6 / ONS resident_age_5c): 1 = 24 and under, 2 = 25-34, 3 = 35-49, 4 = 50-64, 5 = 65 and over.
- Cell key perturbation and targeted record swapping: LSOA x sex totals do not exactly match RM200 or TS021 (reconciled in Stage B).
- The ONS API at area-type=lsoa returns identical values (spot-checked on E01011954). It is an equivalent fallback.
- Nomis returns rows in its own geography order, not code order. Downstream stages sort.

## S2: Census 2021 RM200 - Sex by single year of age (LSOA 2021)

| Field | Value |
|---|---|
| Role | Single-year age margin (IPF column margins) |
| Publisher | ONS (via Nomis, dataset NM_2300_1) |
| Landing page | <https://www.nomisweb.co.uk/datasets/c2021rm200> |
| Release date | 2023-03-28 |
| Edition | Census 2021, RM200 version 1 |
| Reference date | 2021-03-21 |
| Geography | LSOA 2021, England (E01*), 33,755 areas |
| Status | census |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `rm200_lsoa21_england.csv` | 2026-10-01T18:12:22Z | 150.0 MB | `056bf02fe57a8bc73df2cc312c3199cb02264f62a29639a9da5353d0c3f0daa1` | <https://www.nomisweb.co.uk/api/v01/dataset/NM_2300_1.data.csv?geography=2092957699TYPE151&c2021_age_92=0...91&c_sex=1,2&measures=20100&select=geography_code,c2021_age_92,c_sex,obs_value,record_count> |
| ↳ Long CSV: geography_code, c2021_age_92 (0=total; 1-91 = age 0..90+, i.e. age = code - 1), c_sex, obs_value. | | | | |

**Known quirks**

- TS009 has no LSOA level (LA and above only), so RM200 is the LSOA single-year source.
- Nomis age code = age + 1 (1 = under 1, 91 = 90 and over). Code 0 = all ages.
- Independently perturbed from RM032 (see S1).

## S3: Census 2021 ethnic group (20) x sex x single year of age, LTLA 2021 (custom dataset)

| Field | Value |
|---|---|
| Role | Ethnicity-specific age-shape seed for IPF; LA-level validation |
| Publisher | ONS (Create a custom dataset API, population type UR) |
| Landing page | <https://www.ons.gov.uk/datasets/create> |
| Release date | 2023-03-28 |
| Edition | Census 2021 custom dataset API (api.beta.ons.gov.uk/v1), queried 2026-10 |
| Reference date | 2021-03-21 |
| Geography | LTLA 2021, England (E06/E07/E08/E09) |
| Status | census |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `ltla21_eth20_sex_age91.jsonl.gz` | 2026-10-01T18:13:04Z | 9.3 MB | `6c09e7478a4dcf0beefaff9cf9e0a3fb800815188e2ef493a7ccbc52ef0414ac` | <https://api.beta.ons.gov.uk/v1/population-types/UR/census-observations?dimensions=ethnic_group_tb_20b,sex,resident_age_91a> |
| ↳ Primary seed: single year 0-90+. Disclosure control blocks a few small LTLAs (recorded per batch). | | | | |
| `ltla21_eth20_sex_age23.jsonl.gz` | 2026-10-01T18:13:15Z | 2.0 MB | `8881f4e2d4c86226f1f32f4da75288ea470255f8161957ab46aa29e0a03d4957` | <https://api.beta.ons.gov.uk/v1/population-types/UR/census-observations?dimensions=ethnic_group_tb_20b,sex,resident_age_23a> |
| ↳ Fallback seed (23 age categories) for LTLAs blocked at single year of age. | | | | |

**Known quirks**

- The API blocks whole areas, not cells, when a query is too detailed for an area. At 91a, 8 English LTLAs are blocked (E06000053 Isles of Scilly, E07000026, E07000029, E07000030, E07000046, E07000047, E07000166, E07000167). At 23a only Isles of Scilly is blocked. ADR-0011 sets the fallbacks.
- MSOA is unusable at finer ages: 41% of MSOAs are blocked at 23a and 8.6% at 8b. LSOA x 91a is refused as 'too large'.
- API caps a response at 100,000 rows (HTTP 403 beyond). Cloudflare blocks default library User-Agents and rate-limits (HTTP 429, backoff applied).
- Perturbed independently of RM032/RM200. Summed to RM032 bands at LTLA, 36% of cells match exactly, with mean abs diff 1.3 and max 12.
- The API includes 'Does not apply' (-8), always 0 for usual residents.

## S4: Census 2021 TS021 - Ethnic group (LSOA 2021)

| Field | Value |
|---|---|
| Role | Validation of 2021 ethnic totals |
| Publisher | ONS (via Nomis bulk download) |
| Landing page | <https://www.nomisweb.co.uk/sources/census_2021_bulk> |
| Release date | 2022-11-29 |
| Edition | Nomis bulk zip census2021-ts021 (ONS TS021 is at version 3, 2023-03-28) |
| Reference date | 2021-03-21 |
| Geography | OA/LSOA/MSOA/LTLA/UTLA/region/country 2021, England and Wales |
| Status | census |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `census2021-ts021.zip` | 2026-10-01T18:13:16Z | 5.6 MB | `ca2301d72a2de7e91c495695b6dceddb4dd318b580ae530b61582f851144fc78` | <https://www.nomisweb.co.uk/output/census/2021/census2021-ts021.zip> |
| ↳ Zip of wide CSVs; census2021-ts021-lsoa.csv has 35,672 rows (E+W), total + 5 high-level + 19 detailed groups. | | | | |

**Known quirks**

- Wide format with 5 high-level groups interleaved among the 19 detailed groups. Select by label, not position.
- England and Wales; filter E01*. England LSOA total 56,490,108.
- The bulk zip predates the ONS v3 re-release (2023-03-28). Check in Stage B whether the counts differ.

## S5: ONS LSOA population estimates by single year of age and sex, mid-2022 (revised) to mid-2024

| Field | Value |
|---|---|
| Role | Current-year totals (roll-forward target) |
| Publisher | ONS |
| Landing page | <https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareamidyearpopulationestimates> |
| Release date | 2025-11-07 |
| Edition | Mid-2022 revised (Nov 2025) to mid-2024 (SAPE2024) |
| Reference date | 2024-06-30 |
| Geography | LSOA 2021, England and Wales (33,755 England) |
| Status | supporting information |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `sapelsoasyoa20222024.xlsx` | 2026-10-01T18:13:24Z | 83.4 MB | `2a59e9332112639ff37552641193aedaf14ff10db99d12e034505959eabd8909` | <https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareamidyearpopulationestimates/mid2022revisednov2025tomid2024/sapelsoasyoa20222024.xlsx> |
| ↳ Sheets 'Mid-2022 LSOA 2021', 'Mid-2023 LSOA 2021', 'Mid-2024 LSOA 2021'; header on row 4; LAD 2023 code/name, LSOA code/name, Total, F0..F90, M0..M90. | | | | |

**Known quirks**

- Single-year-of-age LSOA estimates are 'supporting information', not accredited official statistics (Note 4). ONS doesn't recommend using them directly.
- F90/M90 is the open-ended 90+ group (no '+' in the header).
- LAD columns are LAD 2023 codes. Barnsley (E08000016) and Sheffield (E08000019) differ from the LAD 2026 codes in S7 (E08000038/E08000039). Use S7 for LAD.
- Mid-2024 England total 58,620,101 across 33,755 LSOAs. Total = sum of the 182 cells exactly. Integers.
- Mid-2025 LSOA estimates are NOT yet published. The ONS release calendar lists them as provisional for Dec 2026 to Jan 2027 (checked 2026-10-01).

## S5b: ONS LSOA population estimates by broad age and sex, mid-2022 (revised) to mid-2024 (accredited)

| Field | Value |
|---|---|
| Role | Validation: accredited broad-age totals vs single-year file |
| Publisher | ONS |
| Landing page | <https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareamidyearpopulationestimatesnationalstatistics> |
| Release date | 2025-11-07 |
| Edition | Mid-2022 revised (Nov 2025) to mid-2024 |
| Reference date | 2024-06-30 |
| Geography | LSOA 2021, England and Wales |
| Status | accredited official statistics |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `sapelsoabroadage20222024.xlsx` | 2026-10-01T18:13:25Z | 12.5 MB | `b77a07033dca67a204ff7d306819bb90241234ea0ce4e3c259ebf98d7c7e6f28` | <https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/lowersuperoutputareamidyearpopulationestimatesnationalstatistics/mid2022revisednov2025tomid2024/sapelsoabroadage20222024.xlsx> |

**Known quirks**

- Layout not yet inspected (Phase 6).

## S6: ONS mid-2025 population estimates for local authorities, England and Wales

| Field | Value |
|---|---|
| Role | Provisional mid-2025 scaling (out of scope; ADR-0006) |
| Publisher | ONS |
| Landing page | <https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/estimatesofthepopulationforenglandandwales> |
| Release date | 2026-07-29 |
| Edition | Mid-2025, 2023 local authority boundaries |
| Reference date | 2025-06-30 |
| Geography | LAD 2023 |
| Status | accredited official statistics |
| Licence | Open Government Licence v3.0 |
| Enabled | no |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `mye25tablesew.xlsx` | _not downloaded_ | | | <https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/estimatesofthepopulationforenglandandwales/mid20252023localauthorityboundaries/mye25tablesew.xlsx> |

**Known quirks**

- Disabled: mid-2025 variant out of scope (ADR-0006). URL constructed from the dataset page and not fetched.

## S7: LSOA (2021) to SICBL to ICB to NHSER to LAD (April 2026) Lookup in EN

| Field | Value |
|---|---|
| Role | Geography lookup and footprint |
| Publisher | ONS Open Geography Portal (item bebf631bb1ac40cf9ec7dc060897ca99) |
| Landing page | <https://geoportal.statistics.gov.uk/datasets/bebf631bb1ac40cf9ec7dc060897ca99> |
| Release date | 2026-04-20 |
| Edition | April 2026 |
| Reference date | 2026-04-01 |
| Geography | LSOA 2021 -> SICBL 2026 -> ICB 2026 -> NHSER 2026; LAD 2026 |
| Status | lookup |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `lsoa21_sicbl26_icb26_nhser26_lad26.csv` | 2026-10-01T18:13:26Z | 6.2 MB | `6cdd0cb55f2e05ec4e0ab74189a7580addb6bd03ee3b0ee370da6128218bce50` | <https://hub.arcgis.com/api/v3/datasets/bebf631bb1ac40cf9ec7dc060897ca99_0/downloads/data?format=csv&spatialRefId=4326> |
| ↳ LSOA21CD, LSOA21NM, SICBL26CD/CDH/NM, ICB26CD/CDH/NM, NHSER26CD/CDH/NM, LAD26CD/NM, ObjectId. 33,755 rows. | | | | |

**Known quirks**

- UTF-8 with BOM.
- 36 ICBs in April 2026, down from 42 in April 2025 after mergers. 10,207 LSOAs changed ICB. NHS Lancashire and South Cumbria ICB (E54000048 / QE1) is unchanged: 1,060 LSOAs, 8 SICBLs, spanning 17 LAD26s (incl. 106 LSOAs in Westmorland and Furness, 6 in Cumberland, 3 in North Yorkshire).
- The hub CSV is generated on demand. A re-download may differ byte-wise; the manifest pins the copy used.

## S7b: Output Area (2021) to LSOA to MSOA to LAD (December 2021) Exact Fit Lookup in EW (V3)

| Field | Value |
|---|---|
| Role | LSOA21 -> MSOA21 (for S9 catchment apportionment) and LSOA21 -> LTLA 2021 (for the S3 seed) |
| Publisher | ONS Open Geography Portal (item b9ca90c10aaa4b8d9791e9859a38ca67) |
| Landing page | <https://geoportal.statistics.gov.uk/datasets/b9ca90c10aaa4b8d9791e9859a38ca67> |
| Release date | 2023-03-20 |
| Edition | V3 |
| Reference date | 2021-12-31 |
| Geography | OA21 -> LSOA21 -> MSOA21 -> LAD (December 2021, labelled LAD22), England and Wales |
| Status | lookup |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `oa21_lsoa21_msoa21_lad22_exactfit_v3.csv` | 2026-10-01T18:14:01Z | 17.4 MB | `1b7e715936374c586efbe669d82e3f3d6d093dc5295c2d99ce6ea2349f85153a` | <https://hub.arcgis.com/api/v3/datasets/b9ca90c10aaa4b8d9791e9859a38ca67_0/downloads/data?format=csv&spatialRefId=4326> |
| ↳ OA21CD, LSOA21CD/NM/NMW, MSOA21CD/NM/NMW, LAD22CD/NM/NMW, ObjectId. 188,880 OAs (E+W). | | | | |

**Known quirks**

- Exact fit: each England LSOA21 maps to exactly one MSOA21 (6,856) and one LAD (309), checked 2026-10-01.
- The LAD columns are labelled LAD22, but the 309 English codes match the ONS custom-dataset API's 2021 LTLA list exactly, which is what the S3 seed is keyed on. They predate the 2023 Cumbria, North Yorkshire and Somerset reorganisations (e.g. E07000027 Barrow-in-Furness, E07000031 South Lakeland).
- UTF-8 with BOM.

## S7c: Local Authority District to Region (December 2022) Lookup in EN

| Field | Value |
|---|---|
| Role | LTLA 2021 -> ONS region (for the regional fallback seed, ADR-0011) |
| Publisher | ONS Open Geography Portal (item 78b348cd8fb04037ada3c862aa054428) |
| Landing page | <https://geoportal.statistics.gov.uk/datasets/78b348cd8fb04037ada3c862aa054428> |
| Release date | 2022-12-31 |
| Edition | December 2022 |
| Reference date | 2022-12-31 |
| Geography | LAD (December 2022) -> Region, England (309 LADs, 9 regions) |
| Status | lookup |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `lad22_rgn22.csv` | 2026-10-01T18:41:51Z | 14.7 KB | `b20db2949c8e3ff9a505136e920c5b0021ca745a92998e82d867333f9efb2c5a` | <https://hub.arcgis.com/api/v3/datasets/78b348cd8fb04037ada3c862aa054428_0/downloads/data?format=csv&spatialRefId=4326> |
| ↳ LAD22CD, LAD22NM, RGN22CD, RGN22NM, ObjectId. | | | | |

**Known quirks**

- December 2022 LADs are identical to the 2021 LTLAs used by the Census (all 309 S7b codes match).
- UTF-8 with BOM.

## S7d: Local Authority District to County and Unitary Authority (December 2022) Lookup in EW

| Field | Value |
|---|---|
| Role | LTLA 2021 -> upper-tier LA (diagnostic only: OHID T5 comparison, ADR-0019) |
| Publisher | ONS Open Geography Portal (item b1c0deb950cf4a619d332d17270845bb) |
| Landing page | <https://geoportal.statistics.gov.uk/datasets/b1c0deb950cf4a619d332d17270845bb> |
| Release date | 2022-12-31 |
| Edition | December 2022 |
| Reference date | 2022-12-31 |
| Geography | LTLA 2022 (= 2021 LTLAs) -> county / unitary authority, England and Wales |
| Status | lookup |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `lad22_ctyua22.csv` | 2026-10-02T08:10:06Z | 15.3 KB | `be1ac3e16093a4979bf5bb6ea47bb372cdd50363e7c4848d197347277807c670` | <https://hub.arcgis.com/api/v3/datasets/b1c0deb950cf4a619d332d17270845bb_0/downloads/data?format=csv&spatialRefId=4326> |
| ↳ LTLA22CD, LTLA22NM, UTLA22CD, UTLA22NM, ObjectId. | | | | |

**Known quirks**

- Used only to test hypotheses about OHID's 'All (5% and above)' ethnicity method. Never used for estimates.
- UTF-8 with BOM. Column names are LTLA22CD/UTLA22CD (not LAD22CD).

## S8: English Indices of Deprivation 2025 - File 7: all ranks, scores, deciles and population denominators

| Field | Value |
|---|---|
| Role | Deprivation (IMD and domains) |
| Publisher | MHCLG |
| Landing page | <https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025> |
| Release date | 2025-11-17 |
| Edition | IoD 2025 (first published 2025-10-30; files corrected 2025-11-17) |
| Reference date | 2025 |
| Geography | LSOA 2021, England, 33,755 areas |
| Status | accredited official statistics |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv` | 2026-10-01T18:13:27Z | 9.4 MB | `b1b716aa2e476449f987b9de3e08255b4794eabfd270626de5de18b2f5eff3ef` | <https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv> |
| ↳ 56 columns: LSOA/LAD 2024 identifiers; IMD and 7 domain scores/ranks/deciles; IDACI, IDAOPI; 6 sub-domains; mid-2022 population denominators. | | | | |

**Known quirks**

- 17 Nov 2025 correction: LSOA E01027305 reassigned from Cherwell to West Northamptonshire (data values unchanged).
- LAD 2024 codes match S5's LAD 2023 codes; use S7 for LAD 2026.
- One header truncated ('...Sub-domain Decile (where 1 is most deprived 10% of LSO'). Match columns by prefix.
- Population denominators are mid-2022 and are not used as population inputs.
- Rank 1 = most deprived. Deciles have ~3,375-3,376 LSOAs each.

## S9: OHID NHS acute (hospital) trust catchment populations, April 2026 - data tables

| Field | Value |
|---|---|
| Role | Trust catchment proportions (MSOA 2021) and trust-level validation comparators |
| Publisher | OHID (DHSC) |
| Landing page | <https://www.gov.uk/government/statistics/nhs-acute-hospital-trust-catchment-populations-april-2026> |
| Release date | 2026-05-29 |
| Edition | April 2026 edition; first published 2026-04-14, ethnicity/deprivation added 2026-05-11, file replaced 2026-05-29 (Last-Modified) |
| Reference date | Catchment years 2023 and 2024 (HES FY2021/22-2024/25; ONS MYE 2022 populations) |
| Geography | MSOA 2021, England (6,856), x 134 acute trusts |
| Status | official statistics |
| Licence | Open Government Licence v3.0 |
| Enabled | yes |

**Files**

| File | Retrieved | Size | SHA-256 | URL |
|---|---|---|---|---|
| `nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods` | 2026-10-01T18:13:27Z | 18.0 MB | `7f7639b2cc056fe0d4c388a3d71eb59015b219bcba8cba78e1672c0b7b47a997` | <https://assets.publishing.service.gov.uk/media/6a199144050971fbebf3bc3f/nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods> |
| ↳ Sheets T1 Trust_analysis (trust x sex x 5yr), T2-T4 All/Elective/Emergency (MSOA x trust proportions, all ages), T5 Ethnicity (5 groups), T6 Deprivation (mean IMD 2025 score), T7 Trust_area_lookup, T8 HES_years_covered. | | | | |

**Known quirks**

- Catchment proportions are by MSOA 2021 and all ages only. Age/sex-specific proportions are used internally by OHID but not published.
- Proportions are rounded to 3 dp, counts to the nearest 5, and trust-MSOA cells with fewer than 8 patients are suppressed. Each MSOA's proportions sum to 0.88-0.997 (mean 0.978) across trusts, with no 'other' row.
- Populations are ONS MYE 2022 for both catchment years, not mid-2024.
- T5 ethnicity has 5 groups only, with two selection methods ('All (5% and above)' vs 'First past the post') that give very different results for some trusts (e.g. RXR Asian 10.8% vs 21.3%).
- T6 gives the population-weighted mean IMD 2025 score and rank only, with no quintiles.
- RBN (Mersey and West Lancashire Teaching Hospitals) covers former Southport & Ormskirk activity. RW5 (LSCFT) is not included (it isn't an acute trust).
- Large ODS (content.xml ~550 MB uncompressed). Pandas/odfpy is very slow, so the Phase 7 reader should use a streaming XML parser.
- The file was replaced silently on 2026-05-29 with no change note. The internal 'Published 28 April 2026' doesn't match gov.uk's dates.
