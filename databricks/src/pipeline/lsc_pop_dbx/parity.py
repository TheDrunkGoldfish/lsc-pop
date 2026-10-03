"""Parity: Databricks gold tables vs the local reference pipeline's outputs (ADR-0024).

Runs anywhere Spark can read both. Used by the local tests and by the optional Databricks job
``lsc_pop_parity_<target>`` (``databricks/src/parity_task.py``), which reads reference Parquet
uploaded to ``<volume>/reference/`` (the ``tables/`` folder of a local run).

Tolerances:

* ``fact_population``: every cell matched on (lsoa21_code, sex, age, eth19);
  |difference| ≤ 1e-6 persons. Hash equality isn't expected: IPF fitted LTLA by LTLA converges
  in a different number of iterations than one national batch, and Spark sums in a different
  order.
* Dimensions and bridge: identical rows and values (numeric columns to 1e-6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

FACT_TOLERANCE = 1e-6
KEYS = {
    "dim_lsoa": ["lsoa21_code"],
    "dim_ethnicity": ["eth19"],
    "dim_age": ["age"],
    "dim_trust": ["trust_code"],
    "dim_region": ["rgn21_code"],
    "dim_ltla": ["ltla21_code"],
    "dim_msoa": ["msoa21_code"],
    "dim_lad": ["lad_code"],
    "dim_nhs_region": ["nhser_code"],
    "dim_icb": ["icb_code"],
    "dim_sub_icb": ["sicbl_code"],
    "bridge_lsoa_trust": ["lsoa21_code", "trust_code"],
}


@dataclass
class ParityResult:
    table: str
    passed: bool
    details: dict = field(default_factory=dict)


def compare_fact(spark, gold_table: str, reference_parquet: str) -> ParityResult:
    from pyspark.sql import functions as F

    sp = spark.read.table(gold_table).select("lsoa21_code", "sex", "age", "eth19", "population")
    ref = spark.read.parquet(reference_parquet).select(
        "lsoa21_code", "sex", "age", "eth19", F.col("population").alias("reference")
    )
    j = sp.join(ref, ["lsoa21_code", "sex", "age", "eth19"], "full_outer")
    r = (
        j.agg(
            F.count("*").alias("rows"),
            F.count(F.when(F.col("population").isNull() | F.col("reference").isNull(), 1)).alias(
                "unmatched"
            ),
            F.max(F.abs(F.col("population") - F.col("reference"))).alias("max_abs_diff"),
            F.sum("population").alias("total"),
            F.sum("reference").alias("reference_total"),
        )
        .collect()[0]
        .asDict()
    )
    ok = r["unmatched"] == 0 and (r["max_abs_diff"] or 0) <= FACT_TOLERANCE
    return ParityResult("fact_population", ok, r)


def _text(s):
    return s.astype(object).where(s.notna(), "<null>").astype(str)


def compare_dimension(
    spark, name: str, gold_table: str, reference_parquet: str, reference_year: int | None = None
) -> ParityResult:
    import pandas as pd

    a = spark.read.table(gold_table).toPandas()
    b = pd.read_parquet(reference_parquet)  # local path or /Volumes/... (FUSE) on Databricks
    if name == "dim_lsoa" and reference_year is not None:
        a = a.rename(columns={"population_mid_year": f"population_mid{reference_year}"})
    a = a[[c for c in a.columns if not c.startswith("_")]]
    keys = KEYS[name]
    cols = sorted(set(a.columns) & set(b.columns))
    details = {
        "rows": len(a),
        "reference_rows": len(b),
        "only_gold": sorted(set(a.columns) - set(b.columns)),
        "only_reference": sorted(set(b.columns) - set(a.columns)),
        "mismatched_columns": {},
    }
    if len(a) != len(b):
        return ParityResult(name, False, details)
    a = a[cols].sort_values(keys).reset_index(drop=True)
    b = b[cols].sort_values(keys).reset_index(drop=True)
    for c in cols:
        x, y = a[c], b[c]
        numeric = pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y)
        if numeric and not pd.api.types.is_bool_dtype(x):
            d = float((x.astype(float) - y.astype(float)).abs().max())
            if not d <= 1e-6:
                details["mismatched_columns"][c] = d
        else:
            xs, ys = _text(x), _text(y)  # nulls compare equal, whether None, NaN or NA
            if (xs.values != ys.values).any():
                details["mismatched_columns"][c] = int((xs.values != ys.values).sum())
    ok = (
        not details["mismatched_columns"]
        and not details["only_gold"]
        and not details["only_reference"]
    )
    return ParityResult(name, ok, details)


def compare_all(spark, fq, reference_dir: str, reference_year: int) -> list[ParityResult]:
    """``fq(table) -> 'catalog.gold.table'``; ``reference_dir`` holds the local run's tables/."""
    ref = reference_dir.rstrip("/")
    out = [compare_fact(spark, fq("fact_population"), f"{ref}/fact_population.parquet")]
    for name in KEYS:
        out.append(
            compare_dimension(spark, name, fq(name), f"{ref}/{name}.parquet", reference_year)
        )
    return out
