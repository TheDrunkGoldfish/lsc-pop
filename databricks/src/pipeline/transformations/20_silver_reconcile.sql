-- Stage B (part 2): margin reconciliation (ADR-0015; local: lsc_pop.census.reconcile_margins).
-- Both margins of each LSOA x sex x band are scaled to a common total chosen by
-- params.margin_source, with the documented fallbacks for zero-inconsistent bands.
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_silver};

CREATE OR REFRESH MATERIALIZED VIEW census_band_totals
COMMENT 'LSOA x sex x RM032 band totals from RM032 (t032) and RM200 (t200), and the reconciled target.'
AS
WITH t032 AS (
  SELECT lsoa21_code, sex, band, SUM(population) AS t032 FROM rm032 GROUP BY lsoa21_code, sex, band
),
t200 AS (
  SELECT r.lsoa21_code, r.sex, a.rm032_band AS band, SUM(r.population) AS t200
  FROM rm200 r JOIN map_age a ON r.age = a.age
  GROUP BY r.lsoa21_code, r.sex, a.rm032_band
)
SELECT t032.lsoa21_code, t032.sex, t032.band, t032.t032, t200.t200,
       CASE p.margin_source
         WHEN 'rm200' THEN CAST(t200.t200 AS DOUBLE)
         WHEN 'rm032' THEN CAST(t032.t032 AS DOUBLE)
         ELSE (t032.t032 + t200.t200) / 2.0 END AS target
FROM t032 JOIN t200 ON t032.lsoa21_code = t200.lsoa21_code AND t032.sex = t200.sex AND t032.band = t200.band
CROSS JOIN params p;

CREATE OR REFRESH MATERIALIZED VIEW census_margins (
  CONSTRAINT finite_non_negative EXPECT (population >= 0 AND NOT isnan(population)) ON VIOLATION FAIL UPDATE
)
COMMENT 'Reconciled IPF margins: kind = eth19 (RM032 scaled) or age (RM200 scaled); Sum eth19 = Sum age per LSOA x sex x band.'
AS
WITH pooled AS (   -- fallback 1 for ethnicity: LSOA x sex ethnic mix pooled over all bands
  SELECT lsoa21_code, sex, eth19,
         SUM(population) / NULLIF(SUM(SUM(population)) OVER (PARTITION BY lsoa21_code, sex), 0) AS share
  FROM rm032 GROUP BY lsoa21_code, sex, eth19
),
seedmix AS (       -- fallback 2 for ethnicity: LTLA seed ethnic mix for the sex x band
  SELECT s.ltla21_code, s.sex, a.rm032_band AS band, s.eth19,
         SUM(s.population) / NULLIF(SUM(SUM(s.population)) OVER (PARTITION BY s.ltla21_code, s.sex, a.rm032_band), 0) AS share
  FROM seed_age91 s JOIN map_age a ON s.age = a.age
  GROUP BY s.ltla21_code, s.sex, a.rm032_band, s.eth19
),
seedshape AS (     -- fallback for ages: LTLA seed all-ethnicity age shape within the band
  SELECT s.ltla21_code, s.sex, s.age,
         SUM(s.population) / NULLIF(SUM(SUM(s.population)) OVER (PARTITION BY s.ltla21_code, s.sex, a.rm032_band), 0) AS shape
  FROM seed_age91 s JOIN map_age a ON s.age = a.age
  GROUP BY s.ltla21_code, s.sex, s.age, a.rm032_band
),
eth AS (
  SELECT r.lsoa21_code, g.ltla21_code, r.sex, r.band, 'eth19' AS kind, r.eth19 AS key,
         CASE WHEN bt.t032 > 0 THEN r.population * bt.target / bt.t032
              WHEN bt.target > 0 THEN bt.target * COALESCE(pl.share, sm.share, 0.0)
              ELSE CAST(r.population AS DOUBLE) END AS population
  FROM rm032 r
  JOIN census_band_totals bt ON r.lsoa21_code = bt.lsoa21_code AND r.sex = bt.sex AND r.band = bt.band
  JOIN lsoa_geography g ON r.lsoa21_code = g.lsoa21_code
  LEFT JOIN pooled pl ON r.lsoa21_code = pl.lsoa21_code AND r.sex = pl.sex AND r.eth19 = pl.eth19
  LEFT JOIN seedmix sm ON g.ltla21_code = sm.ltla21_code AND r.sex = sm.sex AND r.band = sm.band AND r.eth19 = sm.eth19
),
age AS (
  SELECT r.lsoa21_code, g.ltla21_code, r.sex, a.rm032_band AS band, 'age' AS kind, r.age AS key,
         CASE WHEN bt.t200 > 0 THEN r.population * bt.target / bt.t200
              WHEN bt.target > 0 THEN bt.target * COALESCE(ss.shape, 0.0)
              ELSE CAST(r.population AS DOUBLE) END AS population
  FROM rm200 r
  JOIN map_age a ON r.age = a.age
  JOIN census_band_totals bt ON r.lsoa21_code = bt.lsoa21_code AND r.sex = bt.sex AND a.rm032_band = bt.band
  JOIN lsoa_geography g ON r.lsoa21_code = g.lsoa21_code
  LEFT JOIN seedshape ss ON g.ltla21_code = ss.ltla21_code AND r.sex = ss.sex AND r.age = ss.age
)
SELECT * FROM eth UNION ALL SELECT * FROM age;
