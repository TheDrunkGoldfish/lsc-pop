"""Databricks job task after the pipeline: OHID trust comparisons -> audit schema.

Uses the pipeline's configuration keys as arguments. It calls ``lsc_pop.catchments`` unchanged, via
``lsc_pop_dbx.audit``, and writes ``audit.ohid_comparison_*`` (totals, ethnicity, imd,
ethnicity_diagnostic) and ``audit.ohid_checks`` (CAT-07 to CAT-11). Fails if a hard check fails.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))

from lsc_pop_dbx.audit import write_ohid_tables  # noqa: E402
from lsc_pop_dbx.params import Names  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    for layer in ("bronze", "silver", "gold", "audit"):
        p.add_argument(f"--schema-{layer}", required=True)
    p.add_argument("--raw-dir", required=True)
    a = p.parse_args()
    n = Names(
        catalog=a.catalog,
        schemas={k: getattr(a, f"schema_{k}") for k in ("bronze", "silver", "gold", "audit")},
        raw_dir=a.raw_dir,
        manifest_path="",
        bundle_target="",
        git_commit="",
        local=False,
    )
    spark = SparkSession.builder.getOrCreate()
    print("written:", write_ohid_tables(spark, n))


if __name__ == "__main__":
    main()
