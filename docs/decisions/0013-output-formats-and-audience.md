# 0013. Output formats and audience: internal analysts; Parquet canonical + CSV
Status: accepted
Date: 2026-10-01

## Context
The user confirmed (2026-10-01): outputs are for **internal analysts only**; no local comparator data is planned;
formats are **Parquet + CSV**.

## Decision
- Parquet is canonical. Every output also gets a CSV. The full England LSOA cube
  (~117M rows at SYOA × 19 groups) is written as **CSV split by ICB** (one file per ICB26) to keep each file usable.
  Aggregate tables are single CSVs.
- No suppressed output tables. `docs/limitations.md` gives disclosure and suppression guidance for anyone who
  later publishes derived tables.
- `validate.py` keeps its comparator registry, used only for public comparators (TS021, S3 at LA, OHID T1/T5/T6).

## Consequences
CSVs are large (several GB in total). If the audience widens, a new ADR will add disclosure control.

## Related
ADR-0005, `provenance.write_output`, Stage outputs (Phase 8).
