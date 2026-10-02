"""End to end on synthetic raw files: local lsc-pop pipeline vs the Databricks pipeline (harness).

Both read the same synthetic sources (real formats: CSV, JSON lines, zip, xlsx, ODS). The test
asserts that every Databricks check passes and that the gold tables match the local outputs
within the ADR-0024 parity tolerances.
"""

from __future__ import annotations

import json

import pytest
from conftest import requires_spark
from harness import LocalPipeline, local_conf
from synthetic import LSOAS, make_project
from typer.testing import CliRunner

from lsc_pop.cli import app


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic")
    cfg_path = make_project(root)
    result = CliRunner().invoke(app, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    runs = sorted((root / "outputs").glob("*/"))
    return root, cfg_path, runs[-1]


def test_local_pipeline_ran_and_passed_checks(project):
    _root, _cfg, run = project
    checks = [json.loads(x) for x in (run / "validation.jsonl").read_text().splitlines()]
    assert not [c["check_id"] for c in checks if c["hard"] and not c["passed"]]
    assert (run / "tables" / "fact_population.parquet").is_file()


@requires_spark
def test_databricks_pipeline_matches_local(project, spark, monkeypatch):
    root, cfg_path, run = project
    monkeypatch.setenv("LSC_POP_CONFIG", str(cfg_path))
    from lsc_pop_dbx import params
    from lsc_pop_dbx.parity import compare_all

    params.config.cache_clear()
    pl = LocalPipeline(
        spark, local_conf(root / "data" / "raw", root / "data" / "manifest.json")
    ).run()
    failed_fail = [e for e in pl.expectations if e.action == "fail" and e.violations]
    assert not failed_fail

    from lsc_pop_dbx.audit import write_ohid_tables
    from lsc_pop_dbx.params import names_from_conf

    written = write_ohid_tables(spark, names_from_conf(spark))  # the audit job task
    assert set(written) == {"totals", "ethnicity", "imd", "ethnicity_diagnostic"}
    ohid = spark.read.table("audit.ohid_checks").toPandas()
    assert {"CAT-07", "CAT-11"} <= set(ohid.check_id) and not ohid[
        (ohid.hard) & (~ohid.passed)
    ].shape[0]

    v = spark.read.table("audit.validation").toPandas()
    hard_failures = v[(v.hard) & (~v.passed)]
    assert hard_failures.empty, hard_failures[["check_id", "metrics"]].to_dict("records")
    assert {"GEO-02", "CEN-10", "BAS-01", "ROL-05", "OUT-04", "CAT-05"} <= set(v.check_id)

    fact = spark.read.table("gold.fact_population")
    assert fact.count() == len(LSOAS) * 2 * 91 * 19

    results = compare_all(spark, lambda t: f"gold.{t}", str(run / "tables"), 2024)
    failed = [(r.table, r.details) for r in results if not r.passed]
    assert not failed, failed

    sens = spark.read.table("audit.sensitivity").toPandas()
    assert set(sens.variant) == {"cohort", "static", "cohort_newborn_0_4"}
    meta = spark.read.table("audit.run_metadata").toPandas().iloc[0]
    assert meta.config_hash == json.loads((run / "metadata.json").read_text())["config_hash"]
    params.config.cache_clear()
