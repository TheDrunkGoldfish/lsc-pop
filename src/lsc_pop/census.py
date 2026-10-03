"""Stage B - Census ingest and harmonisation.

Tidies the Census 2021 inputs to long format with standard codes, checks their integrity, compares
them with each other, and reconciles the IPF margins.

Tidy tables (``data/interim/census/``), all England, sorted by key:

==================  ==========================================================  ===========
table               columns                                                     source
==================  ==========================================================  ===========
``rm032``           lsoa21_code, sex, band (1-5), eth19 (1-19), population          S1
``rm200``           lsoa21_code, sex, age (0-90), population                        S2
``ts021``           lsoa21_code, eth19, population                                  S4
``seed_age91``      ltla21_code, eth19, sex, age (0-90), population                 S3
``seed_age23``      ltla21_code, eth19, sex, age23 (1-23), population               S3
``seed_blocked``    ltla21_code, classification (age_91a | age_23a)                 S3
``margins``         lsoa21_code, sex, band, kind (eth19 | age), key, population     reconciled
==================  ==========================================================  ===========

``sex`` is ``"F"`` / ``"M"`` throughout (Nomis and ONS API code 1 = Female, 2 = Male).

Margin reconciliation (§5.3 of the brief; ADR-0015). IPF fits ethnic group × single year within
each LSOA × sex × RM032 band, so RM032's ethnic counts and RM200's single-year counts must agree on
the **band** total. They don't exactly, because the tables were perturbed independently. A common
band total T is chosen (``config.reconciliation.margin_source``) and both margins are scaled to it.
"""

from __future__ import annotations

import gzip
import json
import zipfile
from dataclasses import dataclass

import numpy as np
import pandas as pd

from lsc_pop.config import Config
from lsc_pop.download import raw_file
from lsc_pop.mappings import age_to_code, load_census_age_classifications, load_ethnicity_mapping
from lsc_pop.provenance import RunContext, logged_step, write_output
from lsc_pop.validate import check

STAGE = "census"
OUT_DIR = "census"
SEX = {1: "F", 2: "M"}
N_ETH = 19

RM032 = ("S1", "rm032_lsoa21_england.csv")
RM200 = ("S2", "rm200_lsoa21_england.csv")
TS021 = ("S4", "census2021-ts021.zip", "census2021-ts021-lsoa.csv")
SEED91 = ("S3", "ltla21_eth20_sex_age91.jsonl.gz", "resident_age_91a", "age_91a")
SEED23 = ("S3", "ltla21_eth20_sex_age23.jsonl.gz", "resident_age_23a", "age_23a")


def _interim(cfg: Config, name: str):
    return cfg.resolve(cfg.paths.interim) / OUT_DIR / name


def _grid_complete(df: pd.DataFrame, keys: list[str], expected: int) -> bool:
    return len(df) == expected and not df.duplicated(keys).any()


# --------------------------------------------------------------------------------------------
# Tidy loaders
# --------------------------------------------------------------------------------------------


def load_rm032(ctx: RunContext, lsoas: pd.Index) -> pd.DataFrame:
    with logged_step(ctx, "census.load_rm032") as step:
        path, entry = raw_file(ctx.cfg, *RM032)
        raw = pd.read_csv(
            path,
            usecols=["GEOGRAPHY_CODE", "C2021_ETH_20", "C2021_AGE_6", "C_SEX", "OBS_VALUE"],
            dtype={"GEOGRAPHY_CODE": str, "C2021_ETH_20": "int16", "C2021_AGE_6": "int8",
                   "C_SEX": "int8", "OBS_VALUE": "int64"},
        )  # fmt: skip
        step.input_file("S1/" + RM032[1], path, entry["sha256"], rows=len(raw))
        df = raw.rename(
            columns={"GEOGRAPHY_CODE": "lsoa21_code", "C2021_ETH_20": "eth", "C2021_AGE_6": "band",
                     "C_SEX": "sex", "OBS_VALUE": "population"}
        )  # fmt: skip
        df["sex"] = df["sex"].map(SEX)
        keys = ["lsoa21_code", "sex", "band"]
        total = df[df["eth"] == 0].set_index(keys)["population"].sort_index()
        groups = df[df["eth"] > 0]
        s19 = groups.groupby(keys)["population"].sum().sort_index()
        diff = total.sub(s19, fill_value=0)
        check(
            ctx, "CEN-01", "RM032 'Does not apply' = 0 (all-groups total = sum of 19 groups)",
            bool((diff == 0).all()), stage=STAGE,
            metrics={"cells_nonzero": int((diff != 0).sum()), "total_minus_sum": int(diff.sum())},
        )  # fmt: skip
        step.drop(len(df) - len(groups), "all-groups total rows (eth=0), used only for CEN-01")
        out = groups.rename(columns={"eth": "eth19"})[
            ["lsoa21_code", "sex", "band", "eth19", "population"]
        ]
        out = out.sort_values(["lsoa21_code", "sex", "band", "eth19"]).reset_index(drop=True)
        _coverage_checks(
            ctx,
            "CEN-02",
            "RM032",
            out,
            lsoas,
            ["lsoa21_code", "sex", "band", "eth19"],
            len(lsoas) * 2 * 5 * N_ETH,
        )
        step.output("rm032", out)
    return out


def load_rm200(ctx: RunContext, lsoas: pd.Index) -> pd.DataFrame:
    max_age = ctx.cfg.age.max_age
    with logged_step(ctx, "census.load_rm200") as step:
        path, entry = raw_file(ctx.cfg, *RM200)
        raw = pd.read_csv(
            path,
            usecols=["GEOGRAPHY_CODE", "C2021_AGE_92", "C_SEX", "OBS_VALUE"],
            dtype={"GEOGRAPHY_CODE": str, "C2021_AGE_92": "int16", "C_SEX": "int8",
                   "OBS_VALUE": "int64"},
        )  # fmt: skip
        step.input_file("S2/" + RM200[1], path, entry["sha256"], rows=len(raw))
        df = raw.rename(
            columns={"GEOGRAPHY_CODE": "lsoa21_code", "C2021_AGE_92": "code", "C_SEX": "sex",
                     "OBS_VALUE": "population"}
        )  # fmt: skip
        df["sex"] = df["sex"].map(SEX)
        keys = ["lsoa21_code", "sex"]
        total = df[df["code"] == 0].set_index(keys)["population"].sort_index()
        ages = df[df["code"] > 0].copy()
        ages["age"] = (ages["code"] - 1).astype("int16")  # Nomis code = age + 1
        if ages["age"].max() != max_age:
            raise ValueError(f"RM200 top age {ages['age'].max()} != config max_age {max_age}")
        diff = total.sub(ages.groupby(keys)["population"].sum().sort_index(), fill_value=0)
        check(
            ctx, "CEN-03", "RM200 all-ages total = sum of single years",
            bool((diff == 0).all()), stage=STAGE, metrics={"cells_nonzero": int((diff != 0).sum())},
        )  # fmt: skip
        step.drop(len(df) - len(ages), "all-ages total rows (code 0), used only for CEN-03")
        step.note("Nomis age code converted to age = code - 1 (code 91 = 90+)")
        out = ages[["lsoa21_code", "sex", "age", "population"]]
        out = out.sort_values(["lsoa21_code", "sex", "age"]).reset_index(drop=True)
        _coverage_checks(ctx, "CEN-04", "RM200", out, lsoas, ["lsoa21_code", "sex", "age"],
                         len(lsoas) * 2 * (max_age + 1))  # fmt: skip
        step.output("rm200", out)
    return out


def load_ts021(ctx: RunContext, lsoas: pd.Index) -> pd.DataFrame:
    eth = load_ethnicity_mapping(ctx.cfg.resolve(ctx.cfg.ethnicity.mapping_file))
    with logged_step(ctx, "census.load_ts021") as step:
        path, entry = raw_file(ctx.cfg, TS021[0], TS021[1])
        with zipfile.ZipFile(path) as z:
            raw = pd.read_csv(z.open(TS021[2]))
        step.input_file(f"S4/{TS021[1]}!{TS021[2]}", path, entry["sha256"], rows=len(raw))
        raw = raw[raw["geography code"].str.startswith("E")]
        cols = {f"Ethnic group: {r.label_19}": r.code_19 for r in eth.itertuples()}
        missing = set(cols) - set(raw.columns)
        if missing:
            raise KeyError(f"TS021 lacks expected columns: {sorted(missing)}")
        wide = raw.set_index("geography code")[list(cols)].rename(columns=cols)
        total = raw.set_index("geography code")["Ethnic group: Total: All usual residents"]
        diff = total - wide.sum(axis=1)
        check(
            ctx, "CEN-05", "TS021 total = sum of 19 groups", bool((diff == 0).all()), stage=STAGE,
            metrics={"lsoas_nonzero": int((diff != 0).sum())},
        )  # fmt: skip
        out = (
            wide.rename_axis("lsoa21_code").rename_axis(columns="eth19").stack()
            .rename("population").reset_index()
        )  # fmt: skip
        out["eth19"] = out["eth19"].astype("int16")
        out["population"] = out["population"].astype("int64")
        out = out.sort_values(["lsoa21_code", "eth19"]).reset_index(drop=True)
        step.note("wide -> long by label; 5 high-level group columns ignored (derivable)")
        _coverage_checks(ctx, "CEN-06", "TS021", out, lsoas, ["lsoa21_code", "eth19"],
                         len(lsoas) * N_ETH)  # fmt: skip
        step.output("ts021", out)
    return out


def _coverage_checks(ctx, cid, name, df, lsoas, keys, expected) -> None:
    got = pd.Index(df["lsoa21_code"].unique())
    check(
        ctx, cid, f"{name} covers exactly the lookup LSOAs with a complete, unique grid",
        got.sort_values().equals(lsoas.sort_values()) and _grid_complete(df, keys, expected),
        stage=STAGE,
        metrics={"rows": len(df), "expected_rows": expected,
                 "missing_lsoas": int(len(lsoas.difference(got))),
                 "extra_lsoas": int(len(got.difference(lsoas)))},
    )  # fmt: skip
    check(
        ctx,
        f"{cid}b",
        f"{name} counts are non-negative integers",
        bool((df["population"] >= 0).all()),
        stage=STAGE,
    )


def load_seed(ctx: RunContext, which: tuple, ltlas: pd.Index) -> tuple[pd.DataFrame, list[str]]:
    """Parse an ONS-API seed file. Returns (tidy table, blocked LTLA codes)."""
    source, file, dim, classification = which
    age_col = "age" if dim == "resident_age_91a" else "age23"
    with logged_step(ctx, f"census.load_seed_{classification}") as step:
        path, entry = raw_file(ctx.cfg, source, file)
        rows, blocked, requested = [], [], []
        with gzip.open(path) as f:
            for line in f:
                rec = json.loads(line)
                requested += rec["requested"]
                blocked += rec["blocked"]
                for o in rec["response"]["observations"] or []:
                    d = {x["dimension_id"]: x["option_id"] for x in o["dimensions"]}
                    rows.append((d["ltla"], int(d["ethnic_group_tb_20b"]), int(d["sex"]),
                                 int(d[dim]), o["observation"]))  # fmt: skip
        step.input_file(f"{source}/{file}", path, entry["sha256"], rows=len(rows))
        df = pd.DataFrame(rows, columns=["ltla21_code", "eth", "sex", age_col, "population"])
        dna = df[df["eth"] == -8]
        check(
            ctx, f"CEN-07-{classification}", f"S3 {classification}: 'Does not apply' = 0",
            bool((dna["population"] == 0).all()), stage=STAGE,
            metrics={"total": int(dna["population"].sum())},
        )  # fmt: skip
        df = df[df["eth"] > 0].rename(columns={"eth": "eth19"})
        step.drop(len(dna), "'Does not apply' rows (all zero; CEN-07)")
        df["sex"] = df["sex"].map(SEX)
        df[["eth19", age_col]] = df[["eth19", age_col]].astype("int16")
        df["population"] = df["population"].astype("int64")
        df = df.sort_values(["ltla21_code", "eth19", "sex", age_col]).reset_index(drop=True)
        check(
            ctx, f"CEN-08-{classification}",
            f"S3 {classification}: requested areas = lookup LTLAs; returned + blocked = requested",
            set(requested) == set(ltlas)
            and set(df["ltla21_code"]) | set(blocked) == set(requested)
            and not set(df["ltla21_code"]) & set(blocked),
            stage=STAGE,
            metrics={"requested": len(set(requested)), "returned": int(df["ltla21_code"].nunique()),
                     "blocked": sorted(blocked)},
        )  # fmt: skip
        step.note(f"blocked LTLAs ({len(blocked)}): {', '.join(sorted(blocked))}")
        step.output(f"seed_{classification}", df)
    return df, sorted(blocked)


# --------------------------------------------------------------------------------------------
# Comparisons (informational; distributions logged)
# --------------------------------------------------------------------------------------------


def _dist(diff: pd.Series, base: pd.Series | None = None) -> dict:
    a = diff.abs()
    out = {
        "cells": int(len(diff)),
        "share_identical": round(float((diff == 0).mean()), 4),
        "mean_abs": round(float(a.mean()), 3),
        "p50_abs": float(a.quantile(0.5)),
        "p95_abs": float(a.quantile(0.95)),
        "p99_abs": float(a.quantile(0.99)),
        "max_abs": float(a.max()),
        "net": float(diff.sum()),
    }
    if base is not None:
        rel = (a / base.where(base > 0)).dropna()
        out |= {
            "p95_rel": round(float(rel.quantile(0.95)), 4),
            "max_rel": round(float(rel.max()), 4),
        }
    return out


def band_totals(cfg: Config, rm032: pd.DataFrame, rm200: pd.DataFrame) -> pd.DataFrame:
    """LSOA x sex x band totals from each table: columns t032, t200."""
    classes = load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )
    a2b = age_to_code(classes, "rm032_5", cfg.age.max_age)
    t200 = (
        rm200.assign(band=rm200["age"].map(a2b))
        .groupby(["lsoa21_code", "sex", "band"])["population"].sum().rename("t200")
    )  # fmt: skip
    t032 = rm032.groupby(["lsoa21_code", "sex", "band"])["population"].sum().rename("t032")
    return pd.concat([t032, t200], axis=1).reset_index()


def compare_tables(ctx: RunContext, rm032, rm200, ts021, seed91, lookup, focus: pd.Index) -> dict:
    """Log discrepancy distributions between independently perturbed tables (no changes made)."""
    out = {}
    with logged_step(ctx, "census.compare_tables") as step:
        bt = band_totals(ctx.cfg, rm032, rm200)
        ls = bt.groupby(["lsoa21_code", "sex"])[["t032", "t200"]].sum()
        out["rm032_vs_rm200_lsoa_sex"] = _dist(ls["t032"] - ls["t200"], ls["t200"])
        out["rm032_vs_rm200_lsoa_sex_band"] = _dist(bt["t032"] - bt["t200"], bt["t200"])
        fb = bt[bt["lsoa21_code"].isin(focus)]
        out["focus_rm032_vs_rm200_lsoa_sex_band"] = _dist(fb["t032"] - fb["t200"], fb["t200"])
        out["band_zero_inconsistency"] = {
            "rm032_zero_rm200_pos": int(((bt["t032"] == 0) & (bt["t200"] > 0)).sum()),
            "rm200_zero_rm032_pos": int(((bt["t200"] == 0) & (bt["t032"] > 0)).sum()),
            "persons_rm032_zero_rm200_pos": int(bt.loc[bt["t032"] == 0, "t200"].sum()),
            "persons_rm200_zero_rm032_pos": int(bt.loc[bt["t200"] == 0, "t032"].sum()),
        }
        e032 = rm032.groupby(["lsoa21_code", "eth19"])["population"].sum()
        e021 = ts021.set_index(["lsoa21_code", "eth19"])["population"]
        out["rm032_vs_ts021_lsoa_eth"] = _dist(e032 - e021, e021)
        out["totals"] = {
            "rm032": int(rm032["population"].sum()),
            "rm200": int(rm200["population"].sum()),
            "ts021": int(ts021["population"].sum()),
        }
        # Seed vs RM032 aggregated to LTLA x eth x sex x band (returned LTLAs only)
        classes = load_census_age_classifications(
            ctx.cfg.resolve(ctx.cfg.age.census_classifications_file), ctx.cfg.age.max_age
        )
        a2b = age_to_code(classes, "rm032_5", ctx.cfg.age.max_age)
        s = seed91.assign(band=seed91["age"].map(a2b))
        s = s.groupby(["ltla21_code", "eth19", "sex", "band"])["population"].sum()
        r = rm032.merge(lookup[["lsoa21_code", "ltla21_code"]], on="lsoa21_code")
        r = r.groupby(["ltla21_code", "eth19", "sex", "band"])["population"].sum()
        r = r.reindex(s.index)
        out["seed91_vs_rm032_ltla_eth_sex_band"] = _dist(s - r, r)
        for k, v in out.items():
            step.note(f"{k}: {json.dumps(v)}")
    check(ctx, "CEN-09", "Cross-table discrepancies (informational)", True, stage=STAGE,
          hard=False, metrics=out)  # fmt: skip
    return out


# --------------------------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------------------------


@dataclass
class Reconciled:
    margins: pd.DataFrame  # lsoa21_code, sex, band, kind, key, population (float)
    summary: dict


def reconcile_margins(
    ctx: RunContext,
    rm032: pd.DataFrame,
    rm200: pd.DataFrame,
    seed91: pd.DataFrame,
    lookup: pd.DataFrame,
    source: str | None = None,
) -> Reconciled:
    """Scale RM032 ethnic and RM200 single-year margins to a common LSOA x sex x band total.

    ``source`` picks the common total T: ``rm200`` (T = RM200 band sum), ``rm032`` (T = RM032
    band sum) or ``mean`` (average). Zero-inconsistent bands (one table zero, the other positive,
    and T > 0) are filled from a documented fallback (ADR-0015):

    * no RM032 ethnic information in the band: use the LSOA x sex ethnic mix pooled over all
      bands; if that is empty too, the LTLA seed's ethnic mix for that sex x band;
    * no RM200 age information in the band: spread T over the band's single years using the LTLA
      seed's all-ethnicity age shape for that sex.
    """
    cfg = ctx.cfg
    source = source or cfg.reconciliation.margin_source
    if source not in ("rm200", "rm032", "mean"):
        raise ValueError(f"reconciliation.margin_source must be set (got {source!r}); ADR-0015")
    classes = load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )
    a2b = age_to_code(classes, "rm032_5", cfg.age.max_age)

    with logged_step(ctx, f"census.reconcile_margins[{source}]", params={"source": source}) as step:
        step.input("rm032", rm032)
        step.input("rm200", rm200)
        bt = band_totals(cfg, rm032, rm200).set_index(["lsoa21_code", "sex", "band"])
        target = {"rm200": bt["t200"], "rm032": bt["t032"], "mean": bt.mean(axis=1)}[source]
        target = target.astype(float).rename("target")

        # --- ethnic margins
        e = rm032.set_index(["lsoa21_code", "sex", "band"]).join(bt["t032"]).join(target)
        e["population"] = e["population"].astype(float)
        has = e["t032"] > 0
        e.loc[has, "population"] = (
            e.loc[has, "population"] * e.loc[has, "target"] / e.loc[has, "t032"]
        )
        need_eth = e.index[(~has) & (e["target"] > 0)].unique()
        n_eth_fb = len(need_eth)
        if n_eth_fb:
            pooled = rm032.groupby(["lsoa21_code", "sex", "eth19"])["population"].sum()
            pooled = pooled / pooled.groupby(["lsoa21_code", "sex"]).transform("sum")
            fb = e.loc[need_eth].reset_index()
            fb = fb.merge(
                pooled.rename("share").reset_index(), on=["lsoa21_code", "sex", "eth19"], how="left"
            )
            if fb["share"].isna().any():  # LSOA x sex with no RM032 people at all: LTLA seed mix
                seed_mix = _seed_eth_mix(seed91, a2b)
                fb = fb.merge(lookup[["lsoa21_code", "ltla21_code"]], on="lsoa21_code").merge(
                    seed_mix, on=["ltla21_code", "sex", "band", "eth19"], how="left"
                )
                fb["share"] = fb["share"].fillna(fb["seed_share"])
            fb["population"] = fb["share"].fillna(0) * fb["target"]
            fb = fb.set_index(["lsoa21_code", "sex", "band", "eth19"])["population"]
            e = e.set_index("eth19", append=True)
            e.loc[fb.index, "population"] = fb
            e = e.reset_index("eth19")
        eth = e.reset_index()[["lsoa21_code", "sex", "band", "eth19", "population"]]

        # --- age margins
        a = rm200.assign(band=rm200["age"].map(a2b)).set_index(["lsoa21_code", "sex", "band"])
        a = a.join(bt["t200"]).join(target)
        a["population"] = a["population"].astype(float)
        has = a["t200"] > 0
        a.loc[has, "population"] = (
            a.loc[has, "population"] * a.loc[has, "target"] / a.loc[has, "t200"]
        )
        need_age = a.index[(~has) & (a["target"] > 0)].unique()
        n_age_fb = len(need_age)
        if n_age_fb:
            shape = _seed_age_shape(seed91, a2b)
            fb = (
                a.loc[need_age]
                .reset_index()
                .merge(lookup[["lsoa21_code", "ltla21_code"]], on="lsoa21_code")
            )
            fb = fb.merge(shape, on=["ltla21_code", "sex", "age"], how="left")
            fb["population"] = fb["shape"].fillna(0) * fb["target"]
            fb = fb.set_index(["lsoa21_code", "sex", "band", "age"])["population"]
            a = a.set_index("age", append=True)
            a.loc[fb.index, "population"] = fb
            a = a.reset_index("age")
        age = a.reset_index()[["lsoa21_code", "sex", "band", "age", "population"]]

        # --- adjustment distribution
        adj = (target - bt["t032"]).rename("adj032"), (target - bt["t200"]).rename("adj200")
        summary = {
            "source": source,
            "target_total": float(target.sum()),
            "rm032_adjustment": _dist(adj[0], bt["t032"]),
            "rm200_adjustment": _dist(adj[1], bt["t200"]),
            "bands_eth_fallback": int(n_eth_fb),
            "persons_eth_fallback": float(target.loc[need_eth].sum()) if n_eth_fb else 0.0,
            "bands_age_fallback": int(n_age_fb),
            "persons_age_fallback": float(target.loc[need_age].sum()) if n_age_fb else 0.0,
            "persons_dropped_rm032_zeroed": float(bt.loc[target == 0, "t032"].sum()),
            "persons_dropped_rm200_zeroed": float(bt.loc[target == 0, "t200"].sum()),
        }
        step.note(json.dumps(summary))

        margins = pd.concat(
            [
                eth.rename(columns={"eth19": "key"}).assign(kind="eth19"),
                age.rename(columns={"age": "key"}).assign(kind="age"),
            ],
            ignore_index=True,
        )[["lsoa21_code", "sex", "band", "kind", "key", "population"]]
        margins["key"] = margins["key"].astype("int16")
        margins = margins.sort_values(["lsoa21_code", "sex", "band", "kind", "key"]).reset_index(
            drop=True
        )
        step.output("margins", margins)

    # Both margins must now agree on every band total, exactly up to float error.
    g = margins.groupby(["lsoa21_code", "sex", "band", "kind"])["population"].sum().unstack("kind")
    gap = (g["eth19"] - g["age"]).abs().max()
    check(
        ctx,
        "CEN-10",
        "Reconciled ethnic and age margins agree on every LSOA x sex x band total",
        bool(gap < 1e-6),
        stage=STAGE,
        tolerance=1e-6,
        metrics={"max_gap": float(gap)},
    )
    check(
        ctx,
        "CEN-11",
        "Reconciled margins non-negative and finite",
        bool(np.isfinite(margins["population"]).all() and (margins["population"] >= 0).all()),
        stage=STAGE,
    )
    r = cfg.reconciliation
    adjusted = bt["t032"] if source != "rm032" else bt["t200"]
    gap = (target - adjusted).abs()
    flagged = gap > np.maximum(r.warn_abs, r.warn_rel * adjusted)
    check(
        ctx, "CEN-12",
        f"Band-total adjustment within max({r.warn_abs:g} persons, {r.warn_rel:.0%}) (soft)",
        not flagged.any(), stage=STAGE, hard=False,
        tolerance=r.warn_rel,
        metrics={"bands_flagged": int(flagged.sum()), "bands": int(len(flagged)),
                 "examples": [list(map(str, i)) for i in flagged[flagged].index[:10]],
                 **summary},
    )  # fmt: skip
    return Reconciled(margins, summary)


def _seed_eth_mix(seed91: pd.DataFrame, a2b: pd.Series) -> pd.DataFrame:
    s = seed91.assign(band=seed91["age"].map(a2b))
    s = s.groupby(["ltla21_code", "sex", "band", "eth19"])["population"].sum()
    s = s / s.groupby(["ltla21_code", "sex", "band"]).transform("sum")
    return s.rename("seed_share").reset_index()


def _seed_age_shape(seed91: pd.DataFrame, a2b: pd.Series) -> pd.DataFrame:
    s = seed91.groupby(["ltla21_code", "sex", "age"])["population"].sum().reset_index()
    s["band"] = s["age"].map(a2b)
    s["shape"] = s["population"] / s.groupby(["ltla21_code", "sex", "band"])[
        "population"
    ].transform("sum")
    return s[["ltla21_code", "sex", "age", "shape"]]


# --------------------------------------------------------------------------------------------
# Stage entry point
# --------------------------------------------------------------------------------------------


def run(ctx: RunContext) -> dict:
    from lsc_pop.geography import load_lookup

    cfg = ctx.cfg
    lookup = load_lookup(cfg)
    lsoas = pd.Index(lookup["lsoa21_code"])
    ltlas = pd.Index(lookup["ltla21_code"].unique())
    focus = pd.Index(lookup.loc[lookup["in_focus_icb"], "lsoa21_code"])

    rm032 = load_rm032(ctx, lsoas)
    rm200 = load_rm200(ctx, lsoas)
    ts021 = load_ts021(ctx, lsoas)
    seed91, blocked91 = load_seed(ctx, SEED91, ltlas)
    seed23, blocked23 = load_seed(ctx, SEED23, ltlas)
    comparison = compare_tables(ctx, rm032, rm200, ts021, seed91, lookup, focus)
    rec = reconcile_margins(ctx, rm032, rm200, seed91, lookup)

    blocked = pd.DataFrame(
        [(c, "age_91a") for c in blocked91] + [(c, "age_23a") for c in blocked23],
        columns=["ltla21_code", "classification"],
    )
    srcs = {
        "rm032": [{"id": "S1", "file": RM032[1]}],
        "rm200": [{"id": "S2", "file": RM200[1]}],
        "ts021": [{"id": "S4", "file": TS021[1]}],
        "seed_age91": [{"id": "S3", "file": SEED91[1]}],
        "seed_age23": [{"id": "S3", "file": SEED23[1]}],
        "seed_blocked": [{"id": "S3", "file": f} for f in (SEED91[1], SEED23[1])],
        "margins": [{"id": "S1", "file": RM032[1]}, {"id": "S2", "file": RM200[1]},
                    {"id": "S3", "file": SEED91[1]}],
    }  # fmt: skip
    tables = {
        "rm032": rm032, "rm200": rm200, "ts021": ts021, "seed_age91": seed91,
        "seed_age23": seed23, "seed_blocked": blocked, "margins": rec.margins,
    }  # fmt: skip
    for name, df in tables.items():
        write_output(df, _interim(cfg, name), ctx, sources=srcs[name],
                     description=f"Stage B tidy table: {name}")  # fmt: skip
    return {"comparison": comparison, "reconciliation": rec.summary}
