# 0012. Geography vintage: April 2026 LSOA21 → SICBL → ICB → NHSER → LAD lookup
Status: accepted (column-naming bullet superseded by ADR-0014)
Date: 2026-10-01

## Context
The brief asks for the latest vintage of the LSOA21 → Sub-ICB → ICB → LAD lookup. The April 2026 lookup reflects the
2026 ICB mergers (42 → 36 ICBs; 10,207 LSOAs changed ICB). NHS Lancashire and South Cumbria ICB (E54000048 / QE1) is
unchanged. Other sources carry older LAD codes: S5 uses LAD 2023 and IoD 2025 uses LAD 2024. These differ from LAD 2026
only in Barnsley and Sheffield (code changes, same boundaries; 491 LSOAs).

## Decision
- Use the **April 2026** lookup (S7) for SICBL, ICB, NHS region and LAD, joined on `lsoa21cd`. LAD codes carried
  by S5 and S8 are ignored for aggregation (kept only for cross-checks).
- S7b (OA21 → LSOA21 → MSOA21 → LAD Dec 2021) supplies `msoa21cd` (for OHID catchments, which are on MSOA 2021)
  and `ltla21cd` (for the S3 seed, ADR-0011). It isn't used for aggregation.
- ~~Column names in outputs keep the vintage: `sicbl26cd`, `icb26cd`, `lad26cd`, and so on.~~ Superseded by ADR-0014:
  vintage-free names (`icb_cd`, …) plus a `nhs_geog_vintage` column.
- ONS region of each LTLA 2021 comes from S7c (LAD Dec 2022 → region; identical to the 2021 LTLAs) for the seed
  fallback (ADR-0011).
- When the next lookup vintage is published, adopting it is a new ADR.

## Consequences
ICB aggregates reflect current (2026) NHS structures, which differ from 2025 ICBs in merged areas. L&SC is unaffected.

## Related
S7, Stage A (`geography.py`), Phase 3 tests.
