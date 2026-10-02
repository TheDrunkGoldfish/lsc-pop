"""Helpers for the lsc-pop Lakeflow Declarative Pipeline (Databricks implementation, ADR-0022).

Pure ``(spark, names, cfg) -> DataFrame`` functions. The pipeline files in ``../transformations``
wrap them with ``pyspark.pipelines`` decorators, and the tests in ``databricks/tests`` call them
directly (via a local harness), so the same code runs on Databricks and in local Spark.
"""
