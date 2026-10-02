from __future__ import annotations

from typer.testing import CliRunner

from lsc_pop.cli import STAGE_KEYS, app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("run", "docs", "validate"):
        assert cmd in result.output


def test_run_lists_stages_and_exits_pending(project_copy):
    cfg = str(project_copy / "config" / "config.yaml")
    result = runner.invoke(app, ["run", "--stage", "mid2025", "--config", cfg])
    assert result.exit_code == 0 and "skipped" in result.output
    result = runner.invoke(app, ["run", "--stage", "nope", "--config", cfg])
    assert result.exit_code != 0


def test_help_lists_all_stages():
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    for key in STAGE_KEYS:
        assert key in result.output


def test_run_unknown_stage(project_copy):
    cfg = str(project_copy / "config" / "config.yaml")
    result = runner.invoke(app, ["run", "--stage", "nope", "--config", cfg])
    assert result.exit_code != 0
