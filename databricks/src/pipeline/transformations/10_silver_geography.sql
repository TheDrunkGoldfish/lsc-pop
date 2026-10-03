-- Stage A: geography (local equivalent: lsc_pop.geography). Lookups arrive in bronze with their
-- configured columns already renamed to standard names (ADR-0014).
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_silver};

CREATE OR REFRESH MATERIALIZED VIEW lsoa_geography (
  CONSTRAINT lsoa_in_both_lookups EXPECT (lsoa21_code IS NOT NULL AND lad_code IS NOT NULL AND msoa21_code IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT complete_geography EXPECT (ltla21_code IS NOT NULL AND rgn21_code IS NOT NULL AND sicbl_code IS NOT NULL AND icb_code IS NOT NULL AND nhser_code IS NOT NULL) ON VIOLATION FAIL UPDATE
)
COMMENT 'England LSOA 2021 lookup: current NHS/admin geography, Census-era MSOA/LTLA 2021 and region, footprint and focus flags (Stage A; ADR-0012, ADR-0014). Modelled-estimates pipeline.'
AS
WITH nhs AS (
  SELECT DISTINCT lsoa21_code, lsoa21_name, sicbl_code, sicbl_ods_code, sicbl_name, icb_code, icb_ods_code, icb_name,
         nhser_code, nhser_ods_code, nhser_name, lad_code, lad_name
  FROM ${lsc_pop.schema_bronze}.lookup_nhs_raw WHERE lsoa21_code LIKE 'E%'
),
census AS (
  SELECT DISTINCT lsoa21_code, msoa21_code, msoa21_name, ltla21_code, ltla21_name
  FROM ${lsc_pop.schema_bronze}.lookup_census_raw WHERE lsoa21_code LIKE 'E%'
),
rgn AS (SELECT DISTINCT ltla21_code, rgn21_code, rgn21_name FROM ${lsc_pop.schema_bronze}.lookup_ltla_region_raw)
SELECT
  COALESCE(n.lsoa21_code, c.lsoa21_code) AS lsoa21_code, n.lsoa21_name, c.msoa21_code, c.msoa21_name, c.ltla21_code, c.ltla21_name,
  r.rgn21_code, r.rgn21_name, n.lad_code, n.lad_name, n.sicbl_code, n.sicbl_ods_code, n.sicbl_name, n.icb_code, n.icb_ods_code, n.icb_name,
  n.nhser_code, n.nhser_ods_code, n.nhser_name, p.nhs_geog_vintage,
  CASE WHEN p.footprint_mode = 'england' THEN TRUE ELSE array_contains(p.footprint_icb_codes, n.icb_code) END AS in_footprint,
  COALESCE(array_contains(p.focus_icb_codes, n.icb_code), FALSE) AS in_focus_icb
FROM nhs n
FULL OUTER JOIN census c ON n.lsoa21_code = c.lsoa21_code
LEFT JOIN rgn r ON c.ltla21_code = r.ltla21_code
CROSS JOIN params p;
