-- Outputs: the star/snowflake schema (ADR-0018, ADR-0025; local: lsc_pop.outputs). fact_population is built in 40_gold_rollforward.sql.
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_gold};

CREATE OR REFRESH MATERIALIZED VIEW dim_ethnicity
COMMENT 'Ethnic group dimension: Census 2021 19 groups -> 6 (White split WB/WO) -> 5 high-level groups (ADR-0007).'
AS SELECT eth19, label_19, code_5, label_5, code_6, label_6, sort_order FROM ${lsc_pop.schema_silver}.map_ethnicity;

CREATE OR REFRESH MATERIALIZED VIEW dim_age
COMMENT 'Age dimension: single year 0-90 (90 = 90+) -> 5-year and 10-year bands and the Census RM032 band.'
AS SELECT age, age_label, age_5yr, age_5yr_sort, age_10yr, age_10yr_sort, census_band_rm032 FROM ${lsc_pop.schema_silver}.map_age;

-- Geography levels snowflaked off dim_lsoa (ADR-0025): names and flags live once per level.
CREATE OR REFRESH MATERIALIZED VIEW dim_region
COMMENT 'Region dimension (ONS region 2021).'
AS SELECT DISTINCT rgn21_code, rgn21_name FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_ltla
COMMENT 'Lower-tier local authority 2021 dimension (-> dim_region).'
AS SELECT DISTINCT ltla21_code, ltla21_name, rgn21_code FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_msoa
COMMENT 'MSOA 2021 dimension (-> dim_ltla).'
AS SELECT DISTINCT msoa21_code, msoa21_name, ltla21_code FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_lad
COMMENT 'Local authority district dimension (current, April 2026 lookup).'
AS SELECT DISTINCT lad_code, lad_name FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_nhs_region
COMMENT 'NHS England region dimension.'
AS SELECT DISTINCT nhser_code, nhser_ods_code, nhser_name FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_icb
COMMENT 'ICB dimension (-> dim_nhs_region), with is_footprint and is_focus (L&SC) flags.'
AS SELECT DISTINCT icb_code, icb_ods_code, icb_name, nhser_code, in_footprint AS is_footprint, in_focus_icb AS is_focus
   FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_sub_icb
COMMENT 'Sub-ICB location dimension (-> dim_icb).'
AS SELECT DISTINCT sicbl_code, sicbl_ods_code, sicbl_name, icb_code FROM ${lsc_pop.schema_silver}.lsoa_geography;

CREATE OR REFRESH MATERIALIZED VIEW dim_lsoa (
  CONSTRAINT has_iod EXPECT (imd_rank IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT quintile_valid EXPECT (imd_local_quintile BETWEEN 1 AND 5) ON VIOLATION FAIL UPDATE
)
COMMENT 'LSOA dimension: name and keys to the geography levels (dim_msoa, dim_ltla, dim_lad, dim_sub_icb, dim_icb; ADR-0025), IoD 2025, Core20, population-weighted within-ICB IMD quintile (ADR-0008), mid-year population.'
AS
WITH pop AS (SELECT lsoa21_code, SUM(population) AS population_mid_year FROM fact_population GROUP BY lsoa21_code),
b AS (
  SELECT g.lsoa21_code, g.lsoa21_name, g.msoa21_code, g.ltla21_code, g.lad_code, g.sicbl_code, g.icb_code, g.nhs_geog_vintage,
         i.* EXCEPT (lsoa21_code), pop.population_mid_year
  FROM ${lsc_pop.schema_silver}.lsoa_geography g
  JOIN ${lsc_pop.schema_silver}.iod i ON g.lsoa21_code = i.lsoa21_code
  JOIN pop ON g.lsoa21_code = pop.lsoa21_code
),
q AS (
  SELECT b.lsoa21_code, p.local_quintile_within,
         CASE WHEN p.local_quintile_within = 'icb' THEN b.icb_code ELSE b.lad_code END AS grp,
         b.imd_rank, b.population_mid_year AS pop
  FROM b CROSS JOIN ${lsc_pop.schema_silver}.params p
),
w AS (
  SELECT lsoa21_code, local_quintile_within, pop,
         SUM(pop) OVER (PARTITION BY grp ORDER BY imd_rank ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum,
         SUM(pop) OVER (PARTITION BY grp) AS tot
  FROM q
)
SELECT b.*,
       CAST(LEAST(FLOOR((w.cum - w.pop / 2) / COALESCE(NULLIF(w.tot, 0), 1) * 5) + 1, 5) AS INT) AS imd_local_quintile,
       w.local_quintile_within AS imd_local_quintile_within
FROM b JOIN w ON b.lsoa21_code = w.lsoa21_code;

CREATE OR REFRESH MATERIALIZED VIEW bridge_lsoa_trust (
  CONSTRAINT proportions_valid EXPECT (proportion_published >= 0 AND proportion_rescaled >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'LSOA x acute trust catchment proportions (ADR-0019): proportion_published (OHID, plus an UNASSIGNED row holding 1 - Sum) and proportion_rescaled (Sum = 1 over listed trusts). Each LSOA takes its MSOA 2021 shares.'
AS
WITH s AS (SELECT msoa21_code, SUM(proportion_published) AS msum FROM ${lsc_pop.schema_silver}.ohid_shares GROUP BY msoa21_code),
m AS (
  SELECT o.msoa21_code, o.trust_code, o.proportion_published, o.proportion_published / s.msum AS proportion_rescaled, o.fptp
  FROM ${lsc_pop.schema_silver}.ohid_shares o JOIN s ON o.msoa21_code = s.msoa21_code
  UNION ALL
  SELECT msoa21_code, 'UNASSIGNED' AS trust_code, GREATEST(1 - msum, 0.0) AS proportion_published,
         0.0 AS proportion_rescaled, FALSE AS fptp
  FROM s WHERE GREATEST(1 - msum, 0.0) > 0
)
SELECT g.lsoa21_code, m.msoa21_code, m.trust_code, m.proportion_published, m.proportion_rescaled, m.fptp
FROM ${lsc_pop.schema_silver}.lsoa_geography g JOIN m ON g.msoa21_code = m.msoa21_code;

CREATE OR REFRESH MATERIALIZED VIEW dim_trust
COMMENT 'Acute trust dimension (OHID T7), plus UNASSIGNED. is_focus = OneLSC acute trusts. host_icb_code = the ICB the trust is located in (ODS, S10; ADR-0025): an organisational link, separate from the catchment bridge; NULL for UNASSIGNED.'
AS
WITH t AS (
  SELECT trust_code, trust_name, trust_type, commisioning_region AS commissioning_region,
         lower_super_output_area_code_lsoa21cd AS site_lsoa21_code
  FROM ${lsc_pop.schema_bronze}.ohid_t7_raw
  UNION ALL
  SELECT 'UNASSIGNED', 'Unassigned (OHID suppressed/rounded flows; ADR-0019)', 'n/a', 'n/a', ''
),
h AS (
  SELECT DISTINCT x.trust_code, i.icb_code AS host_icb_code
  FROM ${lsc_pop.schema_silver}.trust_host_icb x
  JOIN (SELECT DISTINCT icb_ods_code, icb_code FROM ${lsc_pop.schema_silver}.lsoa_geography) i ON x.icb_ods_code = i.icb_ods_code
)
SELECT t.*, array_contains(p.focus_trusts, t.trust_code) AS is_focus, h.host_icb_code
FROM t CROSS JOIN ${lsc_pop.schema_silver}.params p LEFT JOIN h ON h.trust_code = t.trust_code;
