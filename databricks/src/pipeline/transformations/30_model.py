"""Model: IPF seed and 2021 base, built lazily and distributed (lsc_pop_dbx.model)."""

from lsc_pop_dbx import model as M
from lsc_pop_dbx.params import config, names_from_conf
from pyspark import pipelines as dp

n = names_from_conf(spark)  # noqa: F821
cfg = config()


@dp.materialized_view(
    name=n.fq("silver", "seed_ltla"),
    comment="IPF seed: LTLA 2021 x sex x 19 ethnic groups x single year, with the ADR-0011 fallbacks (regional split for LTLAs blocked at single year; configured substitutes). Built per region by lsc_pop.base.seed_array.",
)
@dp.expect_or_fail("non_negative_finite", "seed >= 0 AND NOT isnan(seed)")
def seed_ltla():
    return M.seed_ltla(spark, n, cfg)  # noqa: F821


@dp.materialized_view(
    name=n.fq("silver", "base_2021"),
    comment="2021 base (Census day): LSOA x sex x single year x 19 ethnic groups, by iterative proportional fitting (ADR-0003, ADR-0016), fitted per LTLA.",
)
@dp.expect_or_fail("non_negative_finite", "population >= 0 AND NOT isnan(population)")
def base_2021():
    return M.base_2021(spark, n, cfg)  # noqa: F821
