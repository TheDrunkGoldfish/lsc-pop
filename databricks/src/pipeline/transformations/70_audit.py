"""Audit: source manifest and run metadata (lsc_pop_dbx).

The OHID comparisons need several finished tables in pandas, so they run in the ``audit`` job
task after the pipeline (``databricks/src/audit_task.py``), not as pipeline datasets.
"""

from lsc_pop_dbx import bronze as B
from lsc_pop_dbx.params import names_from_conf
from pyspark import pipelines as dp
from pyspark.sql import functions as F

n = names_from_conf(spark)  # noqa: F821


@dp.materialized_view(
    name=n.fq("audit", "source_manifest"),
    comment="Raw files used (URL, release, SHA-256) as verified by the ingest task.",
)
def source_manifest():
    return B.source_manifest(spark, n)  # noqa: F821


@dp.materialized_view(
    name=n.fq("audit", "run_metadata"),
    comment="Provenance of this pipeline update: config/code hashes, git commit, bundle target, time.",
)
def run_metadata():
    p = spark.read.table(n.fq("silver", "params"))  # noqa: F821
    return p.select(
        "reference_year",
        "variant",
        "config_hash",
        "code_hash",
        "git_commit",
        "bundle_target",
        F.current_timestamp().alias("refreshed_at"),
        F.lit(spark.conf.get("pipelines.id", "")).alias("pipeline_id"),  # noqa: F821
        F.lit("Modelled estimates - not official statistics.").alias("statement"),
    )
