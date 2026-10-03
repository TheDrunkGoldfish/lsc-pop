-- Stage F/G inputs: IoD 2025 and OHID catchments, typed and filtered (local: lsc_pop.deprivation, catchments).
USE CATALOG ${lsc_pop.catalog};
USE SCHEMA ${lsc_pop.schema_silver};

CREATE OR REFRESH MATERIALIZED VIEW iod (
  CONSTRAINT rank_and_decile_valid EXPECT (imd_rank >= 1 AND imd_decile BETWEEN 1 AND 10) ON VIOLATION FAIL UPDATE
)
COMMENT 'English Indices of Deprivation (IoD) 2025 at LSOA 2021 (S8 File 7): all ranks, scores and deciles; national IMD quintile; Core20 (ADR-0008).'
AS SELECT i.*, p.iod_edition,
          CAST(FLOOR((i.imd_decile + 1) / 2) AS INT) AS imd_quintile,
          i.imd_decile <= p.core20_max_decile AS core20
   FROM (SELECT * EXCEPT (_source_file, _ingested_at) FROM ${lsc_pop.schema_bronze}.iod_raw) i CROSS JOIN params p;

CREATE OR REFRESH MATERIALIZED VIEW ohid_shares (
  CONSTRAINT proportion_valid EXPECT (proportion_published BETWEEN 0 AND 1) ON VIOLATION FAIL UPDATE
)
COMMENT 'OHID acute trust catchment shares (T2) for the configured catchment year and admission type, by MSOA 2021 x trust (S9; ADR-0019).'
AS SELECT r.trust_code, r.msoa21cd AS msoa21_code, CAST(r.patients_admitted_as_a_proportion_of_total_patients AS DOUBLE) AS proportion_published,
          lower(r.first_past_the_post_fptp) IN ('true', '1') AS fptp
   FROM ${lsc_pop.schema_bronze}.ohid_t2_raw r CROSS JOIN params p
   WHERE r.catchment_year = CAST(p.catchment_year AS STRING)
     AND lower(trim(r.admission_type)) = lower(p.admission_type);

CREATE OR REFRESH MATERIALIZED VIEW trust_host_icb
COMMENT 'Trust -> ICB ODS code from the active ODS relationship configured as the host-ICB link (RE5, is located in the geography of; ADR-0025). May hold several rows per trust if ODS does; check CAT-12.'
AS SELECT r.org_code AS trust_code, r.target_code AS icb_ods_code
   FROM ${lsc_pop.schema_bronze}.ods_trust_relationships_raw r CROSS JOIN params p
   WHERE r.relationship_id = p.host_icb_relationship AND r.target_role_id = p.host_icb_target_role AND r.status = 'Active';
