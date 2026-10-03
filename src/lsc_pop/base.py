"""Stage C - 2021 base cube: LSOA × sex × single year of age × ethnic group (Census day 2021).

1. **Seed** (ADR-0011): an LTLA 2021 × sex × ethnic group × single-year count array from S3.
   * 301 LTLAs: single year of age as published (``age91``);
   * 7 LTLAs blocked at single year: their own 23-category counts, each category split into single
     years using the region's single-year shape for the same ethnic group × sex
     (``age23_region_split``);
   * Isles of Scilly: blocked at all fine ages; borrows Cornwall's seed (``substitute:<code>``,
     ``config.ipf.seed_substitutes``).
   ``config.ipf.seed_floor`` is then added to every cell (ADR-0016).
2. **Fit** (ADR-0003): for each RM032 band, one IPF table per LSOA × sex (ethnic groups × the
   band's single years) with the reconciled Stage B margins, all fitted in one batch.
3. **Validate**: margins reproduced (BAS-01/02), totals (BAS-03), comparison with raw RM032 and
   TS021 (BAS-04/05) and with the LTLA seed (BAS-06), non-negative/finite (BAS-07).

Output: ``data/interim/base2021/base`` (dense cube, dims lsoa21_code × sex × age × eth19), plus
``seed`` and ``seed_source`` tables.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from lsc_pop.census import _dist, _interim
from lsc_pop.config import Config
from lsc_pop.ipf import ipf_fit
from lsc_pop.mappings import age_to_code, load_census_age_classifications
from lsc_pop.provenance import Cube, RunContext, logged_step, read_cube, write_cube, write_output
from lsc_pop.validate import check

STAGE = "base"
OUT_DIR = "base2021"
SEXES = ["F", "M"]
ETH = list(range(1, 20))
DIMS = ("lsoa21_code", "sex", "age", "eth19")


def _out(cfg: Config, name: str):
    return cfg.resolve(cfg.paths.interim) / OUT_DIR / name


def _classes(cfg: Config) -> pd.DataFrame:
    return load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )


# --------------------------------------------------------------------------------------------
# Seed
# --------------------------------------------------------------------------------------------


def seed_array(
    cfg: Config,
    seed91: pd.DataFrame,
    seed23: pd.DataFrame,
    blocked: pd.DataFrame,
    lookup: pd.DataFrame,
    note=lambda text: None,
) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    """Pure seed construction (ADR-0011): (seed[ltla, sex, eth, age] without floor, ltlas, sources).

    Shared by the local stage (``build_seed``) and the Databricks pipeline.
    """
    n_age = cfg.age.max_age + 1
    ltlas = sorted(lookup["ltla21_code"].unique())
    li = {c: i for i, c in enumerate(ltlas)}
    si = {s: i for i, s in enumerate(SEXES)}
    seed = np.full((len(ltlas), 2, len(ETH), n_age), np.nan)
    source = {}
    idx = (
        seed91["ltla21_code"].map(li).to_numpy(),
        seed91["sex"].map(si).to_numpy(),
        seed91["eth19"].to_numpy() - 1,
        seed91["age"].to_numpy(),
    )
    seed[idx] = seed91["population"].to_numpy(float)
    for c in seed91["ltla21_code"].unique():
        source[c] = "age91"

    blocked91 = set(blocked.loc[blocked["classification"] == "age_91a", "ltla21_code"])
    blocked23 = set(blocked.loc[blocked["classification"] == "age_23a", "ltla21_code"])
    region = lookup.drop_duplicates("ltla21_code").set_index("ltla21_code")["rgn21_code"]
    a2k = age_to_code(_classes(cfg), "age_23a", cfg.age.max_age).to_numpy()

    for c in sorted(blocked91 - blocked23):
        rg = region[c]
        peers = [li[p] for p in region.index[region == rg] if source.get(p) == "age91"]
        shape = seed[peers].sum(0)  # (sex, eth, age) regional single-year counts
        k_tot = np.zeros(shape.shape[:2] + (a2k.max() + 1,))
        np.add.at(k_tot, (slice(None), slice(None), a2k), shape)
        denom = k_tot[:, :, a2k]
        width = np.bincount(a2k)[a2k]
        within = np.where(denom > 0, shape / np.where(denom > 0, denom, 1), 1.0 / width)
        own = seed23[seed23["ltla21_code"] == c]
        c23 = np.zeros((2, len(ETH), a2k.max() + 1))
        c23[own["sex"].map(si), own["eth19"] - 1, own["age23"]] = own["population"]
        seed[li[c]] = c23[:, :, a2k] * within
        source[c] = "age23_region_split"
        note(f"{c}: 23-category counts split by region {rg} single-year shape")

    for c in sorted(blocked91 & blocked23):
        sub = cfg.ipf.seed_substitutes.get(c)
        if sub is None or source.get(sub) is None:
            raise ValueError(f"LTLA {c} is blocked at all fine ages; set ipf.seed_substitutes")
        seed[li[c]] = seed[li[sub]]
        source[c] = f"substitute:{sub}"
        note(f"{c}: blocked at 91a and 23a; uses seed of {sub}")

    missing = [c for c in ltlas if c not in source]
    if missing or np.isnan(seed).any():
        raise ValueError(f"seed incomplete for LTLAs {missing[:5]}")
    src = pd.DataFrame({"ltla21_code": ltlas, "seed_source": [source[c] for c in ltlas]})
    return seed, ltlas, src


def build_seed(
    ctx: RunContext,
    seed91: pd.DataFrame,
    seed23: pd.DataFrame,
    blocked: pd.DataFrame,
    lookup: pd.DataFrame,
) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    """Logged wrapper around :func:`seed_array` (local pipeline)."""
    cfg = ctx.cfg
    with logged_step(ctx, "base.build_seed", params=cfg.ipf.model_dump()) as step:
        step.input("seed_age91", seed91)
        step.input("seed_age23", seed23)
        seed, ltlas, src = seed_array(cfg, seed91, seed23, blocked, lookup, note=step.note)
        step.note(json.dumps(src["seed_source"].str.split(":").str[0].value_counts().to_dict()))
        step.output_cube(
            "seed",
            Cube(
                seed,
                ("ltla21_code", "sex", "eth19", "age"),
                {
                    "ltla21_code": ltlas,
                    "sex": SEXES,
                    "eth19": ETH,
                    "age": list(range(cfg.age.max_age + 1)),
                },
            ),
        )
    return seed, ltlas, src


# --------------------------------------------------------------------------------------------
# Fit
# --------------------------------------------------------------------------------------------


def margin_arrays(cfg: Config, margins: pd.DataFrame, lsoas: list[str]):
    """Reconciled margins as arrays: eth (L, 2, 5, 19) and age (L, 2, A)."""
    n_age = cfg.age.max_age + 1
    li = pd.Index(lsoas)
    si = {s: i for i, s in enumerate(SEXES)}
    e = margins[margins["kind"] == "eth19"]
    a = margins[margins["kind"] == "age"]
    eth = np.zeros((len(lsoas), 2, 5, len(ETH)))
    eth[li.get_indexer(e["lsoa21_code"]), e["sex"].map(si), e["band"] - 1, e["key"] - 1] = e[
        "population"
    ]
    age = np.zeros((len(lsoas), 2, n_age))
    age[li.get_indexer(a["lsoa21_code"]), a["sex"].map(si), a["key"]] = a["population"]
    return eth, age


def fit_arrays(
    cfg: Config,
    seed: np.ndarray,
    ltla_of_lsoa: np.ndarray,
    eth_m: np.ndarray,
    age_m: np.ndarray,
    floor: float,
) -> tuple[np.ndarray, dict]:
    """Pure IPF of every LSOA × sex × band (ADR-0003). Returns base[l, s, age, eth], diagnostics.

    Tables are independent, so any subset of LSOAs (e.g. one LTLA on a Spark worker) can be
    fitted separately and gives the same result to within the IPF tolerance.
    """
    n_l = eth_m.shape[0]
    a2b = age_to_code(_classes(cfg), "rm032_5", cfg.age.max_age).to_numpy()
    base = np.zeros((n_l, 2, cfg.age.max_age + 1, len(ETH)))
    diag = {}
    for b in range(1, 6):
        ages = np.flatnonzero(a2b == b)
        s = seed[:, :, :, ages][ltla_of_lsoa] + floor  # (L, 2, E, nb)
        n = n_l * 2
        res = ipf_fit(
            s.reshape(n, len(ETH), len(ages)),
            eth_m[:, :, b - 1, :].reshape(n, len(ETH)),
            age_m[:, :, ages].reshape(n, len(ages)),
            tol=cfg.ipf.tolerance,
            max_iter=cfg.ipf.max_iter,
        )
        base[:, :, ages, :] = res.x.reshape(n_l, 2, len(ETH), len(ages)).transpose(0, 1, 3, 2)
        diag[b] = {
            "tables": n,
            "iter_p50": float(np.median(res.iterations)),
            "iter_p95": float(np.percentile(res.iterations, 95)),
            "iter_max": int(res.n_iter),
            "max_row_error": float(res.max_row_error.max()),
            "max_col_error": float(res.max_col_error.max()),
        }
    return base, diag


def fit_base(
    ctx: RunContext,
    seed: np.ndarray,
    ltla_of_lsoa: np.ndarray,
    eth_m: np.ndarray,
    age_m: np.ndarray,
    floor: float,
    label: str = "base.fit",
) -> tuple[np.ndarray, dict]:
    """Logged wrapper around :func:`fit_arrays` (local pipeline)."""
    cfg = ctx.cfg
    with logged_step(ctx, label, params={"seed_floor": floor, "tol": cfg.ipf.tolerance}) as step:
        base, diag = fit_arrays(cfg, seed, ltla_of_lsoa, eth_m, age_m, floor)
        for b, d in diag.items():
            step.note(f"band {b}: {json.dumps(d)}")
    return base, diag


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------


def validate_base(ctx, base, eth_m, age_m, rm032, ts021, seed91, lookup, lsoas) -> dict:
    cfg = ctx.cfg
    tol = cfg.ipf.tolerance
    a2b = age_to_code(_classes(cfg), "rm032_5", cfg.age.max_age).to_numpy()
    by_band = np.stack([base[:, :, a2b == b, :].sum(2) for b in range(1, 6)], axis=2)
    e_err = float(np.abs(by_band - eth_m).max())
    a_err = float(np.abs(base.sum(3) - age_m).max())
    out = {"max_err_vs_reconciled_rm032": e_err, "max_err_vs_rm200": a_err}
    check(
        ctx,
        "BAS-01",
        "Base reproduces reconciled RM032 (eth × sex × band) within IPF tolerance",
        e_err < tol * 10,
        stage=STAGE,
        tolerance=tol * 10,
        metrics={"max_abs": e_err},
    )
    check(
        ctx,
        "BAS-02",
        "Base reproduces RM200 (sex × single year) within IPF tolerance",
        a_err < tol * 10,
        stage=STAGE,
        tolerance=tol * 10,
        metrics={"max_abs": a_err},
    )
    total = float(base.sum())
    check(
        ctx,
        "BAS-03",
        "Base total = reconciled margin total (RM200)",
        abs(total - float(age_m.sum())) < 1e-3,
        stage=STAGE,
        metrics={"base_total": total, "rm200_total": float(age_m.sum())},
    )
    check(
        ctx,
        "BAS-07",
        "Base non-negative and finite",
        bool(np.isfinite(base).all() and (base >= 0).all()),
        stage=STAGE,
    )

    li = pd.Index(lsoas)
    si = {s: i for i, s in enumerate(SEXES)}
    raw = np.zeros_like(eth_m)
    raw[
        li.get_indexer(rm032["lsoa21_code"]),
        rm032["sex"].map(si),
        rm032["band"] - 1,
        rm032["eth19"] - 1,
    ] = rm032["population"]
    out["vs_raw_rm032_lsoa_sex_band_eth"] = _dist(pd.Series((by_band - raw).ravel()))
    ts = np.zeros((len(lsoas), len(ETH)))
    ts[li.get_indexer(ts021["lsoa21_code"]), ts021["eth19"] - 1] = ts021["population"]
    out["vs_ts021_lsoa_eth"] = _dist(pd.Series((base.sum((1, 2)) - ts).ravel()))
    eth_tot = base.sum((0, 1, 2))
    ts_tot = ts.sum(0)
    out["vs_ts021_england_eth"] = {
        int(e): {"base": round(float(b), 1), "ts021": float(t), "diff": round(float(b - t), 1)}
        for e, b, t in zip(ETH, eth_tot, ts_tot, strict=True)
    }
    check(
        ctx,
        "BAS-04",
        "Base vs raw RM032 (differences = reconciliation; informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics=out["vs_raw_rm032_lsoa_sex_band_eth"],
    )
    check(
        ctx,
        "BAS-05",
        "Base vs TS021 ethnic totals (perturbation differences; informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={"lsoa_eth": out["vs_ts021_lsoa_eth"], "england_eth": out["vs_ts021_england_eth"]},
    )

    # LTLA aggregate vs S3 seed at LTLA × sex × eth × single year (returned LTLAs only).
    comp = ltla_comparison(base, lookup, lsoas, seed91)
    out["vs_seed_ltla_sex_eth_age"] = _dist(comp["base"] - comp["seed"], comp["seed"])
    foc = set(lookup.loc[lookup["in_focus_icb"], "ltla21_code"])
    fc = comp[comp["ltla21_code"].isin(foc)]
    out["vs_seed_focus_ltla_sex_eth_age"] = _dist(fc["base"] - fc["seed"], fc["seed"])
    check(
        ctx,
        "BAS-06",
        "Base aggregated to LTLA vs S3 eth × sex × single year (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "all": out["vs_seed_ltla_sex_eth_age"],
            "focus": out["vs_seed_focus_ltla_sex_eth_age"],
        },
    )
    return out | {"ltla_comparison": comp}


def ltla_comparison(base, lookup, lsoas, seed91) -> pd.DataFrame:
    lk = lookup.set_index("lsoa21_code").loc[lsoas, "ltla21_code"].to_numpy()
    codes, inv = np.unique(lk, return_inverse=True)
    agg = np.zeros((len(codes),) + base.shape[1:])
    np.add.at(agg, inv, base)
    si = {s: i for i, s in enumerate(SEXES)}
    ci = pd.Index(codes)
    s = seed91
    vals = agg[ci.get_indexer(s["ltla21_code"]), s["sex"].map(si), s["age"], s["eth19"] - 1]
    return s.assign(base=vals).rename(columns={"population": "seed"})


# --------------------------------------------------------------------------------------------
# Sensitivity (focus ICB): seed floor and uniform seed
# --------------------------------------------------------------------------------------------


def floor_sensitivity(ctx, seed, ltla_of_lsoa, eth_m, age_m, lookup, lsoas, seed91) -> pd.DataFrame:
    """Refit the focus-ICB LSOAs with each floor (and a uniform seed); compare with S3 at LTLA."""
    cfg = ctx.cfg
    focus = lookup.set_index("lsoa21_code").loc[lsoas, "in_focus_icb"].to_numpy()
    idx = np.flatnonzero(focus)
    sub_l = [lsoas[i] for i in idx]
    rows, fits = [], {}
    variants = [(f"floor={f:g}", seed, f) for f in cfg.ipf.sensitivity_floors]
    variants.append(("uniform seed", np.zeros_like(seed), 1.0))
    for name, sd, fl in variants:
        b, _ = fit_base(
            ctx,
            sd,
            ltla_of_lsoa[idx],
            eth_m[idx],
            age_m[idx],
            fl,
            label=f"base.sensitivity[{name}]",
        )
        fits[name] = b
        comp = ltla_comparison(b, lookup, sub_l, seed91)
        comp = comp[
            comp["ltla21_code"].isin(set(lookup.loc[lookup["in_focus_icb"], "ltla21_code"]))
        ]
        d = comp["base"] - comp["seed"]
        rows.append(
            {
                "variant": name,
                "mae_vs_seed_ltla_cell": float(d.abs().mean()),
                "rmse_vs_seed_ltla_cell": float(np.sqrt((d**2).mean())),
            }
        )
    ref = (
        fits[f"floor={cfg.ipf.seed_floor:g}"]
        if cfg.ipf.seed_floor in cfg.ipf.sensitivity_floors
        else None
    )
    for r in rows:
        if ref is not None:
            diff = np.abs(fits[r["variant"]] - ref)
            r["max_abs_cell_diff_vs_default"] = float(diff.max())
            r["total_abs_diff_vs_default"] = float(diff.sum())
            sh = lambda x: x / np.where(x.sum(3, keepdims=True) > 0, x.sum(3, keepdims=True), 1)  # noqa: E731
            r["max_share_diff_vs_default"] = float(np.abs(sh(fits[r["variant"]]) - sh(ref)).max())
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# Stage entry point
# --------------------------------------------------------------------------------------------


def run(ctx: RunContext) -> dict:
    from lsc_pop.geography import load_lookup

    cfg = ctx.cfg
    lookup = load_lookup(cfg)
    lsoas = lookup["lsoa21_code"].tolist()
    rd = lambda n: pd.read_parquet(_interim(cfg, n).with_suffix(".parquet"))  # noqa: E731
    seed91, seed23, blocked = rd("seed_age91"), rd("seed_age23"), rd("seed_blocked")
    margins, rm032, ts021 = rd("margins"), rd("rm032"), rd("ts021")

    seed, ltlas, seed_src = build_seed(ctx, seed91, seed23, blocked, lookup)
    ltla_of_lsoa = pd.Index(ltlas).get_indexer(lookup["ltla21_code"])
    eth_m, age_m = margin_arrays(cfg, margins, lsoas)

    base, diag = fit_base(ctx, seed, ltla_of_lsoa, eth_m, age_m, cfg.ipf.seed_floor)
    val = validate_base(ctx, base, eth_m, age_m, rm032, ts021, seed91, lookup, lsoas)
    iters = {b: d["iter_max"] for b, d in diag.items()}
    check(
        ctx,
        "BAS-08",
        "IPF converged for every table (iterations by band)",
        True,
        stage=STAGE,
        hard=False,
        metrics=diag,
    )

    sens = floor_sensitivity(ctx, seed, ltla_of_lsoa, eth_m, age_m, lookup, lsoas, seed91)
    sens.to_csv(ctx.out_dir / "sensitivity_seed_floor.csv", index=False)
    check(
        ctx,
        "BAS-09",
        "Seed-floor sensitivity, focus ICB (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={"rows": sens.to_dict("records")},
    )

    cube = Cube(
        base,
        DIMS,
        {"lsoa21_code": lsoas, "sex": SEXES, "age": list(range(cfg.age.max_age + 1)), "eth19": ETH},
    )
    with logged_step(ctx, "base.write") as step:
        step.output_cube("base2021", cube)
        write_cube(
            cube,
            _out(cfg, "base"),
            ctx,
            sources=[{"id": i} for i in ("S1", "S2", "S3")],
            description="2021 base: LSOA x sex x single year x ethnic group (IPF; Stage C)",
        )
        write_output(
            seed_src,
            _out(cfg, "seed_source"),
            ctx,
            sources=[{"id": "S3"}],
            description="Seed source per LTLA 2021 (ADR-0011)",
        )
        write_output(
            val["ltla_comparison"],
            _out(cfg, "ltla_comparison"),
            ctx,
            sources=[{"id": "S3"}],
            description="Base aggregated to LTLA vs S3 (eth x sex x single year)",
        )
    return {
        "diag": diag,
        "iters": iters,
        "validation": {k: v for k, v in val.items() if k != "ltla_comparison"},
        "sensitivity": sens,
    }


def load_base(cfg: Config) -> Cube:
    return read_cube(_out(cfg, "base"))
