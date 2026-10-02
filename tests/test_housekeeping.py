from __future__ import annotations

from typer.testing import CliRunner

from lsc_pop.cli import app
from lsc_pop.housekeeping import apply_cleanup, plan_cleanup


def _runs(root, names_with_tables, names_without=()):
    out = root / "outputs"
    for n in names_with_tables:
        (out / n / "tables").mkdir(parents=True)
        (out / n / "tables" / "fact.parquet").write_bytes(b"x" * 100)
        (out / n / "run_log.jsonl").write_text("{}\n")
    for n in names_without:
        (out / n).mkdir(parents=True)
        (out / n / "run_log.jsonl").write_text("{}\n")
    return out


RUNS = ["20260101T000000Z_aaaaaaaa", "20260102T000000Z_aaaaaaaa", "20260103T000000Z_bbbbbbbb"]


def test_default_keeps_latest_tables_and_all_logs(cfg):
    out = _runs(cfg.root, RUNS, ["20260102T120000Z_aaaaaaaa"])
    items = plan_cleanup(cfg)
    assert [i.run_id for i in items] == RUNS[:2]
    assert all(i.path.name == "tables" and i.bytes == 100 for i in items)
    assert apply_cleanup(items) == 200
    assert not (out / RUNS[0] / "tables").exists()
    assert (out / RUNS[0] / "run_log.jsonl").exists()  # provenance kept
    assert (out / RUNS[2] / "tables" / "fact.parquet").exists()  # latest kept


def test_keep_n_and_include_latest(cfg):
    _runs(cfg.root, RUNS)
    assert [i.run_id for i in plan_cleanup(cfg, keep=2)] == RUNS[:1]
    assert [i.run_id for i in plan_cleanup(cfg, include_latest=True)] == RUNS


def test_whole_runs_spares_kept_runs(cfg):
    out = _runs(cfg.root, RUNS, ["20260102T120000Z_aaaaaaaa"])
    items = plan_cleanup(cfg, whole_runs=True)
    assert {i.run_id for i in items} == {RUNS[0], RUNS[1], "20260102T120000Z_aaaaaaaa"}
    apply_cleanup(items)
    assert [p.name for p in out.iterdir()] == [RUNS[2]]


def test_cli_dry_run_deletes_nothing(cfg, project_copy):
    out = _runs(cfg.root, RUNS)
    cfg_path = str(project_copy / "config" / "config.yaml")
    r = CliRunner().invoke(app, ["clean", "--config", cfg_path])
    assert r.exit_code == 0 and "dry run" in r.output
    assert all((out / n / "tables").exists() for n in RUNS)
    r = CliRunner().invoke(app, ["clean", "--yes", "--config", cfg_path])
    assert "freed" in r.output and not (out / RUNS[0] / "tables").exists()


def test_no_outputs_dir(cfg):
    assert plan_cleanup(cfg) == []
