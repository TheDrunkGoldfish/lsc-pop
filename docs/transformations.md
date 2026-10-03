# Transformations

> **Generated file.** Rendered by `lsc-pop docs` from `outputs/<run_id>/run_log.jsonl` of the latest complete run. Don't edit by hand. Terms: [glossary](glossary.md).

Run `20261003T104609Z_97bc3364_07ee74de` · started 2026-10-03T10:46:09Z · config `97bc33643549` · code `07ee74def47d` · uv.lock `67e24d4e0904` · git dbf9c1cb6c6d65e05e1c7f9be8b81ff1e75ed78e

## Summary

| # | Step | Status | Rows in | Rows out | Population in | Population out | Dropped / added |
|---|---|---|---|---|---|---|---|
| 1 | `geography.read_nhs` | ok | 33,755 | 33,755 |  |  |  |
| 2 | `geography.read_census` | ok | 188,880 | 33,755 |  |  | −153,208 exact duplicate rows after column selection (e.g. OA rows); −1,917 non-England LSOAs |
| 3 | `geography.read_ltla_region` | ok | 309 | 309 |  |  |  |
| 4 | `geography.build_lookup` | ok | 67,819 | 33,755 |  |  |  |
| 5 | `census.load_rm032` | ok | 6,751,000 | 6,413,450 |  | 56,490,573 (F 28,834,314, M 27,656,259) | −337,550 all-groups total rows (eth=0), used only for CEN-01 |
| 6 | `census.load_rm200` | ok | 6,210,920 | 6,143,410 |  | 56,489,042 (F 28,832,682, M 27,656,360) | −67,510 all-ages total rows (code 0), used only for CEN-03 |
| 7 | `census.load_ts021` | ok | 35,672 | 641,345 |  | 56,490,108 |  |
| 8 | `census.load_seed_age_91a` | ok | 1,095,640 | 1,040,858 |  | 56,040,038 (F 28,606,005, M 27,434,033) | −54,782 'Does not apply' rows (all zero; CEN-07) |
| 9 | `census.load_seed_age_23a` | ok | 283,360 | 269,192 |  | 56,487,999 (F 28,832,825, M 27,655,174) | −14,168 'Does not apply' rows (all zero; CEN-07) |
| 10 | `census.compare_tables` | ok | 0 | 0 |  |  |  |
| 11 | `census.reconcile_margins[rm200]` | ok | 12,556,860 | 12,556,860 | 56,490,573 (F 28,834,314, M 27,656,259) | 112,978,084 (F 57,665,364, M 55,312,720) |  |
| 12 | `base.build_seed` | ok | 1,310,050 | 1,068,522 | 56,040,038 (F 28,606,005, M 27,434,033) | 57,058,043 (F 29,126,254, M 27,931,789) |  |
| 13 | `base.fit` | ok | 0 | 0 |  |  |  |
| 14 | `base.sensitivity[floor=0.01]` | ok | 0 | 0 |  |  |  |
| 15 | `base.sensitivity[floor=0.5]` | ok | 0 | 0 |  |  |  |
| 16 | `base.sensitivity[floor=2]` | ok | 0 | 0 |  |  |  |
| 17 | `base.sensitivity[uniform seed]` | ok | 0 | 0 |  |  |  |
| 18 | `base.write` | ok | 0 | 116,724,790 |  | 56,489,042 (F 28,832,682, M 27,656,360) |  |
| 19 | `rollforward.load_mye` | ok | 35,672 | 6,143,410 |  | 58,620,101 (F 29,895,762, M 28,724,339) |  |
| 20 | `rollforward.check_broad_age` | ok | 35,672 | 0 |  |  |  |
| 21 | `rollforward.apply[cohort]` | ok | 116,724,790 | 116,724,790 | 56,489,042 (F 28,832,682, M 27,656,360) | 58,620,101 (F 29,895,762, M 28,724,339) |  |
| 22 | `rollforward.apply[static]` | ok | 116,724,790 | 116,724,790 | 56,489,042 (F 28,832,682, M 27,656,360) | 58,620,101 (F 29,895,762, M 28,724,339) |  |
| 23 | `rollforward.apply[cohort]` | ok | 116,724,790 | 116,724,790 | 56,489,042 (F 28,832,682, M 27,656,360) | 58,620,101 (F 29,895,762, M 28,724,339) |  |
| 24 | `base.build_seed` | ok | 1,310,050 | 1,068,522 | 56,040,038 (F 28,606,005, M 27,434,033) | 57,058,043 (F 29,126,254, M 27,931,789) |  |
| 25 | `rollforward.sensitivity_fit[floor=0.01]` | ok | 0 | 0 |  |  |  |
| 26 | `rollforward.apply[cohort]` | ok | 3,665,480 | 3,665,480 | 1,717,308 (F 872,370, M 844,938) | 1,790,318 (F 905,499, M 884,819) |  |
| 27 | `rollforward.sensitivity_fit[floor=2]` | ok | 0 | 0 |  |  |  |
| 28 | `rollforward.apply[cohort]` | ok | 3,665,480 | 3,665,480 | 1,717,308 (F 872,370, M 844,938) | 1,790,318 (F 905,499, M 884,819) |  |
| 29 | `rollforward.write` | ok | 0 | 116,724,790 |  | 58,620,101 (F 29,895,762, M 28,724,339) |  |
| 30 | `deprivation.load_iod` | ok | 33,755 | 33,755 |  |  |  |
| 31 | `deprivation.derive` | ok | 33,755 | 33,755 |  |  |  |
| 32 | `catchments.load_ohid` | ok | 151,885 | 0 |  |  |  |
| 33 | `catchments.build_bridge` | ok | 60,462 | 337,059 |  |  | +33,755 UNASSIGNED rows (1 − Σ published) |
| 34 | `catchments.host_icb` | ok | 1,901 | 134 |  |  |  |
| 35 | `outputs.validate` | ok | 116,724,790 | 0 | 58,620,101 (F 29,895,762, M 28,724,339) |  |  |
| 36 | `outputs.write` | ok | 0 | 117,103,468 |  | 58,620,101 (F 29,895,762, M 28,724,339) |  |

## Steps in detail

### 1. `geography.read_nhs`

2026-10-03T10:46:09.409Z → 2026-10-03T10:46:09.481Z · ok

Parameters: `{"columns": {"ICB26CD": "icb_code", "ICB26CDH": "icb_ods_code", "ICB26NM": "icb_name", "LAD26CD": "lad_code", "LAD26NM": "lad_name", "LSOA21CD": "lsoa21_code", "LSOA21NM": "lsoa21_name", "NHSER26CD": "nhser_code", "NHSER26CDH": "nhser_ods_code", "NHSER26NM": "nhser_name", "SICBL26CD": "sicbl_code", "SICBL26CDH": "sicbl_ods_code", "SICBL26NM": "sicbl_name"}, "file": "lsoa21_sicbl26_icb26_nhser26_lad26.csv", "key": "lsoa21_code", "source": "S7", "vintage": "2026-04"}`

- input **S7/lsoa21_sicbl26_icb26_nhser26_lad26.csv**: 33,755 rows · hash `6cdd0cb55f2e`
- output **nhs**: 33,755 rows · hash `4fdb8b34d517`

### 2. `geography.read_census`

2026-10-03T10:46:09.481Z → 2026-10-03T10:46:09.641Z · ok

Parameters: `{"columns": {"LAD22CD": "ltla21_code", "LAD22NM": "ltla21_name", "LSOA21CD": "lsoa21_code", "MSOA21CD": "msoa21_code", "MSOA21NM": "msoa21_name"}, "file": "oa21_lsoa21_msoa21_lad22_exactfit_v3.csv", "key": "lsoa21_code", "source": "S7b", "vintage": "2021-12"}`

- input **S7b/oa21_lsoa21_msoa21_lad22_exactfit_v3.csv**: 188,880 rows · hash `1b7e71593637`
- output **census**: 33,755 rows · hash `5d536e9eb848`

### 3. `geography.read_ltla_region`

2026-10-03T10:46:09.641Z → 2026-10-03T10:46:09.643Z · ok

Parameters: `{"columns": {"LAD22CD": "ltla21_code", "RGN22CD": "rgn21_code", "RGN22NM": "rgn21_name"}, "file": "lad22_rgn22.csv", "key": "ltla21_code", "source": "S7c", "vintage": "2022-12"}`

- input **S7c/lad22_rgn22.csv**: 309 rows · hash `b20db2949c8e`
- output **ltla_region**: 309 rows · hash `e89f5dadc9c0`

### 4. `geography.build_lookup`

2026-10-03T10:46:09.643Z → 2026-10-03T10:46:09.731Z · ok

Parameters: `{"footprint": {"extra_lsoas_from_trust_catchments": [], "focus_icb_codes": ["E54000048"], "icb_codes": [], "mode": "england"}}`

- input **nhs**: 33,755 rows · hash `4fdb8b34d517`
- input **census**: 33,755 rows · hash `5d536e9eb848`
- input **ltla_region**: 309 rows · hash `e89f5dadc9c0`
- output **lsoa_lookup**: 33,755 rows · hash `c4fcad816f84`
- note: 33755 LSOAs; footprint 33755 (england); focus ICB 1060

### 5. `census.load_rm032`

2026-10-03T10:46:09.891Z → 2026-10-03T10:46:12.443Z · ok

- input **S1/rm032_lsoa21_england.csv**: 6,751,000 rows · hash `87f8afdcba56`
- output **rm032**: 6,413,450 rows · hash `6d693bab0a43` · population 56,490,573 (F 28,834,314, M 27,656,259)

### 6. `census.load_rm200`

2026-10-03T10:46:12.443Z → 2026-10-03T10:46:14.578Z · ok

- input **S2/rm200_lsoa21_england.csv**: 6,210,920 rows · hash `056bf02fe57a`
- output **rm200**: 6,143,410 rows · hash `4dd1149b3145` · population 56,489,042 (F 28,832,682, M 27,656,360)
- note: Nomis age code converted to age = code - 1 (code 91 = 90+)

### 7. `census.load_ts021`

2026-10-03T10:46:14.580Z → 2026-10-03T10:46:14.694Z · ok

- input **S4/census2021-ts021.zip!census2021-ts021-lsoa.csv**: 35,672 rows · hash `ca2301d72a2d`
- output **ts021**: 641,345 rows · hash `6807c2e20f6e` · population 56,490,108
- note: wide -> long by label; 5 high-level group columns ignored (derivable)

### 8. `census.load_seed_age_91a`

2026-10-03T10:46:14.694Z → 2026-10-03T10:46:19.142Z · ok

- input **S3/ltla21_eth20_sex_age91.jsonl.gz**: 1,095,640 rows · hash `6c09e7478a4d`
- output **seed_age_91a**: 1,040,858 rows · hash `a573d2f85e77` · population 56,040,038 (F 28,606,005, M 27,434,033)
- note: blocked LTLAs (8): E06000053, E07000026, E07000029, E07000030, E07000046, E07000047, E07000166, E07000167

### 9. `census.load_seed_age_23a`

2026-10-03T10:46:19.198Z → 2026-10-03T10:46:20.297Z · ok

- input **S3/ltla21_eth20_sex_age23.jsonl.gz**: 283,360 rows · hash `8881f4e2d4c8`
- output **seed_age_23a**: 269,192 rows · hash `66f9c454d299` · population 56,487,999 (F 28,832,825, M 27,655,174)
- note: blocked LTLAs (1): E06000053

### 10. `census.compare_tables`

2026-10-03T10:46:20.324Z → 2026-10-03T10:46:21.604Z · ok

- note: rm032_vs_rm200_lsoa_sex: {"cells": 67510, "share_identical": 0.0682, "mean_abs": 4.771, "p50_abs": 4.0, "p95_abs": 12.0, "p99_abs": 16.0, "max_abs": 29.0, "net": 1531.0, "p95_rel": 0.015, "max_rel": 0.0377}
- note: rm032_vs_rm200_lsoa_sex_band: {"cells": 337550, "share_identical": 0.1717, "mean_abs": 2.047, "p50_abs": 2.0, "p95_abs": 5.0, "p99_abs": 8.0, "max_abs": 16.0, "net": 1531.0, "p95_rel": 0.042, "max_rel": 0.75}
- note: focus_rm032_vs_rm200_lsoa_sex_band: {"cells": 10600, "share_identical": 0.1827, "mean_abs": 1.92, "p50_abs": 2.0, "p95_abs": 5.0, "p99_abs": 7.0, "max_abs": 13.0, "net": 527.0, "p95_rel": 0.0396, "max_rel": 0.1429}
- note: band_zero_inconsistency: {"rm032_zero_rm200_pos": 0, "rm200_zero_rm032_pos": 0, "persons_rm032_zero_rm200_pos": 0, "persons_rm200_zero_rm032_pos": 0}
- note: rm032_vs_ts021_lsoa_eth: {"cells": 641345, "share_identical": 0.604, "mean_abs": 0.627, "p50_abs": 0.0, "p95_abs": 3.0, "p99_abs": 4.0, "max_abs": 11.0, "net": 465.0, "p95_rel": 0.2857, "max_rel": 5.0}
- note: totals: {"rm032": 56490573, "rm200": 56489042, "ts021": 56490108}
- note: seed91_vs_rm032_ltla_eth_sex_band: {"cells": 57190, "share_identical": 0.2425, "mean_abs": 2.612, "p50_abs": 2.0, "p95_abs": 9.0, "p99_abs": 13.0, "max_abs": 37.0, "net": -815.0, "p95_rel": 0.1538, "max_rel": 3.0}

### 11. `census.reconcile_margins[rm200]`

2026-10-03T10:46:21.606Z → 2026-10-03T10:46:29.007Z · ok

Parameters: `{"source": "rm200"}`

- input **rm032**: 6,413,450 rows · hash `6d693bab0a43` · population 56,490,573 (F 28,834,314, M 27,656,259)
- input **rm200**: 6,143,410 rows · hash `4dd1149b3145` · population 56,489,042 (F 28,832,682, M 27,656,360)
- output **margins**: 12,556,860 rows · hash `65e01cd8aa2d` · population 112,978,084 (F 57,665,364, M 55,312,720)
- note: {"source": "rm200", "target_total": 56489042.0, "rm032_adjustment": {"cells": 337550, "share_identical": 0.1717, "mean_abs": 2.047, "p50_abs": 2.0, "p95_abs": 5.0, "p99_abs": 8.0, "max_abs": 16.0, "net": -1531.0, "p95_rel": 0.042, "max_rel": 0.6667}, "rm200_adjustment": {"cells": 337550, "share_identical": 1.0, "mean_abs": 0.0, "p50_abs": 0.0, "p95_abs": 0.0, "p99_abs": 0.0, "max_abs": 0.0, "net": 0.0, "p95_rel": 0.0, "max_rel": 0.0}, "bands_eth_fallback": 0, "persons_eth_fallback": 0.0, "bands_age_fallback": 0, "persons_age_fallback": 0.0, "persons_dropped_rm032_zeroed": 0.0, "persons_dropped_rm200_zeroed": 0.0}

### 12. `base.build_seed`

2026-10-03T10:46:33.151Z → 2026-10-03T10:46:33.309Z · ok

Parameters: `{"max_iter": 1000, "seed_floor": 0.5, "seed_substitutes": {"E06000053": "E06000052"}, "sensitivity_floors": [0.01, 0.5, 2.0], "tolerance": 1e-06}`

- input **seed_age91**: 1,040,858 rows · hash `a573d2f85e77` · population 56,040,038 (F 28,606,005, M 27,434,033)
- input **seed_age23**: 269,192 rows · hash `66f9c454d299` · population 56,487,999 (F 28,832,825, M 27,655,174)
- output **seed**: 1,068,522 rows · hash `9a442e16db27` · population 57,058,043 (F 29,126,254, M 27,931,789)
- note: E07000026: 23-category counts split by region E12000002 single-year shape
- note: E07000029: 23-category counts split by region E12000002 single-year shape
- note: E07000030: 23-category counts split by region E12000002 single-year shape
- note: E07000046: 23-category counts split by region E12000009 single-year shape
- note: E07000047: 23-category counts split by region E12000009 single-year shape
- note: E07000166: 23-category counts split by region E12000003 single-year shape
- note: E07000167: 23-category counts split by region E12000003 single-year shape
- note: E06000053: blocked at 91a and 23a; uses seed of E06000052
- note: {"age91": 301, "age23_region_split": 7, "substitute": 1}

### 13. `base.fit`

2026-10-03T10:46:34.150Z → 2026-10-03T10:46:40.563Z · ok

Parameters: `{"seed_floor": 0.5, "tol": 1e-06}`

- note: band 1: {"tables": 67510, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 18, "max_row_error": 4.0757778663191857e-07, "max_col_error": 1.1368683772161603e-13}
- note: band 2: {"tables": 67510, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 24, "max_row_error": 8.788811953763798e-07, "max_col_error": 2.842170943040401e-14}
- note: band 3: {"tables": 67510, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 19, "max_row_error": 7.618422799282598e-07, "max_col_error": 2.842170943040401e-14}
- note: band 4: {"tables": 67510, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 32, "max_row_error": 6.542905595097182e-07, "max_col_error": 2.842170943040401e-14}
- note: band 5: {"tables": 67510, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 19, "max_row_error": 5.47089559432834e-07, "max_col_error": 1.4210854715202004e-14}

### 14. `base.sensitivity[floor=0.01]`

2026-10-03T10:46:42.013Z → 2026-10-03T10:46:42.152Z · ok

Parameters: `{"seed_floor": 0.01, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 15, "max_row_error": 4.851916628467734e-07, "max_col_error": 2.2737367544323206e-13}
- note: band 2: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 10, "max_row_error": 6.920920156971988e-07, "max_col_error": 1.4210854715202004e-14}
- note: band 3: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 9, "max_row_error": 4.5318046248965516e-07, "max_col_error": 1.4210854715202004e-14}
- note: band 4: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 9, "max_row_error": 8.994451832222694e-07, "max_col_error": 1.0658141036401503e-14}
- note: band 5: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 7.0, "iter_max": 32, "max_row_error": 8.598293170791749e-07, "max_col_error": 7.105427357601002e-15}

### 15. `base.sensitivity[floor=0.5]`

2026-10-03T10:46:42.227Z → 2026-10-03T10:46:42.311Z · ok

Parameters: `{"seed_floor": 0.5, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 14, "max_row_error": 6.080123853280384e-07, "max_col_error": 1.1368683772161603e-13}
- note: band 2: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 7, "max_row_error": 8.918385674405727e-08, "max_col_error": 2.842170943040401e-14}
- note: band 3: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 1.8742856866538204e-07, "max_col_error": 2.1316282072803006e-14}
- note: band 4: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 9.390415129928442e-07, "max_col_error": 1.4210854715202004e-14}
- note: band 5: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 8, "max_row_error": 8.145881302823454e-07, "max_col_error": 1.0658141036401503e-14}

### 16. `base.sensitivity[floor=2]`

2026-10-03T10:46:42.386Z → 2026-10-03T10:46:42.468Z · ok

Parameters: `{"seed_floor": 2.0, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 13, "max_row_error": 2.304078066117654e-07, "max_col_error": 1.1368683772161603e-13}
- note: band 2: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 4.0, "iter_max": 6, "max_row_error": 1.746840858629639e-07, "max_col_error": 2.1316282072803006e-14}
- note: band 3: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 6.581826994533913e-08, "max_col_error": 2.842170943040401e-14}
- note: band 4: {"tables": 2120, "iter_p50": 3.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 2.2738234406460833e-07, "max_col_error": 1.0658141036401503e-14}
- note: band 5: {"tables": 2120, "iter_p50": 3.0, "iter_p95": 5.0, "iter_max": 8, "max_row_error": 8.871250400943609e-08, "max_col_error": 7.105427357601002e-15}

### 17. `base.sensitivity[uniform seed]`

2026-10-03T10:46:42.541Z → 2026-10-03T10:46:42.569Z · ok

Parameters: `{"seed_floor": 1.0, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 1.0, "iter_p95": 1.0, "iter_max": 1, "max_row_error": 2.2737367544323206e-13, "max_col_error": 1.1368683772161603e-13}
- note: band 2: {"tables": 2120, "iter_p50": 1.0, "iter_p95": 1.0, "iter_max": 1, "max_row_error": 5.684341886080802e-14, "max_col_error": 1.7763568394002505e-14}
- note: band 3: {"tables": 2120, "iter_p50": 1.0, "iter_p95": 1.0, "iter_max": 1, "max_row_error": 2.2737367544323206e-13, "max_col_error": 2.842170943040401e-14}
- note: band 4: {"tables": 2120, "iter_p50": 1.0, "iter_p95": 1.0, "iter_max": 1, "max_row_error": 1.1368683772161603e-13, "max_col_error": 1.4210854715202004e-14}
- note: band 5: {"tables": 2120, "iter_p50": 1.0, "iter_p95": 1.0, "iter_max": 1, "max_row_error": 1.1368683772161603e-13, "max_col_error": 1.4210854715202004e-14}

### 18. `base.write`

2026-10-03T10:46:42.688Z → 2026-10-03T10:46:48.643Z · ok

- output **base2021**: 116,724,790 rows · hash `a0407f3d57e2` · population 56,489,042 (F 28,832,682, M 27,656,360)

### 19. `rollforward.load_mye`

2026-10-03T10:46:49.169Z → 2026-10-03T10:47:04.698Z · ok

Parameters: `{"edition": "Mid-2022 revised (Nov 2025) to mid-2024 (SAPE2024)", "file": "sapelsoasyoa20222024.xlsx", "header_row": 3, "sheet_template": "Mid-{year} LSOA 2021", "source": "S5"}`

- input **S5/sapelsoasyoa20222024.xlsx!Mid-2024 LSOA 2021**: 35,672 rows · hash `2a59e9332112`
- output **mye**: 6,143,410 rows · hash `e2c74b53cc67` · population 58,620,101 (F 29,895,762, M 28,724,339)
- note: Mid-2024 LSOA 2021: England total 58,620,101

### 20. `rollforward.check_broad_age`

2026-10-03T10:47:04.703Z → 2026-10-03T10:47:06.100Z · ok

- input **S5b!Mid-2024 LSOA 2021**: 35,672 rows · hash `b77a07033dca`

### 21. `rollforward.apply[cohort]`

2026-10-03T10:47:06.100Z → 2026-10-03T10:47:08.548Z · ok

Parameters: `{"newborn_proxy_ages": [0], "shift_years": 3, "variant": "cohort"}`

- input **base2021**: 116,724,790 rows · hash `a0407f3d57e2` · population 56,489,042 (F 28,832,682, M 27,656,360)
- output **estimates**: 116,724,790 rows · hash `9fa09f4a4fcb` · population 58,620,101 (F 29,895,762, M 28,724,339)
- note: share fallback levels: {"direct": {"cells": 6054215, "persons": 58489072.0}, "lsoa_sex_band": {"cells": 89172, "persons": 131022.0}, "lsoa_sex_all_ages": {"cells": 23, "persons": 7.0}, "lsoa_all": {"cells": 0, "persons": 0.0}, "ltla_sex_age": {"cells": 0, "persons": 0.0}}

### 22. `rollforward.apply[static]`

2026-10-03T10:47:08.769Z → 2026-10-03T10:47:11.220Z · ok

Parameters: `{"newborn_proxy_ages": [0], "shift_years": 3, "variant": "static"}`

- input **base2021**: 116,724,790 rows · hash `a0407f3d57e2` · population 56,489,042 (F 28,832,682, M 27,656,360)
- output **estimates**: 116,724,790 rows · hash `513d953b1cd9` · population 58,620,101 (F 29,895,762, M 28,724,339)
- note: share fallback levels: {"direct": {"cells": 6004410, "persons": 58372989.0}, "lsoa_sex_band": {"cells": 138974, "persons": 247102.0}, "lsoa_sex_all_ages": {"cells": 26, "persons": 10.0}, "lsoa_all": {"cells": 0, "persons": 0.0}, "ltla_sex_age": {"cells": 0, "persons": 0.0}}

### 23. `rollforward.apply[cohort]`

2026-10-03T10:47:11.221Z → 2026-10-03T10:47:13.664Z · ok

Parameters: `{"newborn_proxy_ages": [0, 1, 2, 3, 4], "shift_years": 3, "variant": "cohort"}`

- input **base2021**: 116,724,790 rows · hash `a0407f3d57e2` · population 56,489,042 (F 28,832,682, M 27,656,360)
- output **estimates**: 116,724,790 rows · hash `bfed4d216b75` · population 58,620,101 (F 29,895,762, M 28,724,339)
- note: share fallback levels: {"direct": {"cells": 6055799, "persons": 58495262.0}, "lsoa_sex_band": {"cells": 87588, "persons": 124832.0}, "lsoa_sex_all_ages": {"cells": 23, "persons": 7.0}, "lsoa_all": {"cells": 0, "persons": 0.0}, "ltla_sex_age": {"cells": 0, "persons": 0.0}}

### 24. `base.build_seed`

2026-10-03T10:47:13.806Z → 2026-10-03T10:47:13.969Z · ok

Parameters: `{"max_iter": 1000, "seed_floor": 0.5, "seed_substitutes": {"E06000053": "E06000052"}, "sensitivity_floors": [0.01, 0.5, 2.0], "tolerance": 1e-06}`

- input **seed_age91**: 1,040,858 rows · hash `a573d2f85e77` · population 56,040,038 (F 28,606,005, M 27,434,033)
- input **seed_age23**: 269,192 rows · hash `66f9c454d299` · population 56,487,999 (F 28,832,825, M 27,655,174)
- output **seed**: 1,068,522 rows · hash `9a442e16db27` · population 57,058,043 (F 29,126,254, M 27,931,789)
- note: E07000026: 23-category counts split by region E12000002 single-year shape
- note: E07000029: 23-category counts split by region E12000002 single-year shape
- note: E07000030: 23-category counts split by region E12000002 single-year shape
- note: E07000046: 23-category counts split by region E12000009 single-year shape
- note: E07000047: 23-category counts split by region E12000009 single-year shape
- note: E07000166: 23-category counts split by region E12000003 single-year shape
- note: E07000167: 23-category counts split by region E12000003 single-year shape
- note: E06000053: blocked at 91a and 23a; uses seed of E06000052
- note: {"age91": 301, "age23_region_split": 7, "substitute": 1}

### 25. `rollforward.sensitivity_fit[floor=0.01]`

2026-10-03T10:47:14.994Z → 2026-10-03T10:47:15.138Z · ok

Parameters: `{"seed_floor": 0.01, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 15, "max_row_error": 4.851916628467734e-07, "max_col_error": 2.2737367544323206e-13}
- note: band 2: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 10, "max_row_error": 6.920920156971988e-07, "max_col_error": 1.4210854715202004e-14}
- note: band 3: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 9, "max_row_error": 4.5318046248965516e-07, "max_col_error": 1.4210854715202004e-14}
- note: band 4: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 6.0, "iter_max": 9, "max_row_error": 8.994451832222694e-07, "max_col_error": 1.0658141036401503e-14}
- note: band 5: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 7.0, "iter_max": 32, "max_row_error": 8.598293170791749e-07, "max_col_error": 7.105427357601002e-15}

### 26. `rollforward.apply[cohort]`

2026-10-03T10:47:15.138Z → 2026-10-03T10:47:15.197Z · ok

Parameters: `{"newborn_proxy_ages": [0], "shift_years": 3, "variant": "cohort"}`

- input **base2021**: 3,665,480 rows · hash `ebbb1dca6aa4` · population 1,717,308 (F 872,370, M 844,938)
- output **estimates**: 3,665,480 rows · hash `f3d01b9f5e0f` · population 1,790,318 (F 905,499, M 884,819)
- note: share fallback levels: {"direct": {"cells": 190906, "persons": 1786802.0}, "lsoa_sex_band": {"cells": 2014, "persons": 3516.0}, "lsoa_sex_all_ages": {"cells": 0, "persons": 0.0}, "lsoa_all": {"cells": 0, "persons": 0.0}, "ltla_sex_age": {"cells": 0, "persons": 0.0}}

### 27. `rollforward.sensitivity_fit[floor=2]`

2026-10-03T10:47:15.208Z → 2026-10-03T10:47:15.290Z · ok

Parameters: `{"seed_floor": 2.0, "tol": 1e-06}`

- note: band 1: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 13, "max_row_error": 2.304078066117654e-07, "max_col_error": 1.1368683772161603e-13}
- note: band 2: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 4.0, "iter_max": 6, "max_row_error": 1.746840858629639e-07, "max_col_error": 2.1316282072803006e-14}
- note: band 3: {"tables": 2120, "iter_p50": 4.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 6.581826994533913e-08, "max_col_error": 2.842170943040401e-14}
- note: band 4: {"tables": 2120, "iter_p50": 3.0, "iter_p95": 5.0, "iter_max": 6, "max_row_error": 2.2738234406460833e-07, "max_col_error": 1.0658141036401503e-14}
- note: band 5: {"tables": 2120, "iter_p50": 3.0, "iter_p95": 5.0, "iter_max": 8, "max_row_error": 8.871250400943609e-08, "max_col_error": 7.105427357601002e-15}

### 28. `rollforward.apply[cohort]`

2026-10-03T10:47:15.290Z → 2026-10-03T10:47:15.347Z · ok

Parameters: `{"newborn_proxy_ages": [0], "shift_years": 3, "variant": "cohort"}`

- input **base2021**: 3,665,480 rows · hash `d6ca77e89638` · population 1,717,308 (F 872,370, M 844,938)
- output **estimates**: 3,665,480 rows · hash `1eb9d20a73b5` · population 1,790,318 (F 905,499, M 884,819)
- note: share fallback levels: {"direct": {"cells": 190906, "persons": 1786802.0}, "lsoa_sex_band": {"cells": 2014, "persons": 3516.0}, "lsoa_sex_all_ages": {"cells": 0, "persons": 0.0}, "lsoa_all": {"cells": 0, "persons": 0.0}, "ltla_sex_age": {"cells": 0, "persons": 0.0}}

### 29. `rollforward.write`

2026-10-03T10:47:15.366Z → 2026-10-03T10:47:21.444Z · ok

- output **estimates**: 116,724,790 rows · hash `9fa09f4a4fcb` · population 58,620,101 (F 29,895,762, M 28,724,339)

### 30. `deprivation.load_iod`

2026-10-03T10:47:22.075Z → 2026-10-03T10:47:22.166Z · ok

Parameters: `{"core20_max_decile": 2, "edition": "IoD 2025", "file": "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv", "local_quintile": {"enabled": true, "within": "icb"}, "source": "S8"}`

- input **S8/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv**: 33,755 rows · hash `b1b716aa2e47`
- output **iod**: 33,755 rows · hash `30658f2d81d8`

### 31. `deprivation.derive`

2026-10-03T10:47:22.174Z → 2026-10-03T10:47:22.207Z · ok

Parameters: `{"core20_max_decile": 2, "edition": "IoD 2025", "file": "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv", "local_quintile": {"enabled": true, "within": "icb"}, "source": "S8"}`

- input **iod**: 33,755 rows · hash `30658f2d81d8`
- output **iod**: 33,755 rows · hash `11262b9526eb`

### 32. `catchments.load_ohid`

2026-10-03T10:47:22.794Z → 2026-10-03T10:47:34.612Z · ok

Parameters: `{"admission_type": "All admissions", "catchment_year": 2024, "file": "nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods", "host_icb": {"file": "ods_nhs_trusts.jsonl.gz", "relationship": "RE5", "source": "S10", "target_role": "RO261"}, "source": "S9"}`

- input **S9/nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods**: 151,885 rows · hash `7f7639b2cc05`
- note: All_admissions: 60462 rows for 2024 / All admissions
- note: Trust_analysis: 4996 rows for 2024 / All admissions
- note: Ethnicity: 252 rows for 2024 / All admissions
- note: Deprivation: 134 rows for 2024 / All admissions

### 33. `catchments.build_bridge`

2026-10-03T10:47:34.631Z → 2026-10-03T10:47:34.808Z · ok

- input **ohid_t2**: 60,462 rows · hash `0cdcbde0c70e`
- output **bridge_lsoa_trust**: 337,059 rows · hash `eb4e029c7c68`

### 34. `catchments.host_icb`

2026-10-03T10:47:34.816Z → 2026-10-03T10:47:34.822Z · ok

- input **S10/ods_nhs_trusts.jsonl.gz**: 1,901 rows · hash `5a94de63a168`
- output **host_icb**: 134 rows · hash `30c3127cb4a0`

### 35. `outputs.validate`

2026-10-03T10:47:35.734Z → 2026-10-03T10:47:36.317Z · ok

- input **estimates**: 116,724,790 rows · hash `9fa09f4a4fcb` · population 58,620,101 (F 29,895,762, M 28,724,339)
- note: fact rows 116,724,790; dim_lsoa 33755; bridge 337059

### 36. `outputs.write`

2026-10-03T10:47:36.317Z → 2026-10-03T10:48:00.078Z · ok

- output **fact_population**: 116,724,790 rows · hash `9fa09f4a4fcb` · population 58,620,101 (F 29,895,762, M 28,724,339)
- output **dim_lsoa**: 33,755 rows · hash `13078d5b1577`
- output **dim_region**: 9 rows · hash `7673c8e76680`
- output **dim_ltla**: 309 rows · hash `4c8941ac99f9`
- output **dim_msoa**: 6,856 rows · hash `49e219786a03`
- output **dim_lad**: 296 rows · hash `24ccbcce3b3a`
- output **dim_nhs_region**: 7 rows · hash `0ed4485c46bd`
- output **dim_icb**: 36 rows · hash `77febe5fa6dd`
- output **dim_sub_icb**: 106 rows · hash `7e60e4ef8929`
- output **dim_ethnicity**: 19 rows · hash `ea6de4ae4013`
- output **dim_age**: 91 rows · hash `3e20cb14f4b9`
- output **dim_trust**: 135 rows · hash `400a0a727303`
- output **bridge_lsoa_trust**: 337,059 rows · hash `eb4e029c7c68`

