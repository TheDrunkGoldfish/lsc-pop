# 0010. Census LSOA tables from the Nomis API; seed from the ONS custom-dataset API
Status: accepted
Date: 2026-10-01

## Context
The brief assumed bulk CSVs for RM032 and RM200 at LSOA. Phase 2 found:
- **No LSOA bulk files exist for RM032 or RM200.** The Nomis bulk zips for RM tables are empty (0 bytes), and the ONS
  dataset downloads are LTLA only. TS009 has no LSOA level at all.
- Two APIs serve LSOA data with **identical values** (spot-checked cell-by-cell on E01011954):
  - **Nomis API** (`NM_2132_1` RM032, `NM_2300_1` RM200): CSV, at most 25,000 rows per call without a key, paged with
    `recordoffset`. RM032 needs about 270 calls and RM200 about 249.
  - **ONS custom-dataset API** (`api.beta.ons.gov.uk/v1/population-types/UR/census-observations`): JSON, at most 100,000
    rows per call, batched by area-code lists. RM200 comes to roughly 2 GB of raw JSON.
- TS021 does have a Nomis LSOA bulk zip.
- The S3 seed (ethnicity × sex × single year at LTLA) is available **only** through the ONS API.

## Options considered
- **Nomis for RM032/RM200, Nomis bulk zip for TS021, ONS API for S3**: stable dataset IDs and compact CSV. Two mechanisms.
- **ONS API for everything**: one mechanism, but large raw JSON, and the area batching has to be reproduced exactly.

## Decision
The user chose Nomis (2026-10-01). `download.py` implements three fetch kinds:
- `nomis_paged`: pages are joined into **one raw CSV per table**, with the header written once and rows otherwise
  byte-identical. The joined row count must equal Nomis's `RECORD_COUNT` (requested via `select=…,record_count`) and the
  registry's `expected_rows`.
- `ons_api_batched`: the area list comes from the API, filtered to England (`E`), and is fetched in batches under the
  row cap. Responses are stored **verbatim** as gzip JSON lines (`mtime=0`, empty filename, so the output is
  deterministic), each line annotated with the requested and blocked area codes.
- `http`: plain files.

RM032 is fetched **including the all-groups total** (`c2021_eth_20=0`). Nomis omits "Does not apply", so brief §10's
check becomes "total = Σ codes 1–19" per LSOA × sex × band, which is equivalent. RM200 includes the all-ages total
(`c2021_age_92=0`) for the same kind of internal consistency check.

## Consequences
Joining pages is the only processing done before data lands in `data/raw/`. It's lossless and documented. A rerun
after deliberate deletion must produce the same SHA-256, or the pipeline stops (the publisher changed the data).
If Nomis or the ONS API changes paging or limits, the fetchers fail loudly instead of returning partial data.

## Related
`config/sources.yaml` (S1–S4), `lsc_pop.download`, `tests/test_download.py`.
