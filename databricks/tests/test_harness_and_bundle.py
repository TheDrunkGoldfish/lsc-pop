"""Static checks: pipeline files parse and register; the bundle YAML matches the official schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from harness import TRANSFORMATIONS, _split_statements, parse_create

ROOT = Path(__file__).resolve().parents[1]


def test_parse_create_with_constraints_and_comment():
    kind, name, exps, query = parse_create(
        "CREATE OR REFRESH PRIVATE MATERIALIZED VIEW a.b (\n"
        "  CONSTRAINT c1 EXPECT (x > 0 AND f(y, 2) = 1) ON VIOLATION FAIL UPDATE,\n"
        "  CONSTRAINT c2 EXPECT (z IS NOT NULL) ON VIOLATION DROP ROW,\n"
        "  CONSTRAINT c3 EXPECT (w <> 'a, b')\n"
        ") COMMENT 'it''s a view' AS SELECT 1 AS x"
    )
    assert kind.startswith("MATERIALIZED") and name == "a.b"
    assert exps == [
        ("c1", "x > 0 AND f(y, 2) = 1", "fail"),
        ("c2", "z IS NOT NULL", "drop"),
        ("c3", "w <> 'a, b'", "warn"),
    ]
    assert query == "SELECT 1 AS x"


def test_split_statements_ignores_semicolons_in_strings_and_comments():
    sql = "-- comment; here\nSELECT ';' AS a;\nSELECT 2;"
    assert _split_statements(sql) == ["SELECT ';' AS a", "SELECT 2"]


def test_every_sql_statement_is_supported():
    names = []
    for path in sorted(TRANSFORMATIONS.glob("*.sql")):
        for stmt in _split_statements(path.read_text()):
            if stmt.upper().startswith("USE "):
                continue
            _k, name, _e, _q = parse_create(stmt)
            names.append(name.split(".")[-1])
    assert len(names) == len(set(names)), "duplicate dataset names across SQL files"


def test_files_have_unique_numeric_prefixes():
    """The local harness runs files in name order, so prefixes encode the dependency order."""
    prefixes = [
        int(re.match(r"(\d+)_", p.name).group(1))
        for p in TRANSFORMATIONS.iterdir()
        if p.suffix in (".py", ".sql")
    ]
    assert len(prefixes) == len(set(prefixes))


def _bundle_doc() -> dict:
    doc = yaml.safe_load((ROOT / "databricks.yml").read_text())
    for f in sorted((ROOT / "resources").glob("*.yml")):
        for k, v in yaml.safe_load(f.read_text()).items():
            for kk, vv in v.items():
                doc.setdefault(k, {}).setdefault(kk, {}).update(vv)
    return doc


def test_bundle_matches_official_schema():
    jsonschema = pytest.importorskip("jsonschema")
    txt = (ROOT / "tests" / "bundle_schema.json").read_text()
    # Python's re lacks \p{..} classes used by the schema's variable-reference patterns.
    txt = txt.replace("\\\\p{L}", "[^\\\\W\\\\d_]").replace("\\\\p{N}", "\\\\d")
    errors = list(jsonschema.Draft202012Validator(json.loads(txt)).iter_errors(_bundle_doc()))
    assert not errors, [(list(e.path), e.message[:200]) for e in errors[:5]]


def test_bundle_targets_and_variables():
    doc = _bundle_doc()
    assert set(doc["targets"]) == {"dev", "test", "prod"}
    assert doc["targets"]["dev"]["mode"] == "development"
    assert doc["targets"]["prod"]["mode"] == "production"
    for v in (
        "catalog",
        "schema_bronze",
        "schema_silver",
        "schema_gold",
        "schema_audit",
        "volume_path",
    ):
        assert v in doc["variables"]
    conf = doc["resources"]["pipelines"]["lsc_pop_pipeline"]["configuration"]
    assert conf["lsc_pop.raw_dir"] == "${var.volume_path}/raw"
    used = set(
        re.findall(
            r"\$\{(lsc_pop\.[\w.]+)\}",
            "".join(p.read_text() for p in TRANSFORMATIONS.glob("*.sql")),
        )
    )
    assert used <= set(conf), (
        f"SQL uses configuration keys not set by the bundle: {used - set(conf)}"
    )


def test_harness_rejects_eager_dataset_functions(spark, tmp_path):
    """Regression: Databricks analyses datasets before upstream data exists (2026-10-02 failure)."""
    from harness import EagerDatasetError, LocalPipeline, local_conf

    f = tmp_path / "99_eager.py"
    f.write_text(
        "from pyspark import pipelines as dp\n"
        "@dp.materialized_view(name='silver.eager')\n"
        "def eager():\n"
        "    n = spark.range(3).count()\n"
        "    return spark.range(n)\n"
    )
    pl = LocalPipeline(spark, local_conf(tmp_path, tmp_path / "m.json"))
    with pytest.raises(EagerDatasetError):
        pl.run_python(f)
    f.write_text(
        "from pyspark import pipelines as dp\n"
        "@dp.materialized_view(name='silver.lazy')\n"
        "def lazy():\n"
        "    return spark.range(3)\n"
    )
    pl.run_python(f)
