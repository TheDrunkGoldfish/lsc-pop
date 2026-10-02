# 0002. Footprint: all of England, configurable, with L&SC as the focus
Status: accepted (supersedes the brief's ICB-only footprint, §2)
Date: 2026-10-01

## Context
The brief (§2) scoped the pipeline to LSOAs in NHS Lancashire and South Cumbria ICB, possibly extended for trust
catchments that cross the ICB boundary (§2 "Provider catchments", §6.2). At Phase 1 review the user asked for the
dataset **not** to be restricted to the OneLSC/acute footprint and to cover the **whole of England**, keeping OneLSC
and the acute trusts as the priority.

## Options considered
- **ICB footprint, optionally extended by trust catchments** (brief): smallest compute, but trust totals need a
  fiddly catchment-driven extension, and the outputs can't serve neighbouring ICBs or national benchmarking.
- **All of England, every aggregate**: one consistent national dataset. Cross-boundary catchments are complete by
  construction, and L&SC can be benchmarked against England. Costs more compute and data (~33.7k LSOAs × 2 sexes ×
  91 ages × 19 groups ≈ 117M cells as float64, ~0.9 GB in memory before compression). That's manageable with vectorised
  numpy, processed per region or in chunks if needed.
- **All of England LSOAs, L&SC aggregates only**: saves little, since aggregation is cheap.

## Decision
- Default `footprint.mode: england`: model every 2021 LSOA in England and aggregate to every ICB, sub-ICB, LA and
  OHID acute trust.
- `footprint.mode: icbs` with `icb_codes` remains available to restrict a run (e.g. for development or tests).
- `footprint.focus_icb_codes` (L&SC) and `focus_trusts` (the OneLSC acute trusts: Blackpool, East Lancashire,
  Lancashire Teaching, UHMB) mark the priority areas. They drive the worked example, the focused validation
  comparisons (e.g. against OHID trust figures) and the emphasis in the docs. They don't change any numbers.
- The brief's `in_icb` flag becomes `in_focus_icb`.

## Consequences
- Trust catchments are complete, with no footprint extension needed. `extra_lsoas_from_trust_catchments` only
  matters in `icbs` mode.
- Validation runs nationally, with focused reporting for L&SC.
- Memory and runtime have to be planned for (chunked IPF in Phase 5).
- The ONS code for the L&SC ICB (`E54000048`) and the trust ODS codes in config are **to be verified** in Phase 2/3.

## Related
`config.footprint.*`, `config.focus_trusts`. Stage A (`geography.py`), Stage G (`aggregate.py`). Phase 3 tests.
