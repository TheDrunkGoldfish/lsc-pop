"""Model: the IPF seed and the 2021 base, lazily built and distributed (ADR-0003/0011/0022).

Pipeline dataset functions must only *describe* their result: Databricks calls them while analysing
the pipeline graph, before upstream tables hold data. So nothing here collects data to the driver.

* ``seed_ltla``: ``groupBy(rgn21_code).applyInPandas``. Each region builds its LTLAs' seed with the
  same ``lsc_pop.base.seed_array`` as the local pipeline. The regional single-year fallback only
  needs LTLAs from the same region, and configured seed substitutes must be in the same region
  (checked).
* ``base_2021``: margins and seed are co-grouped by LTLA, and each group fits its LSOA × sex × band
  tables with the same numpy ``ipf_fit`` (``lsc_pop.base.fit_arrays``). IPF tables are
  independent, so the result matches one national batch to within the IPF tolerance.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from lsc_pop.base import ETH, SEXES, fit_arrays, margin_arrays, seed_array

from .params import Names

SEED_SCHEMA = (
    "rgn21_code string, ltla21_code string, sex string, eth19 int, age int, "
    "seed double, seed_source string"
)
BASE_SCHEMA = (
    "lsoa21_code string, ltla21_code string, sex string, age int, eth19 int, population double"
)
_INPUT_TYPES = {
    "ltla21_code": "string",
    "kind": "string",
    "eth19": "int",
    "sex": "string",
    "age": "int",
    "population": "double",
    "classification": "string",
}


def _padded(df: DataFrame, kind: str) -> DataFrame:
    """Give one input part the common column set (missing columns as typed NULLs)."""
    cols = []
    for c, typ in _INPUT_TYPES.items():
        if c == "kind":
            cols.append(F.lit(kind).alias("kind"))
        elif c in df.columns:
            cols.append(F.col(c).cast(typ).alias(c))
        else:
            cols.append(F.lit(None).cast(typ).alias(c))
    return df.select(*cols)


def seed_ltla(spark, n: Names, cfg) -> DataFrame:
    t = lambda name: spark.read.table(n.fq("silver", name))  # noqa: E731
    ltla_rgn = t("lsoa_geography").select("ltla21_code", "rgn21_code").distinct()
    s91 = t("seed_age91").select(
        "ltla21_code", "eth19", "sex", "age", F.col("population").cast("double").alias("population")
    )
    s23 = t("seed_age23").select(
        "ltla21_code",
        "eth19",
        "sex",
        F.col("age23").alias("age"),
        F.col("population").cast("double").alias("population"),
    )
    blocked = t("seed_blocked").select("ltla21_code", "classification")
    rows = (
        _padded(s91, "s91")
        .unionByName(_padded(s23, "s23"))
        .unionByName(_padded(blocked, "blocked"))
        .unionByName(_padded(ltla_rgn, "ltla"))
        .join(ltla_rgn, "ltla21_code")
    )
    subs = dict(cfg.ipf.seed_substitutes)
    n_age = cfg.age.max_age + 1

    def build(pdf: pd.DataFrame) -> pd.DataFrame:
        rgn = pdf["rgn21_code"].iloc[0]
        lookup = pdf.loc[pdf["kind"] == "ltla", ["ltla21_code", "rgn21_code"]].drop_duplicates()
        missing = {s for c, s in subs.items() if c in set(lookup["ltla21_code"])} - set(
            lookup["ltla21_code"]
        )
        if missing:
            raise ValueError(
                f"seed substitutes {sorted(missing)} must be in the same region as the LTLA ({rgn})"
            )
        g = lambda k, cols: pdf.loc[pdf["kind"] == k, cols].reset_index(drop=True)  # noqa: E731
        s91p = g("s91", ["ltla21_code", "eth19", "sex", "age", "population"]).astype(
            {"eth19": int, "age": int}
        )
        s23p = g("s23", ["ltla21_code", "eth19", "sex", "age", "population"]).rename(
            columns={"age": "age23"}
        )
        s23p = s23p.astype({"eth19": int, "age23": int})
        bl = g("blocked", ["ltla21_code", "classification"])
        seed, ltlas, src = seed_array(cfg, s91p, s23p, bl, lookup)
        idx = np.indices(seed.shape).reshape(4, -1)  # (ltla, sex, eth, age)
        source = dict(zip(src["ltla21_code"], src["seed_source"], strict=True))
        lt = np.asarray(ltlas)[idx[0]]
        return pd.DataFrame(
            {
                "rgn21_code": rgn,
                "ltla21_code": lt,
                "sex": np.asarray(SEXES)[idx[1]],
                "eth19": np.asarray(ETH)[idx[2]].astype("int32"),
                "age": np.arange(n_age)[idx[3]].astype("int32"),
                "seed": seed.reshape(-1),
                "seed_source": pd.Series(lt).map(source).to_numpy(),
            }
        )

    return rows.groupBy("rgn21_code").applyInPandas(build, schema=SEED_SCHEMA)


def base_2021(spark, n: Names, cfg) -> DataFrame:
    t = lambda name: spark.read.table(n.fq("silver", name))  # noqa: E731
    margins = t("census_margins").select(
        "lsoa21_code", "ltla21_code", "sex", "band", "kind", "key", "population"
    )
    seed = t("seed_ltla").select("ltla21_code", "sex", "eth19", "age", "seed")
    floor = cfg.ipf.seed_floor
    n_age = cfg.age.max_age + 1
    si = {s: i for i, s in enumerate(SEXES)}

    def fit_ltla(m: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
        if m.empty:
            return pd.DataFrame(columns=[c.split()[0] for c in BASE_SCHEMA.split(", ")])
        ltla = m["ltla21_code"].iloc[0]
        lsoas = sorted(m["lsoa21_code"].unique())
        eth_m, age_m = margin_arrays(cfg, m, lsoas)
        arr = np.zeros((1, 2, len(ETH), n_age))
        arr[0, s["sex"].map(si).to_numpy(), s["eth19"].to_numpy() - 1, s["age"].to_numpy()] = s[
            "seed"
        ].to_numpy()
        base, _diag = fit_arrays(cfg, arr, np.zeros(len(lsoas), dtype=int), eth_m, age_m, floor)
        idx = np.indices(base.shape).reshape(4, -1)  # (lsoa, sex, age, eth)
        return pd.DataFrame(
            {
                "lsoa21_code": np.asarray(lsoas)[idx[0]],
                "ltla21_code": ltla,
                "sex": np.asarray(SEXES)[idx[1]],
                "age": np.arange(n_age)[idx[2]].astype("int32"),
                "eth19": np.asarray(ETH)[idx[3]].astype("int32"),
                "population": base.reshape(-1),
            }
        )

    return (
        margins.groupBy("ltla21_code")
        .cogroup(seed.groupBy("ltla21_code"))
        .applyInPandas(fit_ltla, schema=BASE_SCHEMA)
    )
