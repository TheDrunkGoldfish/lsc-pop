-- Stage D: roll the 2021 base forward to the mid-year (ADR-0004, ADR-0017; local: lsc_pop.rollforward).
-- Shares are pooled 2021 counts at each target age's source ages (silver.source_age_map). Where an
-- LSOA x sex had nobody at those ages, shares fall back to: (1) the RM032 band of the source ages,
-- (2) all ages, (3) the LSOA (both sexes), (4) the LTLA at the source ages.
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_gold};

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW rf_level0
AS SELECT m.variant, b.lsoa21cd, b.ltla21cd, b.sex, m.target_age AS age, m.src_band, b.eth19,
          SUM(b.population) AS c0
   FROM ${lsc_pop.schema_silver}.base_2021 b
   JOIN ${lsc_pop.schema_silver}.source_age_map m ON b.age = m.source_age
   GROUP BY m.variant, b.lsoa21cd, b.ltla21cd, b.sex, m.target_age, m.src_band, b.eth19;

CREATE OR REFRESH PRIVATE MATERIALIZED VIEW rf_shares (
  CONSTRAINT share_defined EXPECT (share IS NOT NULL AND share >= 0 AND share <= 1 + 1e-12) ON VIOLATION FAIL UPDATE
)
AS
WITH l1 AS (
  SELECT b.lsoa21cd, b.sex, a.rm032_band AS band, b.eth19, SUM(b.population) AS c1
  FROM ${lsc_pop.schema_silver}.base_2021 b JOIN ${lsc_pop.schema_silver}.map_age a ON b.age = a.age
  GROUP BY b.lsoa21cd, b.sex, a.rm032_band, b.eth19
),
l2 AS (SELECT lsoa21cd, sex, eth19, SUM(population) AS c2 FROM ${lsc_pop.schema_silver}.base_2021 GROUP BY lsoa21cd, sex, eth19),
l3 AS (SELECT lsoa21cd, eth19, SUM(population) AS c3 FROM ${lsc_pop.schema_silver}.base_2021 GROUP BY lsoa21cd, eth19),
l4 AS (SELECT variant, ltla21cd, sex, age, eth19, SUM(c0) AS c4 FROM rf_level0 GROUP BY variant, ltla21cd, sex, age, eth19),
c AS (
  SELECT r.variant, r.lsoa21cd, r.sex, r.age, r.eth19, r.c0, l1.c1, l2.c2, l3.c3, l4.c4
  FROM rf_level0 r
  JOIN l1 ON r.lsoa21cd = l1.lsoa21cd AND r.sex = l1.sex AND r.src_band = l1.band AND r.eth19 = l1.eth19
  JOIN l2 ON r.lsoa21cd = l2.lsoa21cd AND r.sex = l2.sex AND r.eth19 = l2.eth19
  JOIN l3 ON r.lsoa21cd = l3.lsoa21cd AND r.eth19 = l3.eth19
  JOIN l4 ON r.variant = l4.variant AND r.ltla21cd = l4.ltla21cd AND r.sex = l4.sex AND r.age = l4.age AND r.eth19 = l4.eth19
),
t AS (
  SELECT *, SUM(c0) OVER w AS t0, SUM(c1) OVER w AS t1, SUM(c2) OVER w AS t2, SUM(c3) OVER w AS t3, SUM(c4) OVER w AS t4
  FROM c WINDOW w AS (PARTITION BY variant, lsoa21cd, sex, age)
)
SELECT variant, lsoa21cd, sex, age, eth19,
       CASE WHEN t0 > 0 THEN 0 WHEN t1 > 0 THEN 1 WHEN t2 > 0 THEN 2 WHEN t3 > 0 THEN 3 ELSE 4 END AS fallback_level,
       CASE WHEN t0 > 0 THEN c0 / t0 WHEN t1 > 0 THEN c1 / t1 WHEN t2 > 0 THEN c2 / t2
            WHEN t3 > 0 THEN c3 / t3 ELSE c4 / NULLIF(t4, 0) END AS share
FROM t;

CREATE OR REFRESH MATERIALIZED VIEW fact_population (
  CONSTRAINT population_valid EXPECT (population IS NOT NULL AND population >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'MODELLED ESTIMATES - NOT OFFICIAL STATISTICS. Population by LSOA 2021 x sex x single year of age (90 = 90+) x 19 ethnic groups at the reference mid-year; sums exactly to the ONS mid-year estimates per LSOA x sex x age. See the lsc-pop docs (limitations, data dictionary).'
AS SELECT s.lsoa21cd, s.sex, s.age, s.eth19, m.population * s.share AS population, p.reference_year
   FROM rf_shares s
   JOIN ${lsc_pop.schema_silver}.mye m ON s.lsoa21cd = m.lsoa21cd AND s.sex = m.sex AND s.age = m.age
   CROSS JOIN ${lsc_pop.schema_silver}.params p
   WHERE s.variant = p.variant;

CREATE OR REFRESH MATERIALIZED VIEW ${lsc_pop.schema_audit}.share_fallback
COMMENT 'How many LSOA x sex x age cells (and people) used each share fallback level (ADR-0017), default variant.'
AS SELECT s.fallback_level, COUNT(*) / 19 AS cells, SUM(m.population) / 19 AS persons
   FROM rf_shares s
   JOIN ${lsc_pop.schema_silver}.mye m ON s.lsoa21cd = m.lsoa21cd AND s.sex = m.sex AND s.age = m.age
   CROSS JOIN ${lsc_pop.schema_silver}.params p
   WHERE s.variant = p.variant
   GROUP BY s.fallback_level;

CREATE OR REFRESH MATERIALIZED VIEW ${lsc_pop.schema_audit}.sensitivity
COMMENT 'Roll-forward sensitivity: England and focus ICB totals by variant x sex x 10-year band x ethnic group (cohort default vs static vs newborn proxy 0-4).'
AS
WITH e AS (
  SELECT s.variant, s.lsoa21cd, s.sex, s.age, s.eth19, m.population * s.share AS population
  FROM rf_shares s
  JOIN ${lsc_pop.schema_silver}.mye m ON s.lsoa21cd = m.lsoa21cd AND s.sex = m.sex AND s.age = m.age
),
g AS (
  SELECT 'England' AS geography, e.* FROM e
  UNION ALL
  SELECT 'Focus ICB' AS geography, e.* FROM e JOIN ${lsc_pop.schema_silver}.lsoa_geography g ON e.lsoa21cd = g.lsoa21cd WHERE g.in_focus_icb
)
SELECT g.geography, g.variant, g.sex, a.age_10yr AS age_band, g.eth19, x.code_6 AS eth6, SUM(g.population) AS population
FROM g
JOIN ${lsc_pop.schema_silver}.map_age a ON g.age = a.age
JOIN ${lsc_pop.schema_silver}.map_ethnicity x ON g.eth19 = x.eth19
GROUP BY g.geography, g.variant, g.sex, a.age_10yr, g.eth19, x.code_6;
