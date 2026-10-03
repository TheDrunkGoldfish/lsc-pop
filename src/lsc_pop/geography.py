"""Stage A - Geography.

Builds one England-wide LSOA 2021 lookup, ``data/interim/geography/lsoa_lookup.parquet``, with one
row per LSOA:

* current NHS/admin geography from the ``nhs`` lookup (S7): sub-ICB, ICB, NHS region, LAD;
* Census-era geography from the ``census`` lookup (S7b): MSOA 2021 (for OHID catchments) and
  LTLA 2021 (for the IPF seed), plus ONS region of the LTLA (S7c);
* flags: ``in_footprint`` (config ``footprint``; ADR-0002) and ``in_focus_icb`` (L&SC).

Which raw files and columns are used is set by ``config.geography`` (ADR-0014), so a new lookup
vintage needs no code change (see docs/updating.md). Hard checks (brief §10) stop the run.
"""

from __future__ import annotations

import pandas as pd

from lsc_pop.config import Config, LookupSpec
from lsc_pop.download import raw_file
from lsc_pop.provenance import RunContext, logged_step, write_output
from lsc_pop.validate import check

STAGE = "geography"
LOOKUP_PATH = "geography/lsoa_lookup"

OUTPUT_COLUMNS = [
    "lsoa21_code",
    "lsoa21_name",
    "msoa21_code",
    "msoa21_name",
    "ltla21_code",
    "ltla21_name",
    "rgn21_code",
    "rgn21_name",
    "lad_code",
    "lad_name",
    "sicbl_code",
    "sicbl_ods_code",
    "sicbl_name",
    "icb_code",
    "icb_ods_code",
    "icb_name",
    "nhser_code",
    "nhser_ods_code",
    "nhser_name",
    "nhs_geog_vintage",
    "in_footprint",
    "in_focus_icb",
]


def read_lookup(ctx: RunContext, name: str, spec: LookupSpec) -> pd.DataFrame:
    """Read a raw lookup CSV, keep and rename the configured columns, drop exact duplicates."""
    with logged_step(ctx, f"geography.read_{name}", params=spec.model_dump()) as step:
        path, entry = raw_file(ctx.cfg, spec.source, spec.file)
        raw = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
        step.input_file(f"{spec.source}/{spec.file}", path, entry["sha256"], rows=len(raw))
        missing = set(spec.columns) - set(raw.columns)
        if missing:
            raise KeyError(
                f"{spec.source}/{spec.file} lacks columns {sorted(missing)}; "
                "update config.geography to match the file"
            )
        df = raw[list(spec.columns)].rename(columns=spec.columns)
        before = len(df)
        df = df.drop_duplicates()
        if len(df) < before:
            step.drop(
                before - len(df), "exact duplicate rows after column selection (e.g. OA rows)"
            )
        if spec.key == "lsoa21_code":
            n_w = int((~df["lsoa21_code"].str.startswith("E")).sum())
            if n_w:
                df = df[df["lsoa21_code"].str.startswith("E")]
                step.drop(n_w, "non-England LSOAs")
        dup = df[spec.key].duplicated(keep=False)
        if dup.any():
            raise ValueError(
                f"{spec.source}: {dup.sum()} rows with a non-unique {spec.key} after dedup, "
                f"e.g. {df.loc[dup, spec.key].iloc[0]}"
            )
        df = df.sort_values(spec.key).reset_index(drop=True)
        step.output(name, df)
    return df


def apply_footprint(cfg: Config, lookup: pd.DataFrame) -> pd.DataFrame:
    fp = cfg.footprint
    known = set(lookup["icb_code"])
    for label, codes in (
        ("footprint.icb_codes", fp.icb_codes),
        ("focus_icb_codes", fp.focus_icb_codes),
    ):
        unknown = sorted(set(codes) - known)
        if unknown:
            raise ValueError(f"{label} not in the {cfg.geography.nhs.vintage} lookup: {unknown}")
    if fp.extra_lsoas_from_trust_catchments:
        raise NotImplementedError(
            "footprint.extra_lsoas_from_trust_catchments is not implemented: the England-wide "
            "footprint (ADR-0002) already contains every catchment LSOA"
        )
    out = lookup.copy()
    out["in_footprint"] = True if fp.mode == "england" else out["icb_code"].isin(fp.icb_codes)
    out["in_focus_icb"] = out["icb_code"].isin(fp.focus_icb_codes)
    return out


def build_lookup(ctx: RunContext) -> pd.DataFrame:
    cfg = ctx.cfg
    g = cfg.geography
    nhs = read_lookup(ctx, "nhs", g.nhs)
    census = read_lookup(ctx, "census", g.census)
    region = read_lookup(ctx, "ltla_region", g.ltla_region)

    with logged_step(
        ctx, "geography.build_lookup", params={"footprint": cfg.footprint.model_dump()}
    ) as step:
        for name, df in (("nhs", nhs), ("census", census), ("ltla_region", region)):
            step.input(name, df)
        merged = nhs.merge(census, on="lsoa21_code", how="outer", indicator=True, validate="1:1")
        unmatched = merged[merged["_merge"] != "both"]
        check(
            ctx,
            "GEO-01",
            "NHS and Census lookups cover the same England LSOAs",
            unmatched.empty,
            stage=STAGE,
            metrics={
                "only_nhs": int((unmatched["_merge"] == "left_only").sum()),
                "only_census": int((unmatched["_merge"] == "right_only").sum()),
            },
        )
        merged = merged.drop(columns="_merge")
        merged = merged.merge(region, on="ltla21_code", how="left", validate="m:1")
        merged["nhs_geog_vintage"] = g.nhs.vintage
        lookup = apply_footprint(cfg, merged)
        lookup = lookup[OUTPUT_COLUMNS].sort_values("lsoa21_code").reset_index(drop=True)
        step.note(
            f"{len(lookup)} LSOAs; footprint {int(lookup['in_footprint'].sum())} "
            f"({cfg.footprint.mode}); focus ICB {int(lookup['in_focus_icb'].sum())}"
        )
        step.output("lsoa_lookup", lookup)

    validate_lookup(ctx, lookup)
    return lookup


def _nests(df: pd.DataFrame, child: str, parent: str) -> pd.Series:
    """Children mapping to more than one parent (empty Series if it nests)."""
    n = df.groupby(child)[parent].nunique()
    return n[n > 1]


def validate_lookup(ctx: RunContext, lookup: pd.DataFrame) -> None:
    cfg = ctx.cfg
    n, expected = len(lookup), cfg.geography.expected_lsoa_count
    check(
        ctx,
        "GEO-02",
        "England LSOA count matches expected",
        n == expected,
        stage=STAGE,
        metrics={"lsoas": n, "expected": expected},
    )
    check(
        ctx,
        "GEO-03",
        "LSOA codes unique",
        lookup["lsoa21_code"].is_unique,
        stage=STAGE,
        metrics={"duplicates": int(lookup["lsoa21_code"].duplicated().sum())},
    )
    geo_cols = [c for c in OUTPUT_COLUMNS if c not in ("in_footprint", "in_focus_icb")]
    blanks = {c: int((lookup[c].isna() | (lookup[c] == "")).sum()) for c in geo_cols}
    blanks = {c: v for c, v in blanks.items() if v}
    check(
        ctx,
        "GEO-04",
        "Every LSOA has MSOA, LTLA21, region, LAD, sub-ICB, ICB and NHS region",
        not blanks,
        stage=STAGE,
        metrics={"blank_cells": blanks},
    )
    for cid, child, parent in (
        ("GEO-05", "sicbl_code", "icb_code"),
        ("GEO-06", "icb_code", "nhser_code"),
        ("GEO-07", "msoa21_code", "ltla21_code"),
        ("GEO-08", "ltla21_code", "lad_code"),
        ("GEO-09", "ltla21_code", "rgn21_code"),
    ):
        bad = _nests(lookup, child, parent)
        check(
            ctx,
            cid,
            f"{child} nests within {parent}",
            bad.empty,
            stage=STAGE,
            metrics={"violations": int(len(bad)), "examples": bad.index[:5].tolist()},
        )
    # Informational: LADs are not required to nest within ICBs (e.g. North Yorkshire spans two).
    split = _nests(lookup, "lad_code", "icb_code")
    check(
        ctx,
        "GEO-10",
        "LADs split across ICBs (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={"lads_split": int(len(split)), "examples": split.index[:10].tolist()},
    )
    fp = lookup[lookup["in_footprint"]]
    check(
        ctx,
        "GEO-11",
        "Footprint is non-empty",
        len(fp) > 0,
        stage=STAGE,
        metrics={"footprint_lsoas": len(fp), "mode": cfg.footprint.mode},
    )
    focus = lookup[lookup["in_focus_icb"]]
    check(
        ctx,
        "GEO-12",
        "Focus ICB(s) summary (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "lsoas": len(focus),
            "sicbls": int(focus["sicbl_code"].nunique()),
            "lads": int(focus["lad_code"].nunique()),
            "ltla21s": int(focus["ltla21_code"].nunique()),
            "msoa21s": int(focus["msoa21_code"].nunique()),
        },
    )


def run(ctx: RunContext) -> pd.DataFrame:
    lookup = build_lookup(ctx)
    cfg = ctx.cfg
    g = cfg.geography
    write_output(
        lookup,
        cfg.resolve(cfg.paths.interim) / LOOKUP_PATH,
        ctx,
        sources=[
            {"id": spec.source, "file": spec.file, "vintage": spec.vintage}
            for spec in (g.nhs, g.census, g.ltla_region)
        ],
        csv=True,
        description="England LSOA 2021 geography lookup with footprint flags (Stage A).",
    )
    return lookup


def load_lookup(cfg: Config, footprint_only: bool = False) -> pd.DataFrame:
    """Read the Stage A output (downstream stages)."""
    df = pd.read_parquet(cfg.resolve(cfg.paths.interim) / f"{LOOKUP_PATH}.parquet")
    return df[df["in_footprint"]].reset_index(drop=True) if footprint_only else df
