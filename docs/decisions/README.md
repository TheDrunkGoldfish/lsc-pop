# Decision log (ADRs)

> **Abbreviations on this page:** ADR = architecture decision record; ICB = Integrated Care Board; IMD = Index of Multiple Deprivation; IPF = iterative proportional fitting; L&SC = Lancashire and South Cumbria; LSOA = Lower layer Super Output Area; LTLA = lower-tier local authority; MSOA = Middle layer Super Output Area; ONS = Office for National Statistics; SYOA = single year of age. Full definitions: [glossary](../glossary.md).

Every choice that affects the numbers is recorded here **before or alongside** the code that implements it.
Copy `template.md` to the next number. Never edit an accepted ADR's decision: supersede it with a new one.

| # | Title | Status |
|---|---|---|
| [0001](0001-lsoa-2021-base-geography.md) | LSOA 2021 as base geography | accepted |
| [0002](0002-footprint-england-with-lsc-focus.md) | Footprint: all of England, configurable, L&SC focus | accepted |
| [0003](0003-ipf-within-lsoa-sex-band.md) | IPF within LSOA × sex × broad age band, in-house numpy | accepted |
| [0004](0004-cohort-ageing-roll-forward.md) | Cohort-ageing roll-forward (3-year shift) as default; static as sensitivity | accepted |
| [0005](0005-unrounded-floats-canonical.md) | Unrounded floats are canonical; no integerisation for now | accepted |
| [0006](0006-mid-2024-only.md) | Reference date mid-2024 only; mid-2025 deferred | accepted |
| [0007](0007-output-age-and-ethnicity-levels.md) | Output levels: SYOA, 5- and 10-year bands; ethnicity 19 and 6 | accepted |
| [0008](0008-local-imd-quintile-within-icb.md) | Local IMD quintile, population-weighted, within ICB | accepted |
| [0009](0009-reproducibility-without-git.md) | Reproducibility without git | accepted |
| [0010](0010-census-acquisition-nomis-and-ons-api.md) | Census LSOA tables via Nomis API; seed via ONS API | accepted |
| [0011](0011-s3-seed-ltla-single-year.md) | IPF seed: LTLA × single year, fallbacks for blocked LTLAs | accepted |
| [0012](0012-geography-vintage-april-2026.md) | Geography vintage: April 2026 lookup | accepted (naming superseded by 0014) |
| [0013](0013-output-formats-and-audience.md) | Output formats and audience | accepted |
| [0014](0014-config-driven-lookups-generic-columns.md) | Config-driven lookups, vintage-free column names | accepted |
| [0015](0015-margin-reconciliation-rm200-totals.md) | Margin reconciliation: RM200 defines band totals | accepted |
| [0016](0016-ipf-seed-floor.md) | IPF seed floor 0.5 | accepted |
| [0017](0017-rollforward-shares-fallbacks.md) | Roll-forward: pooled source ages, share fallbacks, newborn proxy | accepted |
| [0018](0018-star-schema-outputs-no-aggregates.md) | Star-schema outputs for SQL/Databricks; no aggregate tables | accepted |
| [0019](0019-trust-catchment-apportionment.md) | Trust catchments: MSOA→LSOA; published + unassigned, rescaled column | accepted |
| [0020](0020-drop-variant-column.md) | Drop the constant variant column from fact_population | accepted |
| [0021](0021-adopt-git-public-repository.md) | Adopt git; public GitHub repo; MIT code + OGL docs | accepted |
| [0022](0022-databricks-native-implementation.md) | Databricks-native implementation alongside the local pipeline | accepted |
| [0023](0023-config-hash-excludes-paths.md) | Config hash excludes `paths` | accepted |
| [0024](0024-databricks-parity-tolerances.md) | Parity tolerances (Databricks vs local) | accepted |
| [0025](0025-snowflake-geography-host-icb-naming.md) | Snowflaked geography dimensions, trust host ICB, `_code`/`_name` column names | accepted |
