"""Command-line interface: ``lsc-pop run | docs | validate``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from lsc_pop.config import load_config

app = typer.Typer(
    help="Modelled LSOA population estimates (sex x age x ethnicity). Not official statistics.",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    phase: int
    implemented: bool = False


STAGES: list[Stage] = [
    Stage(
        "download",
        "Download raw sources (skips files already present) & check manifest",
        2,
        implemented=True,
    ),
    Stage(
        "geography",
        "A. LSOA geography lookup (ICB, sub-ICB, LAD, MSOA) & footprint",
        3,
        implemented=True,
    ),
    Stage("census", "B. Census 2021 tables: tidy, check, reconcile totals", 4, implemented=True),
    Stage("ipf", "C. 2021 base by iterative proportional fitting (IPF)", 5, implemented=True),
    Stage(
        "rollforward",
        "D. Roll forward to the mid-year (cohort ageing) & sensitivity",
        6,
        implemented=True,
    ),
    Stage("mid2025", "E. Provisional mid-2025 variant (disabled in config; ADR-0006)", 6),
    Stage(
        "deprivation", "F. Indices of Deprivation 2025, Core20, local quintile", 7, implemented=True
    ),
    Stage("catchments", "G. Acute trust catchments (OHID) & comparison", 7, implemented=True),
    Stage("outputs", "Write star-schema tables (Parquet + CSV) & schema.sql", 8, implemented=True),
]
STAGE_KEYS = [s.key for s in STAGES]

ConfigOpt = typer.Option(
    None,
    "--config",
    "-c",
    help="Config file (must sit in a config/ folder). Default: the repo's config/config.yaml.",
)


@app.command()
def run(
    stage: str | None = typer.Option(
        None, "--stage", "-s", help=f"Run only this stage (one of: {', '.join(STAGE_KEYS)})."
    ),
    config: Path = ConfigOpt,
) -> None:
    """Run the pipeline: every stage in order, or just one with --stage.

    Each run writes a new outputs/<run_id>/ folder (tables, run log, checks). A failed hard
    check stops the run. Stages read the previous stage's saved files, so a single stage can
    be rerun, but later stages must then be rerun too.
    """
    cfg = load_config(config)
    typer.echo(f"config: {config}  hash: {cfg.config_hash()[:12]}")
    if stage is not None and stage not in STAGE_KEYS:
        raise typer.BadParameter(f"unknown stage {stage!r}; choose from {STAGE_KEYS}")
    selected = [s for s in STAGES if stage is None or s.key == stage]
    for s in selected:
        status = "ready" if s.implemented else f"not implemented until phase {s.phase}"
        if s.key == "mid2025" and not cfg.mid2025.enabled:
            status = "disabled in config"
        typer.echo(f"  {s.key:<12} {s.title:<48} [{status}]")
    ctx = None
    for s in selected:
        if s.key == "mid2025" and not cfg.mid2025.enabled:
            typer.echo("[mid2025] skipped: mid2025.enabled is false (ADR-0006)")
            continue
        if not s.implemented:
            typer.echo(f"stopping at {s.key!r}: not implemented until phase {s.phase}", err=True)
            raise typer.Exit(code=2)
        if ctx is None:
            from lsc_pop.provenance import RunContext

            ctx = RunContext.create(cfg)
            typer.echo(f"run_id: {ctx.run_id}  ->  {ctx.out_dir}")
        typer.echo(f"[{s.key}]")
        RUNNERS[s.key](ctx)


def _run_download(ctx) -> None:
    from lsc_pop.download import download as do_download

    do_download(ctx.cfg, log=typer.echo)


def _run_geography(ctx) -> None:
    from lsc_pop import geography

    lookup = geography.run(ctx)
    typer.echo(
        f"  {len(lookup):,} LSOAs; footprint {int(lookup['in_footprint'].sum()):,}; "
        f"focus ICB {int(lookup['in_focus_icb'].sum()):,}"
    )


def _run_census(ctx) -> None:
    from lsc_pop import census

    out = census.run(ctx)
    r = out["reconciliation"]
    typer.echo(
        f"  margins reconciled to {r['source']}: total {r['target_total']:,.0f}; "
        f"fallback bands: eth {r['bands_eth_fallback']}, age {r['bands_age_fallback']}"
    )


def _run_ipf(ctx) -> None:
    from lsc_pop import base

    out = base.run(ctx)
    typer.echo(f"  IPF max iterations by band: {out['iters']}")
    v = out["validation"]
    typer.echo(
        f"  max error vs reconciled RM032 {v['max_err_vs_reconciled_rm032']:.2e}, "
        f"vs RM200 {v['max_err_vs_rm200']:.2e}"
    )


def _run_rollforward(ctx) -> None:
    from lsc_pop import rollforward

    out = rollforward.run(ctx)
    typer.echo(f"  mid-{ctx.cfg.reference_year} ({ctx.cfg.variant}) total {out['total']:,.0f}")
    typer.echo(f"  share fallback: {out['fallback']}")


def _mid_year_inputs(ctx):
    """Per-LSOA mid-year total and 5-group ethnicity from the Stage D estimates."""
    import pandas as pd

    from lsc_pop.mappings import load_ethnicity_mapping
    from lsc_pop.provenance import read_cube
    from lsc_pop.rollforward import _processed

    cube = read_cube(_processed(ctx.cfg) / "estimates")
    lsoas = cube.coords["lsoa21cd"]
    by_eth = pd.DataFrame(cube.data.sum((1, 2)), index=lsoas, columns=cube.coords["eth19"])
    eth = load_ethnicity_mapping(ctx.cfg.resolve(ctx.cfg.ethnicity.mapping_file))
    eth5 = by_eth.T.groupby(eth.set_index("code_19")["code_5"]).sum().T
    return by_eth.sum(axis=1), eth5


def _run_deprivation(ctx) -> None:
    from lsc_pop import deprivation

    pop, _ = _mid_year_inputs(ctx)
    iod = deprivation.run(ctx, pop)
    typer.echo(f"  IoD joined to {len(iod):,} LSOAs; Core20 LSOAs {int(iod['core20'].sum()):,}")


def _run_catchments(ctx) -> None:
    import pandas as pd

    from lsc_pop import catchments

    pop, eth5 = _mid_year_inputs(ctx)
    iod = pd.read_parquet(ctx.cfg.resolve(ctx.cfg.paths.interim) / "deprivation" / "iod.parquet")
    out = catchments.run(ctx, pop, eth5, iod.set_index("lsoa21cd")["imd_score"])
    t = out["totals"]
    f = t[t["trust_code"].isin(ctx.cfg.focus_trusts)]
    for r in f.itertuples():
        typer.echo(
            f"  {r.trust_code}: published {r.modelled_published:,.0f}, rescaled "
            f"{r.modelled_rescaled:,.0f}, OHID T1 (mid-2022) {r.ohid_t1_mye2022:,.0f}"
        )


def _run_outputs(ctx) -> None:
    from lsc_pop import outputs

    out = outputs.run(ctx)
    typer.echo(f"  wrote {out['tables']} ({out['rows']:,} fact rows)")


RUNNERS = {
    "download": _run_download,
    "geography": _run_geography,
    "census": _run_census,
    "ipf": _run_ipf,
    "rollforward": _run_rollforward,
    "deprivation": _run_deprivation,
    "catchments": _run_catchments,
    "outputs": _run_outputs,
}


@app.command()
def download(
    source: list[str] = typer.Option(
        None,
        "--source",
        "-s",
        help=(
            "Source id(s) from config/sources.yaml to fetch; repeat for several "
            "(-s S5 -s S7). Default: all enabled sources."
        ),
    ),
    raw_dir: Path = typer.Option(
        None,
        "--raw-dir",
        help="Put raw files here instead of data/raw/ (e.g. a /Volumes/... path).",
    ),
    manifest: Path = typer.Option(
        None,
        "--manifest",
        help="Manifest file to use (seeded from the committed data/manifest.json if missing).",
    ),
    mode: str = typer.Option(
        "download",
        "--mode",
        help="download: fetch missing files. verify: fetch nothing; check files already in place "
        "(e.g. uploaded to a Volume) against the manifest.",
    ),
    config: Path = ConfigOpt,
) -> None:
    """Download raw source files into data/raw/ and record them in data/manifest.json.

    Files already present (with a matching SHA-256 hash) are skipped. Raw files are read-only
    and never overwritten. A changed or tampered file stops with an error. With --mode verify,
    nothing is downloaded and every file must already be in place (e.g. uploaded to a Volume).
    """
    from lsc_pop.config import with_paths
    from lsc_pop.download import download as do_download
    from lsc_pop.download import seed_manifest, verify

    cfg = load_config(config)
    reference = cfg.resolve(cfg.paths.manifest)
    overrides = {k: v for k, v in (("raw", raw_dir), ("manifest", manifest)) if v is not None}
    if overrides:
        cfg = with_paths(cfg, **overrides)
        seed_manifest(cfg, reference)
    if mode not in ("download", "verify"):
        raise typer.BadParameter("--mode must be 'download' or 'verify'")
    if mode == "verify":
        verify(cfg, source_ids=source or None, log=typer.echo)
    else:
        do_download(cfg, source_ids=source or None, log=typer.echo)


@app.command()
def docs(config: Path = ConfigOpt) -> None:
    """Regenerate the generated docs and figures from the latest complete run.

    Writes docs/data_sources.md, sensitivity.md, transformations.md, validation_report.md,
    docs/figures/*.png and the command reference in README.md.
    """
    from lsc_pop.report import write_all

    cfg = load_config(config)
    for p in write_all(cfg):
        typer.echo(f"wrote {p}")


@app.command()
def validate(config: Path = ConfigOpt) -> None:
    """Summarise the checks of the latest complete run (exit code 1 if any hard check failed).

    The checks themselves run inside `lsc-pop run`; this only reports them.
    """
    import json

    from lsc_pop.report import latest_complete_run

    cfg = load_config(config)
    run_dir = latest_complete_run(cfg)
    if run_dir is None:
        typer.echo("no complete run found; run `lsc-pop run` first", err=True)
        raise typer.Exit(code=2)
    recs = [json.loads(x) for x in (run_dir / "validation.jsonl").read_text().splitlines() if x]
    fails = [r for r in recs if r["hard"] and not r["passed"]]
    warns = [r for r in recs if not r["hard"] and not r["passed"]]
    typer.echo(
        f"{run_dir.name}: {len(recs)} checks, {len(fails)} hard failures, {len(warns)} warnings"
    )
    for r in fails + warns:
        typer.echo(f"  {'FAIL' if r['hard'] else 'WARN'} {r['check_id']}: {r['description']}")
    raise typer.Exit(code=1 if fails else 0)


@app.command()
def clean(
    keep: int = typer.Option(1, "--keep", "-k", help="Keep tables of the N most recent runs."),
    include_latest: bool = typer.Option(
        False, "--include-latest", help="Also remove the latest run's tables (same as --keep 0)."
    ),
    whole_runs: bool = typer.Option(
        False,
        "--whole-runs",
        help="Delete entire run directories (logs, checks too), not just tables/.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Actually delete. Without it: dry run."),
    config: Path = ConfigOpt,
) -> None:
    """Free disk space by deleting previous runs' output tables (dry run unless --yes).

    By default removes outputs/<run_id>/tables/ from every run except the latest, and keeps each
    run's small provenance files (metadata, run log, checks, hashes).
    """
    from lsc_pop.housekeeping import apply_cleanup, human, plan_cleanup

    cfg = load_config(config)
    items = plan_cleanup(cfg, keep=keep, include_latest=include_latest, whole_runs=whole_runs)
    if not items:
        typer.echo("nothing to clean")
        return
    total = sum(i.bytes for i in items)
    for i in items:
        typer.echo(f"  {i.run_id:<28} {i.reason:<20} {human(i.bytes):>10}")
    if not yes:
        typer.echo(
            f"dry run: would free {human(total)} from {len(items)} item(s). Re-run with --yes."
        )
        return
    typer.echo(f"freed {human(apply_cleanup(items))}")


@app.command("compare-runs")
def compare_runs_cmd(
    run_a: Path = typer.Argument(..., help="outputs/<run_id> directory"),
    run_b: Path = typer.Argument(
        ..., help="outputs/<run_id> directory (e.g. from a clean checkout)"
    ),
    config: Path = ConfigOpt,
) -> None:
    """Check two runs produced identical output tables (compares their data hashes).

    Exit code 0 if identical, 1 if any table differs. Writes outputs/reproducibility_check.json.
    """
    from lsc_pop.report import compare_runs

    res = compare_runs(load_config(config), run_a, run_b)
    typer.echo(f"identical: {res['identical']} ({res['tables_compared']} tables)")
    for t in res["differing_tables"]:
        typer.echo(f"  differs: {t}")
    raise typer.Exit(code=0 if res["identical"] else 1)


def task_main(argv: list[str] | None = None) -> None:
    """Entry point for Databricks Python wheel tasks (console script ``lsc-pop-task``).

    Same commands as ``lsc-pop``, but it returns normally on success: Databricks treats any
    ``SystemExit`` (even code 0, which Typer always raises) as a failed task.
    """
    try:
        app(args=argv)
    except SystemExit as e:
        if e.code not in (0, None):
            raise RuntimeError(f"lsc-pop exited with code {e.code}") from None


if __name__ == "__main__":
    app()
