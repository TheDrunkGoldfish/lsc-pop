"""Stage G - Acute trust catchments (ADR-0019) and comparison with OHID's published figures.

There are no aggregate tables (ADR-0018). This stage builds the **bridge** that lets SQL/BI
apportion LSOA populations to trusts, plus the trust dimension, and checks the result against OHID.

* ``bridge_lsoa_trust``: lsoa21_code, msoa21_code, trust_code, proportion_published,
  proportion_rescaled, fptp. Each LSOA takes its MSOA 2021's OHID proportions for the configured
  catchment year and admission type. A ``UNASSIGNED`` row per LSOA holds 1 − Σ published, so
  published proportions sum to exactly 1. Rescaled = published ÷ Σ (UNASSIGNED = 0).
* ``dim_trust``: the 134 acute trusts (OHID T7) + ``UNASSIGNED``, with ``is_focus`` and
  ``host_icb_code`` (the ICB whose geography the trust is in, from the ODS directory, S10;
  ADR-0025). That's an organisational link, separate from the catchment bridge.
* Comparators (informational, written to the run directory):
  ``trust_comparison_totals.csv`` (vs OHID T1), ``trust_comparison_ethnicity.csv`` (vs T5, both
  selection methods), ``trust_comparison_imd.csv`` (vs T6).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from lsc_pop.download import raw_file
from lsc_pop.ods import read_ods_sheets, sheet_to_frame
from lsc_pop.ods_directory import read_relationships
from lsc_pop.provenance import RunContext, logged_step, write_output
from lsc_pop.validate import check

STAGE = "catchments"
UNASSIGNED = "UNASSIGNED"
SHEETS = ["All_admissions", "Trust_analysis", "Ethnicity", "Deprivation", "Trust_area_lookup"]
OUT = "catchments"
P_COL = "Patients admitted as a proportion of total patients"
OHID_5PCT = 0.05  # OHID "All (5% and above)" selection threshold


def _norm(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower()


def load_ohid(ctx: RunContext) -> dict[str, pd.DataFrame]:
    c = ctx.cfg.catchments
    with logged_step(ctx, "catchments.load_ohid", params=c.model_dump()) as step:
        path, entry = raw_file(ctx.cfg, c.source, c.file)
        sheets = read_ods_sheets(path, SHEETS)
        frames = {k: sheet_to_frame(v, header_row=2) for k, v in sheets.items()}
        step.input_file(
            f"{c.source}/{c.file}", path, entry["sha256"], rows=sum(len(f) for f in frames.values())
        )
        year, adm = str(c.catchment_year), c.admission_type.lower()
        for k in ("All_admissions", "Trust_analysis", "Ethnicity", "Deprivation"):
            f = frames[k]
            ycol = next(col for col in f.columns if col.lower() == "catchment year")
            keep = (f[ycol].astype(str) == year) & (_norm(f["Admission type"]) == adm)
            frames[k] = f[keep].reset_index(drop=True)
            step.note(f"{k}: {int(keep.sum())} rows for {year} / {c.admission_type}")
    return frames


def build_bridge(ctx: RunContext, t2: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    with logged_step(ctx, "catchments.build_bridge") as step:
        prop = pd.DataFrame(
            {
                "trust_code": t2["Trust code"].astype(str),
                "msoa21_code": t2["MSOA21CD"].astype(str),
                "proportion_published": t2[P_COL].astype(float),
                "fptp": _norm(t2["First past the post (FPTP)"]).isin(["true", "1"]),
            }
        )
        step.input("ohid_t2", prop)
        msoas = set(lookup["msoa21_code"])
        check(
            ctx,
            "CAT-01",
            "OHID MSOAs = lookup MSOAs (MSOA 2021, England)",
            set(prop["msoa21_code"]) == msoas,
            stage=STAGE,
            metrics={
                "ohid": prop["msoa21_code"].nunique(),
                "lookup": len(msoas),
                "missing": len(msoas - set(prop["msoa21_code"])),
            },
        )
        check(
            ctx,
            "CAT-02",
            "One OHID row per MSOA x trust",
            not prop.duplicated(["msoa21_code", "trust_code"]).any(),
            stage=STAGE,
        )
        msum = prop.groupby("msoa21_code")["proportion_published"].sum()
        check(
            ctx,
            "CAT-03",
            "Published proportions per MSOA sum to <= 1",
            bool((msum <= 1 + 1e-9).all()),
            stage=STAGE,
            metrics={
                "min": float(msum.min()),
                "mean": float(msum.mean()),
                "max": float(msum.max()),
            },
        )
        fp = prop.groupby("msoa21_code")["fptp"].sum()
        check(
            ctx,
            "CAT-04",
            "Exactly one first-past-the-post trust per MSOA",
            bool((fp == 1).all()),
            stage=STAGE,
            hard=False,
            metrics={"msoas_not_one": int((fp != 1).sum())},
        )

        un = (1 - msum).clip(lower=0).rename("proportion_published").reset_index()
        un = un.assign(trust_code=UNASSIGNED, fptp=False)
        prop = prop.join(msum.rename("msum"), on="msoa21_code")
        prop["proportion_rescaled"] = prop["proportion_published"] / prop["msum"]
        un["proportion_rescaled"] = 0.0
        m = pd.concat(
            [prop.drop(columns="msum"), un[un["proportion_published"] > 0]], ignore_index=True
        )
        bridge = lookup[["lsoa21_code", "msoa21_code"]].merge(m, on="msoa21_code", how="inner")
        bridge = bridge[
            [
                "lsoa21_code",
                "msoa21_code",
                "trust_code",
                "proportion_published",
                "proportion_rescaled",
                "fptp",
            ]
        ]
        bridge = bridge.sort_values(["lsoa21_code", "trust_code"]).reset_index(drop=True)
        step.add(
            int((bridge["trust_code"] == UNASSIGNED).sum()), "UNASSIGNED rows (1 − Σ published)"
        )
        s = bridge.groupby("lsoa21_code")[["proportion_published", "proportion_rescaled"]].sum()
        check(
            ctx,
            "CAT-05",
            "Bridge proportions sum to 1 per LSOA (published incl. UNASSIGNED; rescaled)",
            bool(np.allclose(s.to_numpy(), 1, atol=1e-9)) and len(s) == len(lookup),
            stage=STAGE,
            metrics={"lsoas": len(s), "max_err": float((s - 1).abs().to_numpy().max())},
        )
        step.output("bridge_lsoa_trust", bridge)
    return bridge


def host_icbs(
    ctx: RunContext,
    rels: pd.DataFrame,
    lookup: pd.DataFrame,
    t7: pd.DataFrame,
    source: tuple[Path, str] | None = None,
) -> pd.Series:
    """Trust code -> ``icb_code`` of the ICB the trust is located in (ODS directory, S10; ADR-0025).

    ODS has no "reports to" relationship for NHS trusts (they are independent bodies), so the host
    ICB is the one ODS says the trust "is located in the geography of" (RE5): exactly one per trust.
    """
    cfg = ctx.cfg.catchments.host_icb
    trusts = t7["Trust code"].astype(str)
    with logged_step(ctx, "catchments.host_icb") as step:
        if source:  # (path, sha256) of the raw snapshot
            step.input_file(f"{cfg.source}/{cfg.file}", source[0], source[1], rows=len(rels))
        else:
            step.input("ods_relationships", rels)
        r = rels[
            (rels["relationship_id"] == cfg.relationship)
            & (rels["target_role_id"] == cfg.target_role)
            & (rels["status"] == "Active")
            & rels["org_code"].isin(trusts)
        ]
        per_trust = r.groupby("org_code").size().reindex(trusts, fill_value=0)
        ods_to_icb = lookup.drop_duplicates("icb_ods_code").set_index("icb_ods_code")["icb_code"]
        host = r.drop_duplicates("org_code").set_index("org_code")["target_code"].map(ods_to_icb)
        host = host.reindex(trusts)
        host.index = trusts.to_numpy()
        check(
            ctx,
            "CAT-12",
            "Every acute trust has exactly one active ODS host-ICB link, and it is a current ICB",
            bool((per_trust == 1).all() and host.notna().all()),
            stage=STAGE,
            metrics={
                "trusts": len(trusts),
                "not_exactly_one": sorted(per_trust.index[per_trust != 1]),
                "unmapped_icb": sorted(host.index[host.isna()]),
            },
        )
        site_icb = t7.set_index(trusts.to_numpy())["Lower super output area code (LSOA21CD)"].map(
            lookup.set_index("lsoa21_code")["icb_code"]
        )
        agree = host == site_icb
        check(
            ctx,
            "CAT-13",
            "Host ICB agrees with the ICB of the trust's main-site LSOA (corroboration, "
            "informational)",
            True,
            stage=STAGE,
            hard=False,
            metrics={
                "agree": int(agree.sum()),
                "of": len(host),
                "disagree": sorted(agree.index[~agree]),
            },
        )
        step.output("host_icb", host.rename("host_icb_code").reset_index())
    return host


def build_dim_trust(
    ctx: RunContext, t7: pd.DataFrame, bridge: pd.DataFrame, host_icb: pd.Series
) -> pd.DataFrame:
    focus = set(ctx.cfg.focus_trusts)
    d = pd.DataFrame(
        {
            "trust_code": t7["Trust code"].astype(str),
            "trust_name": t7["Trust name"],
            "trust_type": t7["Trust type"],
            "commissioning_region": t7["Commisioning region"],
            "site_lsoa21_code": t7["Lower super output area code (LSOA21CD)"],
        }
    )
    d = pd.concat(
        [
            d,
            pd.DataFrame(
                [
                    {
                        "trust_code": UNASSIGNED,
                        "trust_name": "Unassigned (OHID suppressed/rounded flows; ADR-0019)",
                        "trust_type": "n/a",
                        "commissioning_region": "n/a",
                        "site_lsoa21_code": "",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    d["is_focus"] = d["trust_code"].isin(focus)
    d["host_icb_code"] = d["trust_code"].map(host_icb)  # None for UNASSIGNED
    d = d.sort_values("trust_code").reset_index(drop=True)
    missing = set(bridge["trust_code"]) - set(d["trust_code"])
    check(
        ctx,
        "CAT-06",
        "Every bridge trust is in dim_trust; every focus trust is present",
        not missing and focus <= set(d["trust_code"]),
        stage=STAGE,
        metrics={
            "missing_in_dim": sorted(missing),
            "focus_missing": sorted(focus - set(d["trust_code"])),
        },
    )
    return d


def compare_with_ohid(
    ctx: RunContext,
    frames: dict[str, pd.DataFrame],
    bridge: pd.DataFrame,
    lsoa_pop: pd.Series,
    lsoa_eth5: pd.DataFrame,
    imd_score: pd.Series,
) -> dict[str, pd.DataFrame]:
    """Trust totals, 5-group ethnicity and mean IMD score vs OHID T1/T5/T6 (informational)."""
    b = bridge[bridge["trust_code"] != UNASSIGNED].copy()
    b["pop"] = b["lsoa21_code"].map(lsoa_pop)
    tot = b.assign(
        pub=b["proportion_published"] * b["pop"], res=b["proportion_rescaled"] * b["pop"]
    )
    tot = tot.groupby("trust_code")[["pub", "res"]].sum()
    t1 = frames["Trust_analysis"]
    t1 = t1.assign(pop=pd.to_numeric(t1["Catchment population"])).groupby("Trust code")["pop"].sum()
    totals = tot.join(t1.rename("ohid_t1_mye2022"), how="outer").reset_index(names="trust_code")
    totals = totals.rename(columns={"pub": "modelled_published", "res": "modelled_rescaled"})
    totals["pct_published_vs_ohid"] = (
        totals["modelled_published"] / totals["ohid_t1_mye2022"] - 1
    ) * 100
    totals["pct_rescaled_vs_ohid"] = (
        totals["modelled_rescaled"] / totals["ohid_t1_mye2022"] - 1
    ) * 100
    unassigned = float(
        (
            bridge.loc[bridge["trust_code"] == UNASSIGNED, "proportion_published"]
            * bridge.loc[bridge["trust_code"] == UNASSIGNED, "lsoa21_code"].map(lsoa_pop)
        ).sum()
    )
    recon = float(tot["pub"].sum() + unassigned)
    check(
        ctx,
        "CAT-07",
        "Σ trusts (published) + UNASSIGNED = total population (reconciles)",
        abs(recon - float(lsoa_pop.sum())) <= 1e-9 * float(lsoa_pop.sum()),
        stage=STAGE,
        metrics={
            "trusts_plus_unassigned": recon,
            "population": float(lsoa_pop.sum()),
            "unassigned": unassigned,
            "rescaled_total": float(tot["res"].sum()),
        },
    )

    # Ethnicity: OHID "All (5% and above)" ~ trust rows with proportion >= 5%; FPTP = whole MSOA.
    groups = list(lsoa_eth5.columns)
    rows = []
    for method, sel in (
        ("All (5% and above)", b["proportion_published"] >= OHID_5PCT),
        ("First past the post", b["fptp"]),
    ):
        bb = b[sel]
        w = (
            bb["proportion_published"]
            if method.startswith("All")
            else pd.Series(1.0, index=bb.index)
        )
        e = lsoa_eth5.loc[bb["lsoa21_code"]].to_numpy() * w.to_numpy()[:, None]
        agg = pd.DataFrame(e, columns=groups).groupby(bb["trust_code"].to_numpy()).sum()
        imd = (
            pd.Series(
                w.to_numpy()
                * bb["pop"].to_numpy()
                * imd_score.reindex(bb["lsoa21_code"]).to_numpy()
            )
            .groupby(bb["trust_code"].to_numpy())
            .sum()
        )
        popw = (
            pd.Series(w.to_numpy() * bb["pop"].to_numpy())
            .groupby(bb["trust_code"].to_numpy())
            .sum()
        )
        for tc, r in agg.iterrows():
            t = r.sum()
            rows.append(
                {
                    "trust_code": tc,
                    "selection_method": method,
                    "modelled_total": t,
                    **{f"modelled_pct_{g}": r[g] / t * 100 for g in groups},
                    "modelled_imd_score": imd[tc] / popw[tc],
                }
            )
    eth = pd.DataFrame(rows)
    t5 = frames["Ethnicity"]
    lab = {"Asian": "A", "black": "B", "mixed": "M", "white": "W", "other": "O"}
    o = pd.DataFrame({"trust_code": t5["Trust code"], "selection_method": t5["Selection method"]})
    for word, g in lab.items():
        col = next(c for c in t5.columns if c.lower() == f"percentage {word.lower()}")
        o[f"ohid_pct_{g}"] = pd.to_numeric(t5[col]) * 100
    eth = eth.merge(o, on=["trust_code", "selection_method"], how="left")
    for g in groups:
        eth[f"diff_pp_{g}"] = eth[f"modelled_pct_{g}"] - eth[f"ohid_pct_{g}"]
    t6 = frames["Deprivation"]
    imd_o = pd.DataFrame(
        {"trust_code": t6["Trust code"], "ohid_imd_score": pd.to_numeric(t6["IMD score"])}
    )
    imd_cmp = eth[eth["selection_method"] == "All (5% and above)"][
        ["trust_code", "modelled_imd_score"]
    ]
    imd_cmp = imd_cmp.merge(imd_o, on="trust_code", how="left")
    imd_cmp["diff"] = imd_cmp["modelled_imd_score"] - imd_cmp["ohid_imd_score"]

    focus = set(ctx.cfg.focus_trusts)
    f_tot = totals[totals["trust_code"].isin(focus)]
    check(
        ctx,
        "CAT-08",
        "Trust totals vs OHID T1 (informational; OHID uses mid-2022 populations)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "focus": f_tot.round(1).to_dict("records"),
            "all_pct_rescaled_vs_ohid": totals["pct_rescaled_vs_ohid"]
            .describe()
            .round(2)
            .to_dict(),
        },
    )
    f_eth = eth[eth["trust_code"].isin(focus)]
    dcols = [f"diff_pp_{g}" for g in groups]
    check(
        ctx,
        "CAT-09",
        "Trust 5-group ethnicity vs OHID T5, both selection methods (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "max_abs_diff_pp_all_trusts": {
                m: float(eth.loc[eth.selection_method == m, dcols].abs().max().max())
                for m in eth["selection_method"].unique()
            },
            "focus": f_eth[["trust_code", "selection_method", *dcols]].round(2).to_dict("records"),
        },
    )
    check(
        ctx,
        "CAT-10",
        "Trust mean IMD 2025 score vs OHID T6 (informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "max_abs_diff": float(imd_cmp["diff"].abs().max()),
            "focus": imd_cmp[imd_cmp["trust_code"].isin(focus)].round(2).to_dict("records"),
        },
    )
    return {"totals": totals, "ethnicity": eth, "imd": imd_cmp}


UTLA_LOOKUP = ("S7d", "lad22_ctyua22.csv")  # diagnostic only
DIAG_LEVELS = [
    "lsoa21_code",
    "msoa21_code",
    "ltla21_code",
    "utla21_code",
    "sicbl_code",
    "icb_code",
    "nhser_code",
]


def ohid_5pct_diagnostic(
    ctx: RunContext,
    bridge: pd.DataFrame,
    lookup: pd.DataFrame,
    lsoa_pop: pd.Series,
    lsoa_eth5: pd.DataFrame,
    ohid_eth: pd.DataFrame,
) -> pd.DataFrame:
    """Which geography's ethnic mix best reproduces OHID's 'All (5% and above)' T5 figures?

    OHID's FPTP ethnicity matches ours closely but its 'All (5% and above)' figures don't, although
    the same weighting reproduces T6 IMD. Hypothesis: OHID applied each area's ethnic mix at a
    coarser geography. For each candidate level, the LSOA ethnic mix is replaced by its level's mix
    and trust percentages are recomputed with the 5%-threshold, share-weighted method.
    Diagnostic only: nothing here changes the estimates.
    """
    lk = lookup.set_index("lsoa21_code", drop=False)
    try:
        path, _ = raw_file(ctx.cfg, *UTLA_LOOKUP)
        utla = pd.read_csv(path, encoding="utf-8-sig").set_index("LTLA22CD")["UTLA22CD"]
        lk = lk.assign(utla21_code=lk["ltla21_code"].map(utla))
    except FileNotFoundError:
        lk = lk.assign(utla21_code=pd.NA)
    groups = list(lsoa_eth5.columns)
    b = bridge[(bridge["trust_code"] != UNASSIGNED) & (bridge["proportion_published"] >= OHID_5PCT)]
    w = b["proportion_published"].to_numpy() * lsoa_pop.reindex(b["lsoa21_code"]).to_numpy()
    oh = ohid_eth[ohid_eth["selection_method"] == "All (5% and above)"].set_index("trust_code")
    rows = []
    for level in DIAG_LEVELS:
        if lk[level].isna().any():
            continue
        g = lk.loc[lsoa_eth5.index, level].to_numpy()
        agg = lsoa_eth5.groupby(g).sum()
        mix = agg.div(agg.sum(axis=1), axis=0).loc[g].set_axis(lsoa_eth5.index)
        m = mix.loc[b["lsoa21_code"]].mul(w, axis=0)
        t = m.groupby(b["trust_code"].to_numpy()).sum()
        t = t.div(t.sum(axis=1), axis=0) * 100
        j = t.join(oh[[f"ohid_pct_{x}" for x in groups]], how="inner")
        err = pd.concat([(j[x] - j[f"ohid_pct_{x}"]).abs() for x in groups], axis=1).to_numpy()
        row = {
            "ethnic_mix_level": level,
            "trusts": len(j),
            "mean_abs_diff_pp": float(err.mean()),
            "median_abs_diff_pp": float(np.median(err)),
        }
        for tc in ctx.cfg.focus_trusts:
            if tc in j.index:
                row[f"{tc}_pct_A"] = float(j.loc[tc, "A"])
                row[f"{tc}_ohid_pct_A"] = float(j.loc[tc, "ohid_pct_A"])
        rows.append(row)
    out = pd.DataFrame(rows)
    best = out.loc[out["mean_abs_diff_pp"].idxmin()]
    lsoa_err = float(out.loc[out["ethnic_mix_level"] == "lsoa21_code", "mean_abs_diff_pp"].iloc[0])
    check(
        ctx,
        "CAT-11",
        "Diagnostic: which geography's ethnic mix best reproduces OHID 'All (5% and above)' "
        "(informational)",
        True,
        stage=STAGE,
        hard=False,
        metrics={
            "best_level": best["ethnic_mix_level"],
            "best_mean_abs_diff_pp": round(float(best["mean_abs_diff_pp"]), 2),
            "lsoa_mean_abs_diff_pp": round(lsoa_err, 2),
        },
    )
    return out


def run(
    ctx: RunContext, lsoa_pop: pd.Series, lsoa_eth5: pd.DataFrame, imd_score: pd.Series
) -> dict:
    from lsc_pop.geography import load_lookup

    cfg = ctx.cfg
    lookup = load_lookup(cfg)
    frames = load_ohid(ctx)
    bridge = build_bridge(ctx, frames["All_admissions"], lookup)
    hi = cfg.catchments.host_icb
    path, entry = raw_file(cfg, hi.source, hi.file)
    host = host_icbs(
        ctx, read_relationships(path), lookup, frames["Trust_area_lookup"], (path, entry["sha256"])
    )
    dim_trust = build_dim_trust(ctx, frames["Trust_area_lookup"], bridge, host)
    comp = compare_with_ohid(ctx, frames, bridge, lsoa_pop, lsoa_eth5, imd_score)
    comp["ethnicity_diagnostic"] = ohid_5pct_diagnostic(
        ctx, bridge, lookup, lsoa_pop, lsoa_eth5, comp["ethnicity"]
    )
    out = cfg.resolve(cfg.paths.interim) / OUT
    src = [
        {
            "id": cfg.catchments.source,
            "file": cfg.catchments.file,
            "catchment_year": cfg.catchments.catchment_year,
            "admission_type": cfg.catchments.admission_type,
        },
        {"id": cfg.catchments.host_icb.source, "file": cfg.catchments.host_icb.file},
    ]
    write_output(
        bridge,
        out / "bridge_lsoa_trust",
        ctx,
        sources=src,
        description="LSOA x acute trust catchment proportions (ADR-0019)",
    )
    write_output(dim_trust, out / "dim_trust", ctx, sources=src, description="Acute trusts")
    for k, v in comp.items():
        v.to_csv(ctx.out_dir / f"trust_comparison_{k}.csv", index=False)
    return {"bridge": bridge, "dim_trust": dim_trust, **comp}
