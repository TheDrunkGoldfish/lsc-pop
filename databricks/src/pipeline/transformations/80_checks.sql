-- Validation checks (local equivalents: validate.check calls in each lsc_pop stage; same ids).
-- Each family is a table of (check_id, stage, description, hard, passed, metrics). A failing hard
-- check fails the pipeline update (expect ... ON VIOLATION FAIL UPDATE); soft checks are logged.
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_audit};

CREATE OR REFRESH MATERIALIZED VIEW checks_geography (
  CONSTRAINT hard_checks_pass EXPECT (passed OR NOT hard) ON VIOLATION FAIL UPDATE,
  CONSTRAINT soft_checks_pass EXPECT (passed OR hard)
)
COMMENT 'Geography checks GEO-02 to GEO-09 (brief s10).'
AS
WITH g AS (SELECT * FROM ${lsc_pop.schema_silver}.lsoa_geography),
p AS (SELECT * FROM ${lsc_pop.schema_silver}.params),
nest AS (
  SELECT 'GEO-05' AS id, 'sicbl_cd nests within icb_cd' AS d, COUNT(*) AS bad FROM (SELECT sicbl_cd FROM g GROUP BY sicbl_cd HAVING COUNT(DISTINCT icb_cd) > 1)
  UNION ALL SELECT 'GEO-06', 'icb_cd nests within nhser_cd', COUNT(*) FROM (SELECT icb_cd FROM g GROUP BY icb_cd HAVING COUNT(DISTINCT nhser_cd) > 1)
  UNION ALL SELECT 'GEO-07', 'msoa21cd nests within ltla21cd', COUNT(*) FROM (SELECT msoa21cd FROM g GROUP BY msoa21cd HAVING COUNT(DISTINCT ltla21cd) > 1)
  UNION ALL SELECT 'GEO-08', 'ltla21cd nests within lad_cd', COUNT(*) FROM (SELECT ltla21cd FROM g GROUP BY ltla21cd HAVING COUNT(DISTINCT lad_cd) > 1)
  UNION ALL SELECT 'GEO-09', 'ltla21cd nests within rgn21cd', COUNT(*) FROM (SELECT ltla21cd FROM g GROUP BY ltla21cd HAVING COUNT(DISTINCT rgn21cd) > 1)
)
SELECT 'GEO-02' AS check_id, 'geography' AS stage, 'England LSOA count matches expected' AS description, TRUE AS hard,
       (SELECT COUNT(*) FROM g) = (SELECT expected_lsoa_count FROM p) AS passed,
       to_json(named_struct('lsoas', (SELECT COUNT(*) FROM g), 'expected', (SELECT expected_lsoa_count FROM p))) AS metrics
UNION ALL
SELECT 'GEO-03', 'geography', 'LSOA codes unique', TRUE,
       (SELECT COUNT(*) FROM g) = (SELECT COUNT(DISTINCT lsoa21cd) FROM g), to_json(named_struct('rows', (SELECT COUNT(*) FROM g)))
UNION ALL
SELECT id, 'geography', d, TRUE, bad = 0, to_json(named_struct('violations', bad)) FROM nest;

CREATE OR REFRESH MATERIALIZED VIEW checks_census (
  CONSTRAINT hard_checks_pass EXPECT (passed OR NOT hard) ON VIOLATION FAIL UPDATE,
  CONSTRAINT soft_checks_pass EXPECT (passed OR hard)
)
COMMENT 'Census checks CEN-01, CEN-03, CEN-05, CEN-10, CEN-12 (ADR-0015).'
AS
WITH c01 AS (
  SELECT COUNT(*) AS bad FROM (
    SELECT GEOGRAPHY_CODE, C_SEX, C2021_AGE_6,
           SUM(CASE WHEN C2021_ETH_20 = 0 THEN OBS_VALUE ELSE 0 END) AS total,
           SUM(CASE WHEN C2021_ETH_20 > 0 THEN OBS_VALUE ELSE 0 END) AS parts
    FROM ${lsc_pop.schema_bronze}.rm032_raw GROUP BY GEOGRAPHY_CODE, C_SEX, C2021_AGE_6) WHERE total <> parts
),
c03 AS (
  SELECT COUNT(*) AS bad FROM (
    SELECT GEOGRAPHY_CODE, C_SEX,
           SUM(CASE WHEN C2021_AGE_92 = 0 THEN OBS_VALUE ELSE 0 END) AS total,
           SUM(CASE WHEN C2021_AGE_92 > 0 THEN OBS_VALUE ELSE 0 END) AS parts
    FROM ${lsc_pop.schema_bronze}.rm200_raw GROUP BY GEOGRAPHY_CODE, C_SEX) WHERE total <> parts
),
c05 AS (
  SELECT COUNT(*) AS bad FROM (
    SELECT t.lsoa21cd,
           SUM(CASE WHEN t.label = 'Ethnic group: Total: All usual residents' THEN t.population ELSE 0 END) AS total,
           SUM(CASE WHEN m.label IS NOT NULL THEN t.population ELSE 0 END) AS parts
    FROM ${lsc_pop.schema_bronze}.ts021_raw t
    LEFT JOIN (SELECT concat('Ethnic group: ', label_19) AS label FROM ${lsc_pop.schema_silver}.map_ethnicity) m ON t.label = m.label
    WHERE t.lsoa21cd LIKE 'E%' GROUP BY t.lsoa21cd) WHERE total <> parts
),
c10 AS (
  SELECT MAX(ABS(e - a)) AS gap FROM (
    SELECT lsoa21cd, sex, band, SUM(CASE WHEN kind = 'eth19' THEN population END) AS e, SUM(CASE WHEN kind = 'age' THEN population END) AS a
    FROM ${lsc_pop.schema_silver}.census_margins GROUP BY lsoa21cd, sex, band)
),
c12 AS (
  SELECT COUNT_IF(ABS(b.target - CASE WHEN p.margin_source = 'rm032' THEN b.t200 ELSE b.t032 END)
                  > GREATEST(p.warn_abs, p.warn_rel * CASE WHEN p.margin_source = 'rm032' THEN b.t200 ELSE b.t032 END)) AS flagged,
         COUNT(*) AS bands
  FROM ${lsc_pop.schema_silver}.census_band_totals b CROSS JOIN ${lsc_pop.schema_silver}.params p
)
SELECT 'CEN-01' AS check_id, 'census' AS stage, 'RM032 Does not apply = 0 (all-groups total = sum of 19 groups)' AS description,
       TRUE AS hard, bad = 0 AS passed, to_json(named_struct('cells_nonzero', bad)) AS metrics FROM c01
UNION ALL SELECT 'CEN-03', 'census', 'RM200 all-ages total = sum of single years', TRUE, bad = 0, to_json(named_struct('cells_nonzero', bad)) FROM c03
UNION ALL SELECT 'CEN-05', 'census', 'TS021 total = sum of 19 groups', TRUE, bad = 0, to_json(named_struct('lsoas_nonzero', bad)) FROM c05
UNION ALL SELECT 'CEN-10', 'census', 'Reconciled ethnic and age margins agree on every LSOA x sex x band total', TRUE, gap < 1e-6, to_json(named_struct('max_gap', gap)) FROM c10
UNION ALL SELECT 'CEN-12', 'census', 'Band-total adjustment within max(warn_abs, warn_rel) (soft)', FALSE, flagged = 0, to_json(named_struct('bands_flagged', flagged, 'bands', bands)) FROM c12;

CREATE OR REFRESH MATERIALIZED VIEW checks_model (
  CONSTRAINT hard_checks_pass EXPECT (passed OR NOT hard) ON VIOLATION FAIL UPDATE,
  CONSTRAINT soft_checks_pass EXPECT (passed OR hard)
)
COMMENT 'Base and roll-forward checks BAS-01/02/03/07 and ROL-01/02/04/05/07.'
AS
WITH p AS (SELECT * FROM ${lsc_pop.schema_silver}.params),
base_eth AS (
  SELECT MAX(ABS(b.pop - m.population)) AS err FROM (
    SELECT x.lsoa21cd, x.sex, a.rm032_band AS band, x.eth19, SUM(x.population) AS pop
    FROM ${lsc_pop.schema_silver}.base_2021 x JOIN ${lsc_pop.schema_silver}.map_age a ON x.age = a.age
    GROUP BY x.lsoa21cd, x.sex, a.rm032_band, x.eth19) b
  JOIN ${lsc_pop.schema_silver}.census_margins m
    ON m.kind = 'eth19' AND b.lsoa21cd = m.lsoa21cd AND b.sex = m.sex AND b.band = m.band AND b.eth19 = m.key
),
base_age AS (
  SELECT MAX(ABS(b.pop - m.population)) AS err FROM (
    SELECT lsoa21cd, sex, age, SUM(population) AS pop FROM ${lsc_pop.schema_silver}.base_2021 GROUP BY lsoa21cd, sex, age) b
  JOIN ${lsc_pop.schema_silver}.census_margins m ON m.kind = 'age' AND b.lsoa21cd = m.lsoa21cd AND b.sex = m.sex AND b.age = m.key
),
totals AS (
  SELECT (SELECT SUM(population) FROM ${lsc_pop.schema_silver}.base_2021) AS base_total,
         (SELECT SUM(population) FROM ${lsc_pop.schema_silver}.census_margins WHERE kind = 'age') AS margin_total,
         (SELECT COUNT_IF(population < 0 OR isnan(population)) FROM ${lsc_pop.schema_silver}.base_2021) AS base_bad,
         (SELECT SUM(population) FROM ${lsc_pop.schema_gold}.fact_population) AS fact_total,
         (SELECT SUM(population) FROM ${lsc_pop.schema_silver}.mye) AS mye_total,
         (SELECT MAX(population) FROM ${lsc_pop.schema_silver}.mye) AS mye_max
),
rol01 AS (
  SELECT COUNT(*) AS missing FROM ${lsc_pop.schema_silver}.lsoa_geography g
  LEFT ANTI JOIN (SELECT DISTINCT lsoa21cd FROM ${lsc_pop.schema_silver}.mye) m ON g.lsoa21cd = m.lsoa21cd
),
rol02 AS (
  SELECT COUNT(*) AS bad FROM (
    SELECT r.lsoa21cd, MAX(r.total) AS total, SUM(m.population) AS parts
    FROM ${lsc_pop.schema_bronze}.mye_raw r JOIN ${lsc_pop.schema_silver}.mye m ON r.lsoa21cd = m.lsoa21cd
    GROUP BY r.lsoa21cd) WHERE total <> parts
),
rol04 AS (
  SELECT MAX(ABS(o.ours - b.theirs)) AS gap FROM (
    SELECT lsoa21cd, concat(lower(sex), CASE WHEN age <= 15 THEN '0_to_15' WHEN age <= 29 THEN '16_to_29'
                         WHEN age <= 44 THEN '30_to_44' WHEN age <= 64 THEN '45_to_64' ELSE '65_and_over' END) AS k,
           SUM(population) AS ours
    FROM ${lsc_pop.schema_silver}.mye GROUP BY 1, 2) o
  JOIN (SELECT lsoa21cd, k, theirs FROM ${lsc_pop.schema_bronze}.mye_broad_raw
        UNPIVOT (theirs FOR k IN (f0_to_15, f16_to_29, f30_to_44, f45_to_64, f65_and_over,
                                  m0_to_15, m16_to_29, m30_to_44, m45_to_64, m65_and_over))) b
    ON o.lsoa21cd = b.lsoa21cd AND o.k = b.k
),
rol05 AS (
  SELECT MAX(ABS(f.pop - m.population)) AS gap FROM (
    SELECT lsoa21cd, sex, age, SUM(population) AS pop FROM ${lsc_pop.schema_gold}.fact_population GROUP BY lsoa21cd, sex, age) f
  JOIN ${lsc_pop.schema_silver}.mye m ON f.lsoa21cd = m.lsoa21cd AND f.sex = m.sex AND f.age = m.age
)
SELECT 'BAS-01' AS check_id, 'base' AS stage, 'Base reproduces reconciled RM032 (eth x sex x band) within IPF tolerance' AS description,
       TRUE AS hard, err < 10 * (SELECT ipf_tolerance FROM p) AS passed, to_json(named_struct('max_abs', err)) AS metrics FROM base_eth
UNION ALL SELECT 'BAS-02', 'base', 'Base reproduces RM200 (sex x single year) within IPF tolerance', TRUE,
       err < 10 * (SELECT ipf_tolerance FROM p), to_json(named_struct('max_abs', err)) FROM base_age
UNION ALL SELECT 'BAS-03', 'base', 'Base total = reconciled margin total (RM200)', TRUE,
       ABS(base_total - margin_total) < 1e-3, to_json(named_struct('base_total', base_total, 'margin_total', margin_total)) FROM totals
UNION ALL SELECT 'BAS-07', 'base', 'Base non-negative and finite', TRUE, base_bad = 0, to_json(named_struct('bad_cells', base_bad)) FROM totals
UNION ALL SELECT 'ROL-01', 'rollforward', 'Mid-year estimates cover every lookup LSOA', TRUE, missing = 0, to_json(named_struct('missing', missing)) FROM rol01
UNION ALL SELECT 'ROL-02', 'rollforward', 'Mid-year Total = sum of sex x single-year cells', TRUE, bad = 0, to_json(named_struct('lsoas_nonzero', bad)) FROM rol02
UNION ALL SELECT 'ROL-04', 'rollforward', 'S5 single-year file agrees with accredited broad-age S5b (soft)', FALSE, gap = 0, to_json(named_struct('max_abs_diff', gap)) FROM rol04
UNION ALL SELECT 'ROL-05', 'rollforward', 'Estimates sum to S5 for every LSOA x sex x age', TRUE,
       gap <= 1e-9 * GREATEST(1.0, (SELECT mye_max FROM totals)), to_json(named_struct('max_abs_gap', gap)) FROM rol05
UNION ALL SELECT 'ROL-07', 'rollforward', 'Estimates total = S5 total', TRUE, ABS(fact_total - mye_total) < 1e-3,
       to_json(named_struct('total', fact_total, 's5_total', mye_total)) FROM totals;

CREATE OR REFRESH MATERIALIZED VIEW checks_outputs (
  CONSTRAINT hard_checks_pass EXPECT (passed OR NOT hard) ON VIOLATION FAIL UPDATE,
  CONSTRAINT soft_checks_pass EXPECT (passed OR hard)
)
COMMENT 'Deprivation, catchment and output checks DEP-01, DEP-03, CAT-01, CAT-03, CAT-05, OUT-01, OUT-03, OUT-04.'
AS
WITH l AS (SELECT * FROM ${lsc_pop.schema_gold}.dim_lsoa),
dep01 AS (SELECT (SELECT COUNT(*) FROM ${lsc_pop.schema_silver}.iod) AS iod_rows, (SELECT COUNT(*) FROM l) AS lsoas),
dep03_q AS (
  SELECT CASE WHEN imd_local_quintile_within = 'icb' THEN icb_cd ELSE lad_cd END AS grp, imd_local_quintile,
         SUM(population_mid_year) AS pop
  FROM l GROUP BY 1, 2
),
dep03 AS (SELECT MAX(ABS(share - 0.2)) AS dev FROM (SELECT pop / SUM(pop) OVER (PARTITION BY grp) AS share FROM dep03_q)),
cat01 AS (
  SELECT (SELECT COUNT(DISTINCT msoa21cd) FROM ${lsc_pop.schema_silver}.ohid_shares) AS ohid,
         (SELECT COUNT(DISTINCT msoa21cd) FROM ${lsc_pop.schema_silver}.lsoa_geography) AS lookup
),
cat03 AS (SELECT MAX(s) AS max_sum FROM (SELECT msoa21cd, SUM(proportion_published) AS s FROM ${lsc_pop.schema_silver}.ohid_shares GROUP BY msoa21cd)),
cat05 AS (
  SELECT MAX(GREATEST(ABS(p - 1), ABS(r - 1))) AS err, COUNT(*) AS lsoas FROM (
    SELECT lsoa21cd, SUM(proportion_published) AS p, SUM(proportion_rescaled) AS r
    FROM ${lsc_pop.schema_gold}.bridge_lsoa_trust GROUP BY lsoa21cd)
),
out01 AS (
  SELECT (SELECT COUNT(*) FROM (SELECT DISTINCT lsoa21cd FROM ${lsc_pop.schema_gold}.fact_population) f LEFT ANTI JOIN l ON f.lsoa21cd = l.lsoa21cd)
       + (SELECT COUNT(*) FROM (SELECT DISTINCT eth19 FROM ${lsc_pop.schema_gold}.fact_population) f LEFT ANTI JOIN ${lsc_pop.schema_gold}.dim_ethnicity e ON f.eth19 = e.eth19)
       + (SELECT COUNT(*) FROM (SELECT DISTINCT age FROM ${lsc_pop.schema_gold}.fact_population) f LEFT ANTI JOIN ${lsc_pop.schema_gold}.dim_age a ON f.age = a.age)
       + (SELECT COUNT(*) FROM (SELECT DISTINCT trust_code FROM ${lsc_pop.schema_gold}.bridge_lsoa_trust) b LEFT ANTI JOIN ${lsc_pop.schema_gold}.dim_trust t ON b.trust_code = t.trust_code) AS orphans
),
out03 AS (
  SELECT MAX(ABS(f.pop - d.pop)) AS gap, COUNT(*) AS icbs FROM (
    SELECT l.icb_cd, SUM(f.population) AS pop FROM ${lsc_pop.schema_gold}.fact_population f JOIN l ON f.lsoa21cd = l.lsoa21cd GROUP BY l.icb_cd) f
  JOIN (SELECT icb_cd, SUM(population_mid_year) AS pop FROM l GROUP BY icb_cd) d ON f.icb_cd = d.icb_cd
),
out04 AS (
  SELECT (SELECT SUM(b.proportion_published * l.population_mid_year) FROM ${lsc_pop.schema_gold}.bridge_lsoa_trust b JOIN l ON b.lsoa21cd = l.lsoa21cd) AS trusts,
         (SELECT SUM(population_mid_year) FROM l) AS population
)
SELECT 'DEP-01' AS check_id, 'deprivation' AS stage, 'IoD covers exactly the lookup LSOAs (1:1)' AS description, TRUE AS hard,
       iod_rows = lsoas AS passed, to_json(named_struct('iod_rows', iod_rows, 'lsoas', lsoas)) AS metrics FROM dep01
UNION ALL SELECT 'DEP-03', 'deprivation', 'Local IMD quintiles hold ~20% of each group population (soft: <= 5pp)', FALSE, dev <= 0.05, to_json(named_struct('max_abs_deviation', dev)) FROM dep03
UNION ALL SELECT 'CAT-01', 'catchments', 'OHID MSOAs = lookup MSOAs (MSOA 2021, England)', TRUE, ohid = lookup, to_json(named_struct('ohid', ohid, 'lookup', lookup)) FROM cat01
UNION ALL SELECT 'CAT-03', 'catchments', 'Published proportions per MSOA sum to <= 1', TRUE, max_sum <= 1 + 1e-9, to_json(named_struct('max', max_sum)) FROM cat03
UNION ALL SELECT 'CAT-05', 'catchments', 'Bridge proportions sum to 1 per LSOA (published incl. UNASSIGNED; rescaled)', TRUE, err < 1e-9, to_json(named_struct('max_err', err, 'lsoas', lsoas)) FROM cat05
UNION ALL SELECT 'OUT-01', 'outputs', 'Referential integrity of the star schema', TRUE, orphans = 0, to_json(named_struct('orphans', orphans)) FROM out01
UNION ALL SELECT 'OUT-03', 'outputs', 'ICB totals from fact = sum of dim_lsoa populations', TRUE, gap < 1e-6, to_json(named_struct('max_abs_gap', gap, 'icbs', icbs)) FROM out03
UNION ALL SELECT 'OUT-04', 'outputs', 'Sum over trusts incl. UNASSIGNED = England total', TRUE, ABS(trusts - population) < 1e-6 * population,
       to_json(named_struct('trust_total', trusts, 'population', population)) FROM out04;

CREATE OR REFRESH MATERIALIZED VIEW validation
COMMENT 'All pipeline checks of the latest update (same ids as the local validation report). OHID checks: audit.ohid_checks.'
AS SELECT check_id, stage, description, hard, passed, metrics FROM checks_geography
   UNION ALL SELECT check_id, stage, description, hard, passed, metrics FROM checks_census
   UNION ALL SELECT check_id, stage, description, hard, passed, metrics FROM checks_model
   UNION ALL SELECT check_id, stage, description, hard, passed, metrics FROM checks_outputs;
-- CAT-07 to CAT-11 (OHID comparisons) are written to audit.ohid_checks by the audit job task.
