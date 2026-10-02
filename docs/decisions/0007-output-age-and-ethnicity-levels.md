# 0007. Output levels: single year, 5- and 10-year bands; ethnicity 19 and 6 groups
Status: accepted (6-group definition confirmed by user 2026-10-01)
Date: 2026-10-01

## Context
The user asked for outputs at single year of age plus **5-year** and **10-year** bands, and ethnicity at **19** and **6**
groups (Phase 1 review).

## Decision
- Age: single year 0–90+ internally and in outputs. Band sets `5yr` (0–4 … 85–89, 90+) and `10yr` (0–9 … 80–89,
  90+) are defined in `config/mappings/age_bands.csv`. Bands are validated on load to tile 0–90 exactly.
- Ethnicity: 19 Census tick-box groups (RM032 categories minus "Does not apply"), plus a 6-group aggregation from
  `config/mappings/ethnicity_19_to_6.csv`. The mapping also carries the Census 5 high-level groups (`code_5`).
- **6-group definition (confirmed by user):** Census 2021's high-level classification has five groups (Asian, Black, Mixed,
  White, Other). "6 groups" is taken to mean those five with **White split into White British and Other White**
  (Irish, Gypsy or Irish Traveller, Roma, Other White), as is common in NHS reporting. Alternative: the five groups
  plus a separate "Not stated/Unknown", but Census 2021 has no unknown category for usual residents, so that would be empty.

## Consequences
Banded outputs are exact sums of single-year cells. The aggregation is presentational: it never changes 19-group numbers.

## Related
`config.age`, `config.ethnicity`, `lsc_pop.mappings`, `tests/test_config.py`, assumption A05.
