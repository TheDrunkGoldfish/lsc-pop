# 0001. LSOA 2021 as base geography
Status: accepted
Date: 2026-10-01

## Context
The output needs small-area detail that aggregates cleanly to ICB, sub-ICB, LA and trust catchments. The inputs
(Census 2021 RM032/RM200/TS021, ONS mid-2024 LSOA estimates, IoD 2025) are all published on 2021 LSOAs.

## Options considered
- **LSOA 2021**: every core input is native, so no boundary conversion. ~33,755 areas in England.
- **LSOA 2011**: older outputs use it. It would need a best-fit or apportioned 2021→2011 conversion, adding error.
- **MSOA 2021**: more robust cell sizes, but too coarse for neighbourhood and catchment work, and finer inputs would be wasted.

## Decision
Use 2021 LSOAs as the base unit everywhere. Higher geographies are built by aggregation.

## Consequences
No boundary conversion error. LSOA21 codes are the join key throughout (`lsoa21cd`). If a future input arrives on
a different vintage, it must be converted with a documented lookup and a new ADR.

## Related
Stage A (`geography.py`), all joins. Test: every footprint LSOA has lookup + IoD records (Phase 3/7).
