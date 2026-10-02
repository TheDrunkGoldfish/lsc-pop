-- Stage A: geography (local equivalent: lsc_pop.geography). Lookups arrive in bronze with their
-- configured columns already renamed to standard names (ADR-0014).
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_silver};

CREATE OR REFRESH MATERIALIZED VIEW lsoa_geography (
  CONSTRAINT lsoa_in_both_lookups EXPECT (lsoa21cd IS NOT NULL AND lad_cd IS NOT NULL AND msoa21cd IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT complete_geography EXPECT (ltla21cd IS NOT NULL AND rgn21cd IS NOT NULL AND sicbl_cd IS NOT NULL AND icb_cd IS NOT NULL AND nhser_cd IS NOT NULL) ON VIOLATION FAIL UPDATE
)
COMMENT 'England LSOA 2021 lookup: current NHS/admin geography, Census-era MSOA/LTLA 2021 and region, footprint and focus flags (Stage A; ADR-0012, ADR-0014). Modelled-estimates pipeline.'
AS
WITH nhs AS (
  SELECT DISTINCT lsoa21cd, lsoa21nm, sicbl_cd, sicbl_ods, sicbl_nm, icb_cd, icb_ods, icb_nm,
         nhser_cd, nhser_ods, nhser_nm, lad_cd, lad_nm
  FROM ${lsc_pop.schema_bronze}.lookup_nhs_raw WHERE lsoa21cd LIKE 'E%'
),
census AS (
  SELECT DISTINCT lsoa21cd, msoa21cd, msoa21nm, ltla21cd, ltla21nm
  FROM ${lsc_pop.schema_bronze}.lookup_census_raw WHERE lsoa21cd LIKE 'E%'
),
rgn AS (SELECT DISTINCT ltla21cd, rgn21cd, rgn21nm FROM ${lsc_pop.schema_bronze}.lookup_ltla_region_raw)
SELECT
  COALESCE(n.lsoa21cd, c.lsoa21cd) AS lsoa21cd, n.lsoa21nm, c.msoa21cd, c.msoa21nm, c.ltla21cd, c.ltla21nm,
  r.rgn21cd, r.rgn21nm, n.lad_cd, n.lad_nm, n.sicbl_cd, n.sicbl_ods, n.sicbl_nm, n.icb_cd, n.icb_ods, n.icb_nm,
  n.nhser_cd, n.nhser_ods, n.nhser_nm, p.nhs_geog_vintage,
  CASE WHEN p.footprint_mode = 'england' THEN TRUE ELSE array_contains(p.footprint_icb_codes, n.icb_cd) END AS in_footprint,
  COALESCE(array_contains(p.focus_icb_codes, n.icb_cd), FALSE) AS in_focus_icb
FROM nhs n
FULL OUTER JOIN census c ON n.lsoa21cd = c.lsoa21cd
LEFT JOIN rgn r ON c.ltla21cd = r.ltla21cd
CROSS JOIN params p;
