"""Bronze: raw files in the Unity Catalog Volume → tables (lsc_pop_dbx.bronze).

Nomis CSVs and ONS-API JSON lines are Auto Loader streaming tables. Other formats are
materialized views parsed with the same Python as the local pipeline.
"""

from lsc_pop_dbx import bronze as B
from lsc_pop_dbx.params import config, names_from_conf
from pyspark import pipelines as dp

n = names_from_conf(spark)  # noqa: F821 - `spark` is provided by the pipeline runtime
cfg = config()


@dp.table(
    name=n.fq("bronze", "rm032_raw"), comment="Census 2021 RM032 via Nomis (S1), rows as published."
)
@dp.expect_or_fail("lsoa_code_present", "GEOGRAPHY_CODE IS NOT NULL")
@dp.expect_or_fail("non_negative", "OBS_VALUE >= 0")
def rm032_raw():
    return B.rm032_raw(spark, n)  # noqa: F821


@dp.table(
    name=n.fq("bronze", "rm200_raw"), comment="Census 2021 RM200 via Nomis (S2), rows as published."
)
@dp.expect_or_fail("lsoa_code_present", "GEOGRAPHY_CODE IS NOT NULL")
@dp.expect_or_fail("non_negative", "OBS_VALUE >= 0")
def rm200_raw():
    return B.rm200_raw(spark, n)  # noqa: F821


@dp.table(
    name=n.fq("bronze", "seed_raw"),
    comment="ONS custom-dataset API observations (S3): LTLA x ethnic group x sex x age category.",
)
@dp.expect_or_fail("does_not_apply_is_zero", "eth_code <> -8 OR population = 0")
def seed_raw():
    return B.seed_raw(spark, n)  # noqa: F821


@dp.table(
    name=n.fq("bronze", "seed_blocked_raw"),
    comment="LTLAs blocked by ONS disclosure control in the S3 queries.",
)
def seed_blocked_raw():
    return B.seed_blocked_raw(spark, n)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "seed_requested_raw"), comment="Areas requested per S3 query."
)
def seed_requested_raw():
    return B.seed_requested_raw(spark, n)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "ts021_raw"),
    comment="Census 2021 TS021 (S4), long: LSOA x published label.",
)
def ts021_raw():
    return B.ts021_raw(spark, n, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "lookup_nhs_raw"),
    comment="LSOA21 -> sub-ICB -> ICB -> NHS region -> LAD lookup (config.geography.nhs), standard column names.",
)
def lookup_nhs_raw():
    return B.lookup_raw(spark, n, cfg.geography.nhs)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "lookup_census_raw"),
    comment="OA21 -> LSOA21 -> MSOA21 -> LTLA 2021 lookup (config.geography.census).",
)
def lookup_census_raw():
    return B.lookup_raw(spark, n, cfg.geography.census)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "lookup_ltla_region_raw"),
    comment="LTLA 2021 -> region lookup (config.geography.ltla_region).",
)
def lookup_ltla_region_raw():
    return B.lookup_raw(spark, n, cfg.geography.ltla_region)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "iod_raw"),
    comment="English Indices of Deprivation 2025, File 7 (S8), standard column names.",
)
@dp.expect_or_fail("lsoa_code_present", "lsoa21cd IS NOT NULL")
def iod_raw():
    return B.iod_raw(spark, n, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "mye_raw"),
    comment="ONS mid-year LSOA estimates (S5), reference-year sheet, wide as published.",
)
@dp.expect_or_fail("lsoa_code_present", "lsoa21cd IS NOT NULL")
def mye_raw():
    return B.mye_raw(spark, n, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("bronze", "mye_broad_raw"),
    comment="ONS accredited broad-age LSOA estimates (S5b), for validation.",
)
def mye_broad_raw():
    return B.mye_broad_raw(spark, n, cfg)  # noqa: F821


def _ohid(table: str):
    @dp.materialized_view(
        name=n.fq("bronze", table),
        comment=f"OHID acute trust catchments (S9), sheet {B.OHID_SHEETS[table]}, as text.",
    )
    def _t():
        return B.ohid_raw(spark, n, cfg, table)  # noqa: F821

    return _t


for _table in B.OHID_SHEETS:
    _ohid(_table)
