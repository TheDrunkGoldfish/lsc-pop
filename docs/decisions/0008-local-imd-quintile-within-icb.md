# 0008. Local IMD quintile: population-weighted, ranked within each ICB
Status: accepted
Date: 2026-10-01

## Context
The brief asks for an optional footprint-local deprivation quintile. With an England-wide footprint (ADR-0002), "local"
needs defining. The user chose **within each ICB** (Phase 1 review).

## Options considered
- **Within ICB**: matches NHS planning use (local Core20-style analysis by ICB).
- **Within LA**: matches local-authority use, but gives small, unstable groups in small LAs.
- **National only**: loses the local view.

## Decision
For each ICB, rank its LSOAs by IMD 2025 score (most deprived first) and cut into quintiles holding ~20% of the ICB's
**mid-2024 total population** each (population-weighted, not LSOA count). National rank, decile and quintile and `core20`
(national IMD deciles 1–2) are carried alongside. `config.deprivation.local_quintile.within` also permits `lad`. Exact tie-
breaking and boundary handling (an LSOA straddling a 20% cut goes to the quintile holding its cumulative midpoint) will be
confirmed in Phase 7.

## Implementation (Phase 7)
Ordering is by national IMD rank, which is unique, so there are no ties. Each LSOA goes to the quintile containing
the midpoint of its own population on the ICB's cumulative population scale. Result: every ICB's quintiles hold
20% ± 0.3 pp of its mid-2024 population (DEP-03).

## Consequences
Local quintiles aren't comparable across ICBs; national ones are. Docs must say which is which.

## Related
Stage F, `config.deprivation.local_quintile`, assumption A07.
