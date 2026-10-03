# 0025. Snowflaked geography dimensions, trust host ICB, and `_code` / `_name` column names
Status: accepted (user, 2026-10-03)
Date: 2026-10-03

## Context
Three problems with the star schema (ADR-0018), found while using it in Databricks:

1. **No trust → ICB link.** `dim_trust` and `bridge_lsoa_trust` carried no ICB. Users could split a trust's
   *catchment* by the ICB of each LSOA (bridge × `dim_lsoa.icb_code`) but couldn't ask which ICB a trust belongs to.
   Catchment and organisation are different things: a trust's catchment spans several ICBs, whereas the trust itself
   sits in one.
2. **Inconsistent column names.** `trust_name` (dim_trust) next to `icb_nm`, `lsoa21nm`, `lad_nm` (dim_lsoa), and
   `_cd` / `cd` beside `trust_code`.
3. **Repeated attributes.** `dim_lsoa` repeated the names of its MSOA, LTLA, region, LAD, sub-ICB, ICB and NHS region
   (and the footprint / focus flags) on each of 33,755 rows.

### Is there a single "reporting" ICB for a trust?
Checked against the live NHS ODS directory (2026-10-03, all 134 OHID acute trusts; source S10):

- **ODS has no "reports to" relationship for NHS trusts.** They are independent statutory bodies, not part of an ICB.
  ICBs commission from them and trusts are ICS partners.
- ODS relationship **RE5 "is located in the geography of"** gives **exactly one active ICB for 134/134 trusts**. For
  all 134 it is the same ICB as the one containing the trust's main-site LSOA (OHID T7 × our April 2026 lookup).
- ODS relationship **RE8 "is partner to"** gives one or more ICBs: 8 of the 134 have two ICBs. Three of its links
  (RDU, RPY, RVR) are stale after the April 2026 ICB mergers (RE5 is current for those).

## Options considered
- **Trust → ICB column plus `dim_icb`** (chosen). Simple, one ICB per trust, and ODS RE5 supplies it.
- A trust-ICB bridge from RE8 (partner links). Rejected for now: partly stale, and "partner" isn't a geography.
- Deriving the ICB from the site LSOA. Same answer today, but a geographic inference rather than a published
  relationship. It is kept as the corroborating check CAT-13.
- Leaving `dim_lsoa` denormalised (star). Rejected: it repeats names for no gain, and the same name can differ
  between tables.

## Decision
- **`dim_trust.host_icb_code`** (FK → `dim_icb`; NULL for `UNASSIGNED`) = the ICB the trust is located in, from ODS
  RE5 (active, target role RO261) in the S10 snapshot, mapped to `icb_code` by ODS code. The column and
  documentation say "host ICB" and say it is **not** a reporting line. The relationship and role are in config
  (`catchments.host_icb`). Checks: CAT-12 (hard: exactly one active link per trust, mapping to a current ICB) and
  CAT-13 (informational: agrees with the ICB of the trust's main-site LSOA).
- **Two ways to split trusts by ICB**, both documented in `schema.sql`: by catchment (bridge × `dim_lsoa.icb_code`)
  or by hierarchy (`dim_trust.host_icb_code`). They answer different questions and aren't merged.
- **New source S10** (`ods_api_orgs`): one full ODS record per active NHS trust (primary role RO197), stored verbatim
  in a gzip JSON-lines file with the SHA-256 in the manifest. The directory is live and unversioned, so a
  re-download can differ; the existing "publisher changed the data" rule applies.
- **Snowflaked geography** (outputs only; the interim lookup stays denormalised):
  `dim_msoa → dim_ltla → dim_region`, `dim_lad`, `dim_sub_icb → dim_icb → dim_nhs_region`. `dim_icb` carries
  `is_footprint` and `is_focus` (renamed from `in_footprint` / `in_focus_icb`, matching `dim_trust.is_focus`).
  `dim_lsoa` keeps `lsoa21_name`, `nhs_geog_vintage`, IoD and population plus the keys `msoa21_code`, `ltla21_code`,
  `lad_code`, `sicbl_code` and `icb_code`. The shortcut keys (`ltla21_code`, `icb_code`) deliberately duplicate what
  the hierarchy implies, because the ICB is the main reporting split and the IMD quintile grouping and a two-hop
  join for the commonest query isn't worth it. OUT-07 (hard) checks they agree with the hierarchy.
- **Column names:** `_cd` / `cd` → `_code`, `_nm` / `nm` → `_name`, `_ods` → `_ods_code`, everywhere in both
  implementations, config and docs (e.g. `lsoa21cd` → `lsoa21_code`, `icb_nm` → `icb_name`,
  `sicbl_ods` → `sicbl_ods_code`). Raw upstream headers (`LSOA21CD`, the OHID sheet headers) are unchanged; they are
  mapped to the new names on ingest (config `geography.*.columns`).

## Consequences
- **Breaking change to published columns and tables** (names, and `dim_lsoa` loses the descriptive geography
  columns and the two flags). The numbers don't change: `fact_population` is identical apart from the key column
  name. Queries that read `dim_lsoa.icb_name` or `in_focus_icb` now join `dim_icb`.
- ADRs and changelog entries written before this keep the old names; they are a historical record.
- Seven geography dimension tables are added to the outputs; `OUT-01` covers all of their keys.
- If ODS adds a real governance relationship between trusts and ICBs, switch `catchments.host_icb.relationship`
  and revisit the name. If a many-to-many link is needed, add a bridge from RE8 (and refresh the stale links).

## Related
`src/lsc_pop/outputs.py`, `catchments.py`, `ods_directory.py`, `download.py` (`ods_api_orgs`); config
`catchments.host_icb`, source S10; `databricks/.../60_gold_star.sql`, `45_silver_iod_catchments.sql`,
`80_checks.sql`; checks CAT-12, CAT-13, OUT-01, OUT-07; tests `test_outputs.py`, `test_phase7.py`,
`test_ods_directory.py`, `test_download.py`.
