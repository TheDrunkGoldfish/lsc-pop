-- Outputs: the star schema (ADR-0018; local: lsc_pop.outputs). fact_population is built in 40_gold_rollforward.sql.
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_gold};

CREATE OR REFRESH MATERIALIZED VIEW dim_ethnicity
COMMENT 'Ethnic group dimension: Census 2021 19 groups -> 6 (White split WB/WO) -> 5 high-level groups (ADR-0007).'
AS SELECT eth19, label_19, code_5, label_5, code_6, label_6, sort_order FROM ${lsc_pop.schema_silver}.map_ethnicity;

CREATE OR REFRESH MATERIALIZED VIEW dim_age
COMMENT 'Age dimension: single year 0-90 (90 = 90+) -> 5-year and 10-year bands and the Census RM032 band.'
AS SELECT age, age_label, age_5yr, age_5yr_sort, age_10yr, age_10yr_sort, census_band_rm032 FROM ${lsc_pop.schema_silver}.map_age;

CREATE OR REFRESH MATERIALIZED VIEW dim_lsoa (
  CONSTRAINT has_iod EXPECT (imd_rank IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT quintile_valid EXPECT (imd_local_quintile BETWEEN 1 AND 5) ON VIOLATION FAIL UPDATE
)
COMMENT 'LSOA dimension: geography (current NHS/admin + Census 2021), IoD 2025, Core20, population-weighted within-ICB IMD quintile (ADR-0008), mid-year population.'
AS
WITH pop AS (SELECT lsoa21cd, SUM(population) AS population_mid_year FROM fact_population GROUP BY lsoa21cd),
b AS (
  SELECT g.*, i.* EXCEPT (lsoa21cd), pop.population_mid_year
  FROM ${lsc_pop.schema_silver}.lsoa_geography g
  JOIN ${lsc_pop.schema_silver}.iod i ON g.lsoa21cd = i.lsoa21cd
  JOIN pop ON g.lsoa21cd = pop.lsoa21cd
),
q AS (
  SELECT b.lsoa21cd, p.local_quintile_within,
         CASE WHEN p.local_quintile_within = 'icb' THEN b.icb_cd ELSE b.lad_cd END AS grp,
         b.imd_rank, b.population_mid_year AS pop
  FROM b CROSS JOIN ${lsc_pop.schema_silver}.params p
),
w AS (
  SELECT lsoa21cd, local_quintile_within, pop,
         SUM(pop) OVER (PARTITION BY grp ORDER BY imd_rank ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum,
         SUM(pop) OVER (PARTITION BY grp) AS tot
  FROM q
)
SELECT b.*,
       CAST(LEAST(FLOOR((w.cum - w.pop / 2) / COALESCE(NULLIF(w.tot, 0), 1) * 5) + 1, 5) AS INT) AS imd_local_quintile,
       w.local_quintile_within AS imd_local_quintile_within
FROM b JOIN w ON b.lsoa21cd = w.lsoa21cd;

CREATE OR REFRESH MATERIALIZED VIEW bridge_lsoa_trust (
  CONSTRAINT proportions_valid EXPECT (proportion_published >= 0 AND proportion_rescaled >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'LSOA x acute trust catchment proportions (ADR-0019): proportion_published (OHID, plus an UNASSIGNED row holding 1 - Sum) and proportion_rescaled (Sum = 1 over listed trusts). Each LSOA takes its MSOA 2021 shares.'
AS
WITH s AS (SELECT msoa21cd, SUM(proportion_published) AS msum FROM ${lsc_pop.schema_silver}.ohid_shares GROUP BY msoa21cd),
m AS (
  SELECT o.msoa21cd, o.trust_code, o.proportion_published, o.proportion_published / s.msum AS proportion_rescaled, o.fptp
  FROM ${lsc_pop.schema_silver}.ohid_shares o JOIN s ON o.msoa21cd = s.msoa21cd
  UNION ALL
  SELECT msoa21cd, 'UNASSIGNED' AS trust_code, GREATEST(1 - msum, 0.0) AS proportion_published,
         0.0 AS proportion_rescaled, FALSE AS fptp
  FROM s WHERE GREATEST(1 - msum, 0.0) > 0
)
SELECT g.lsoa21cd, m.msoa21cd, m.trust_code, m.proportion_published, m.proportion_rescaled, m.fptp
FROM ${lsc_pop.schema_silver}.lsoa_geography g JOIN m ON g.msoa21cd = m.msoa21cd;

CREATE OR REFRESH MATERIALIZED VIEW dim_trust
COMMENT 'Acute trust dimension (OHID T7), plus UNASSIGNED; is_focus = OneLSC acute trusts.'
AS
WITH t AS (
  SELECT trust_code, trust_name, trust_type, commisioning_region AS commissioning_region,
         lower_super_output_area_code_lsoa21cd AS site_lsoa21cd
  FROM ${lsc_pop.schema_bronze}.ohid_t7_raw
  UNION ALL
  SELECT 'UNASSIGNED', 'Unassigned (OHID suppressed/rounded flows; ADR-0019)', 'n/a', 'n/a', ''
)
SELECT t.*, array_contains(p.focus_trusts, t.trust_code) AS is_focus
FROM t CROSS JOIN ${lsc_pop.schema_silver}.params p;
