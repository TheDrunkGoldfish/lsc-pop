from __future__ import annotations

import json

import pandas as pd
import pytest

from lsc_pop import provenance
from lsc_pop.provenance import (
    NOT_OFFICIAL_STATEMENT,
    RunContext,
    hash_dataframe,
    logged_step,
    read_run_log,
    write_output,
)


@pytest.fixture
def ctx(cfg) -> RunContext:
    return RunContext.create(cfg, run_id="test_run")


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "lsoa21_code": ["E01000001", "E01000001", "E01000002", "E01000002"],
            "sex": ["F", "M", "F", "M"],
            "population": [10.0, 12.0, 5.5, 4.5],
        }
    )


def _log(ctx):
    return list(read_run_log(ctx.log_path))


def test_run_context_layout(ctx, cfg):
    assert ctx.out_dir == cfg.root / "outputs" / "test_run"
    meta = json.loads((ctx.out_dir / "metadata.json").read_text())
    assert meta["config_hash"] == cfg.config_hash()
    assert meta["statement"] == NOT_OFFICIAL_STATEMENT
    assert len(meta["code_hash"]) == 64
    assert "git_commit" in meta


def test_context_manager_records_rows_and_totals(ctx, df):
    with logged_step(ctx, "demo", params={"k": 1}) as step:
        step.input("in", df)
        out = df[df["lsoa21_code"] == "E01000001"]
        step.drop(2, "not E01000001")
        step.note("filtered")
        step.output("out", out)

    (rec,) = _log(ctx)
    assert rec["step"] == "demo" and rec["status"] == "ok"
    assert rec["params"] == {"k": 1}
    assert rec["rows_in"] == 4 and rec["rows_out"] == 2
    assert rec["inputs"][0]["population"] == {"total": 32.0, "by_sex": {"F": 15.5, "M": 16.5}}
    assert rec["outputs"][0]["population"] == {"total": 22.0, "by_sex": {"F": 10.0, "M": 12.0}}
    assert rec["rows_dropped"] == [{"rows": 2, "reason": "not E01000001"}]
    assert rec["notes"] == ["filtered"]
    assert rec["outputs"][0]["hash"] == hash_dataframe(out)


def test_decorator_form(ctx, df):
    @logged_step(ctx, "double")
    def double(step, frame):
        step.input("in", frame)
        return step.output("out", frame.assign(population=frame["population"] * 2))

    result = double(df)
    assert result["population"].sum() == 64.0
    double(df)  # reusable: each call is its own record
    recs = _log(ctx)
    assert [r["step"] for r in recs] == ["double", "double"]
    assert recs[0]["outputs"][0]["population"]["total"] == 64.0


def test_error_logged_and_reraised(ctx, df):
    with pytest.raises(ZeroDivisionError), logged_step(ctx, "boom") as step:
        step.input("in", df)
        1 / 0  # noqa: B018
    (rec,) = _log(ctx)
    assert rec["status"] == "error"
    assert "ZeroDivisionError" in rec["error"]
    assert rec["rows_in"] == 4


def test_custom_value_column(ctx):
    frame = pd.DataFrame({"sex": ["F", "M"], "count": [1.0, 2.0]})
    with logged_step(ctx, "c", value_col="count") as step:
        step.input("in", frame)
    assert _log(ctx)[0]["inputs"][0]["population"]["total"] == 3.0


def test_no_population_column(ctx):
    with logged_step(ctx, "lookup") as step:
        step.input("in", pd.DataFrame({"a": [1]}))
    assert _log(ctx)[0]["inputs"][0]["population"] is None


def test_hash_dataframe_ignores_column_order(df):
    assert hash_dataframe(df) == hash_dataframe(df[["population", "sex", "lsoa21_code"]])


def test_hash_dataframe_sensitive_to_values_and_dtype(df):
    h = hash_dataframe(df)
    assert h == hash_dataframe(df.copy())
    changed = df.copy()
    changed.loc[0, "population"] = 10.0000001
    assert hash_dataframe(changed) != h
    assert hash_dataframe(df.astype({"population": "float32"})) != h


def test_write_output_sidecar(ctx, df):
    path = write_output(
        df, ctx.out_dir / "demo", ctx, sources=[{"id": "S5", "version": "mid-2024"}], csv=True
    )
    assert path.suffix == ".parquet" and path.is_file()
    assert path.with_suffix(".csv").is_file()
    pd.testing.assert_frame_equal(pd.read_parquet(path), df)
    meta = json.loads((ctx.out_dir / "demo.metadata.json").read_text())
    for key in [
        "run_id",
        "git_commit",
        "config_hash",
        "code_hash",
        "uv_lock_hash",
        "reference_date",
        "variant",
        "sources",
        "statement",
        "docs",
        "data_hash",
    ]:
        assert key in meta, key
    assert meta["reference_date"] == "2024-06-30"
    assert meta["variant"] == "cohort"
    assert meta["sources"] == [{"id": "S5", "version": "mid-2024"}]
    assert meta["data_hash"] == hash_dataframe(df)
    assert meta["population"]["total"] == 32.0


def test_git_unavailable_is_null(tmp_path):
    info = provenance.git_info(tmp_path)  # tmp_path is not a repo
    assert info == {"git_available": False, "git_commit": None, "git_dirty": None}


def test_default_run_id_has_config_and_code_hash(cfg):
    import re

    ctx = RunContext.create(cfg)
    m = re.fullmatch(r"\d{8}T\d{6}Z_([0-9a-f]{8})_([0-9a-f]{8})", ctx.run_id)
    assert m and m.group(1) == ctx.config_hash[:8] and m.group(2) == ctx.code_hash[:8]
