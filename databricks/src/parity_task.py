"""Databricks job task: compare gold tables with a local reference run (ADR-0024).

Upload the ``tables/`` folder of a local run first, e.g.::

    databricks fs cp -r outputs/<run_id>/tables dbfs:/Volumes/<catalog>/<schema>/<volume>/reference

Arguments: --catalog, --schema-gold, --reference-dir, --reference-year. Exits non-zero if any
table fails parity. Results are printed and written to ``<catalog>.<schema-audit>.parity``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))

from lsc_pop_dbx.parity import compare_all  # noqa: E402
from pyspark.sql import SparkSession  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema-gold", required=True)
    p.add_argument("--schema-audit", required=True)
    p.add_argument("--reference-dir", required=True)
    p.add_argument("--reference-year", type=int, required=True)
    a = p.parse_args()
    spark = SparkSession.builder.getOrCreate()
    results = compare_all(
        spark, lambda t: f"{a.catalog}.{a.schema_gold}.{t}", a.reference_dir, a.reference_year
    )
    rows = [(r.table, r.passed, json.dumps(r.details, default=str)) for r in results]
    for r in rows:
        print(("PASS " if r[1] else "FAIL ") + r[0] + " " + r[2])
    (
        spark.createDataFrame(rows, "table string, passed boolean, details string")
        .write.mode("overwrite")
        .saveAsTable(f"{a.catalog}.{a.schema_audit}.parity")
    )
    if not all(r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
