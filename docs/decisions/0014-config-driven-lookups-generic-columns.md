# 0014. Config-driven geography lookups with vintage-free column names
Status: accepted (supersedes ADR-0012's column-naming bullet)
Date: 2026-10-01

## Context
ADR-0012 proposed vintage-suffixed output columns (`icb26cd`, `lad26cd`). NHS geography is reissued roughly every April
(April 2026 merged 42 ICBs into 36). With suffixed names, every new vintage would rename columns throughout the code and
outputs, which breaks downstream code and users' scripts. The user asked for clear instructions on updating
lookups when ICBs merge or boundaries change.

## Options considered
- **Vintage-suffixed columns** (ADR-0012): self-describing, but each update means code changes everywhere.
- **Vintage-free columns plus an explicit vintage field**: stable schema. The vintage lives in the
  `nhs_geog_vintage` column and in every output's metadata sidecar.

## Decision
- Each lookup is described in `config/config.yaml → geography.{nhs, census, ltla_region}` by its source ID, file,
  vintage and a **raw → standard column map**. Only mapped columns are kept.
- Standard names for the current NHS/admin geography have no vintage: `sicbl_cd`, `sicbl_ods`, `sicbl_nm`, `icb_cd`,
  `icb_ods`, `icb_nm`, `nhser_cd`, `nhser_ods`, `nhser_nm`, `lad_cd`, `lad_nm`. The required set is enforced by the
  config schema.
- Census-era geography **keeps its year** (`lsoa21cd`, `msoa21cd`, `ltla21cd`, `rgn21cd`) because it is fixed to
  the Census 2021 base and must not be swapped for a later vintage.
- Updating to a new NHS lookup is config-only (runbook: `docs/updating.md` §B). A unit test proves this by renaming
  every `…26…` column to `…27…` and changing only the config.

## Consequences
Users must read `nhs_geog_vintage` (or the metadata) to know which ICB boundaries a figure uses. A wrong column
map fails loudly: missing raw columns give an actionable error, and missing standard names fail config validation.

## Related
ADR-0012, `lsc_pop.config.Geography`, `lsc_pop.geography`, `tests/test_geography.py::test_new_lookup_vintage_is_config_only`,
`docs/updating.md`.
