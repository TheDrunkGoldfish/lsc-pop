from __future__ import annotations

from lsc_pop.config import PROJECT_ROOT
from lsc_pop.report import CLI_END, CLI_START, render_cli_reference


def test_readme_command_reference_is_current():
    """README's command reference must match the CLI. Fix: run `uv run lsc-pop docs`."""
    text = (PROJECT_ROOT / "README.md").read_text()
    current = text[text.index(CLI_START) : text.index(CLI_END) + len(CLI_END)]
    assert current == render_cli_reference(), (
        "README command reference is stale: run `lsc-pop docs`"
    )


def test_every_command_and_option_documented():
    import typer

    from lsc_pop.cli import app

    ref = render_cli_reference()
    for name, cmd in typer.main.get_command(app).commands.items():
        assert f"`lsc-pop {name}`" in ref
        for p in cmd.params:
            if p.name != "help" and p.param_type_name == "option":
                assert f"`{p.opts[0]}`" in ref, (name, p.opts)
