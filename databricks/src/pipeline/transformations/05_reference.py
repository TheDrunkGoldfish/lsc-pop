"""Silver reference tables from the lsc-pop config: parameters, mappings, source-age map."""

from lsc_pop_dbx import reference as R
from lsc_pop_dbx.params import config, names_from_conf
from pyspark import pipelines as dp

n = names_from_conf(spark)  # noqa: F821
cfg = config()


@dp.materialized_view(
    name=n.fq("silver", "params"),
    comment="Every setting from the lsc-pop config.yaml used by the SQL (one row), plus config and code hashes.",
)
def params():
    return R.params(spark, n, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("silver", "map_ethnicity"),
    comment="Ethnicity mapping 19 -> 6 -> 5 (config/mappings/ethnicity_19_to_6.csv).",
)
def map_ethnicity():
    return R.map_ethnicity(spark, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("silver", "map_age"),
    comment="Single year of age -> RM032 band, 23-category code, 5- and 10-year bands.",
)
def map_age():
    return R.map_age(spark, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("silver", "source_age_map"),
    comment="Roll-forward: target age <- 2021 source ages per variant (ADR-0004, ADR-0017).",
)
def source_age_map():
    return R.source_age_map(spark, cfg)  # noqa: F821
