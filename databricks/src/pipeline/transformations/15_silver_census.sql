-- Stage B (part 1): tidy Census 2021 tables and the mid-year estimates (local: lsc_pop.census, rollforward).
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_silver};

CREATE OR REFRESH MATERIALIZED VIEW rm032 (
  CONSTRAINT valid_codes EXPECT (sex IN ('F', 'M') AND band BETWEEN 1 AND 5 AND eth19 BETWEEN 1 AND 19) ON VIOLATION FAIL UPDATE,
  CONSTRAINT non_negative EXPECT (population >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'Census 2021 RM032: LSOA x sex x RM032 band (1-5) x 19 ethnic groups (S1, as published; all-groups total rows removed).'
AS SELECT GEOGRAPHY_CODE AS lsoa21cd,
          CASE C_SEX WHEN 1 THEN 'F' WHEN 2 THEN 'M' END AS sex,
          C2021_AGE_6 AS band, C2021_ETH_20 AS eth19, OBS_VALUE AS population
   FROM ${lsc_pop.schema_bronze}.rm032_raw
   WHERE C2021_ETH_20 > 0 AND GEOGRAPHY_CODE LIKE 'E%';

CREATE OR REFRESH MATERIALIZED VIEW rm200 (
  CONSTRAINT valid_codes EXPECT (sex IN ('F', 'M') AND age BETWEEN 0 AND 90) ON VIOLATION FAIL UPDATE,
  CONSTRAINT non_negative EXPECT (population >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'Census 2021 RM200: LSOA x sex x single year of age 0-90+ (S2; Nomis age code - 1).'
AS SELECT GEOGRAPHY_CODE AS lsoa21cd,
          CASE C_SEX WHEN 1 THEN 'F' WHEN 2 THEN 'M' END AS sex,
          C2021_AGE_92 - 1 AS age, OBS_VALUE AS population
   FROM ${lsc_pop.schema_bronze}.rm200_raw
   WHERE C2021_AGE_92 > 0 AND GEOGRAPHY_CODE LIKE 'E%';

CREATE OR REFRESH MATERIALIZED VIEW ts021 (
  CONSTRAINT non_negative EXPECT (population >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'Census 2021 TS021: LSOA x 19 ethnic groups (S4), validation only.'
AS SELECT t.lsoa21cd, m.eth19, t.population
   FROM ${lsc_pop.schema_bronze}.ts021_raw t
   JOIN (SELECT concat('Ethnic group: ', label_19) AS label, eth19 FROM map_ethnicity) m ON t.label = m.label
   WHERE t.lsoa21cd LIKE 'E%';

CREATE OR REFRESH MATERIALIZED VIEW seed_age91 (
  CONSTRAINT non_negative EXPECT (population >= 0) ON VIOLATION FAIL UPDATE
)
COMMENT 'IPF seed: LTLA 2021 x 19 ethnic groups x sex x single year (S3, ONS custom-dataset API).'
AS SELECT ltla21cd, eth_code AS eth19, CASE sex_code WHEN 1 THEN 'F' WHEN 2 THEN 'M' END AS sex,
          age_code AS age, population
   FROM ${lsc_pop.schema_bronze}.seed_raw WHERE classification = 'age_91a' AND eth_code > 0;

CREATE OR REFRESH MATERIALIZED VIEW seed_age23
COMMENT 'IPF seed fallback: LTLA 2021 x 19 ethnic groups x sex x 23 age categories (S3).'
AS SELECT ltla21cd, eth_code AS eth19, CASE sex_code WHEN 1 THEN 'F' WHEN 2 THEN 'M' END AS sex,
          age_code AS age23, population
   FROM ${lsc_pop.schema_bronze}.seed_raw WHERE classification = 'age_23a' AND eth_code > 0;

CREATE OR REFRESH MATERIALIZED VIEW seed_blocked
COMMENT 'LTLAs blocked by ONS disclosure control in the seed queries (ADR-0011).'
AS SELECT DISTINCT ltla21cd, classification FROM ${lsc_pop.schema_bronze}.seed_blocked_raw;

CREATE OR REFRESH MATERIALIZED VIEW mye (
  CONSTRAINT valid_codes EXPECT (sex IN ('F', 'M') AND age BETWEEN 0 AND 90) ON VIOLATION FAIL UPDATE,
  CONSTRAINT non_negative_integer EXPECT (population >= 0 AND population = round(population)) ON VIOLATION FAIL UPDATE
)
COMMENT 'ONS mid-year LSOA estimates (S5) for the reference year: LSOA x sex x single year (supporting information).'
AS SELECT lsoa21cd, substr(col, 1, 1) AS sex, CAST(substr(col, 2) AS INT) AS age, population
   FROM (SELECT * FROM ${lsc_pop.schema_bronze}.mye_raw WHERE lsoa21cd LIKE 'E%')
   UNPIVOT (population FOR col IN (
     F0, F1, F2, F3, F4, F5, F6, F7, F8, F9, F10, F11, F12,
     F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25,
     F26, F27, F28, F29, F30, F31, F32, F33, F34, F35, F36, F37, F38,
     F39, F40, F41, F42, F43, F44, F45, F46, F47, F48, F49, F50, F51,
     F52, F53, F54, F55, F56, F57, F58, F59, F60, F61, F62, F63, F64,
     F65, F66, F67, F68, F69, F70, F71, F72, F73, F74, F75, F76, F77,
     F78, F79, F80, F81, F82, F83, F84, F85, F86, F87, F88, F89, F90,
     M0, M1, M2, M3, M4, M5, M6, M7, M8, M9, M10, M11, M12,
     M13, M14, M15, M16, M17, M18, M19, M20, M21, M22, M23, M24, M25,
     M26, M27, M28, M29, M30, M31, M32, M33, M34, M35, M36, M37, M38,
     M39, M40, M41, M42, M43, M44, M45, M46, M47, M48, M49, M50, M51,
     M52, M53, M54, M55, M56, M57, M58, M59, M60, M61, M62, M63, M64,
     M65, M66, M67, M68, M69, M70, M71, M72, M73, M74, M75, M76, M77,
     M78, M79, M80, M81, M82, M83, M84, M85, M86, M87, M88, M89, M90
   ));
