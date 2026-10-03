"""Stage F - Deprivation (IoD 2025 at LSOA 2021; ADR-0008).

Produces ``data/interim/deprivation/iod`` with one row per England LSOA:

* every IoD rank, score and decile, renamed to short standard names (``IOD_COLUMNS``):
  IMD, the 7 domains, IDACI, IDAOPI and the 6 sub-domains. Rank 1 / decile 1 = most deprived;
* ``imd_quintile`` (national, from deciles: 1-2 -> 1, ..., 9-10 -> 5);
* ``core20``: national IMD decile <= ``core20_max_decile`` (2);
* ``imd_local_quintile``: population-weighted IMD quintile within each ICB (or LAD).
  LSOAs are ordered by national IMD rank (most deprived first; ranks are unique, so there are no
  ties). Each LSOA is placed in the quintile containing the midpoint of its own population on the
  cumulative population scale of its ICB, so each local quintile holds ~20% of the ICB's
  mid-year population.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lsc_pop.download import raw_file
from lsc_pop.provenance import RunContext, logged_step, write_output
from lsc_pop.validate import check

STAGE = "deprivation"
OUT = "deprivation/iod"

_MEASURES = {"Score": "score", "Rank": "rank", "Decile": "decile"}
IOD_PREFIXES = {
    "Index of Multiple Deprivation (IMD)": "imd",
    "Income": "income",
    "Employment": "employment",
    "Education Skills and Training": "education",
    "Health Deprivation and Disability": "health",
    "Crime": "crime",
    "Barriers to Housing and Services": "barriers",
    "Living Environment": "living_env",
    "Income Deprivation Affecting Children Index (IDACI)": "idaci",
    "Income Deprivation Affecting Older People (IDAOPI)": "idaopi",
    "Children and Young People Sub-domain": "sub_children_young_people",
    "Adult Skills Sub-domain": "sub_adult_skills",
    "Geographical Barriers Sub-domain": "sub_geographical_barriers",
    "Wider Barriers Sub-domain": "sub_wider_barriers",
    "Indoors Sub-domain": "sub_indoors",
    "Outdoors Sub-domain": "sub_outdoors",
}


def _standard_name(raw: str) -> str | None:
    """Map an IoD File 7 header to e.g. 'income_score'. Robust to the truncated header and to
    'Education, Skills…' being split across lines/commas."""
    h = " ".join(raw.replace(",", " ").split())
    for prefix, stem in sorted(IOD_PREFIXES.items(), key=lambda kv: -len(kv[0])):
        if h.startswith(prefix + " "):
            rest = h[len(prefix) + 1 :]
            for word, suffix in _MEASURES.items():
                if rest.startswith(word):
                    return f"{stem}_{suffix}"
    return None


def load_iod(ctx: RunContext, lsoas: list[str]) -> pd.DataFrame:
    cfg = ctx.cfg
    d = cfg.deprivation
    with logged_step(ctx, "deprivation.load_iod", params=d.model_dump()) as step:
        path, entry = raw_file(cfg, d.source, d.file)
        raw = pd.read_csv(path, dtype={"LSOA code (2021)": str})
        step.input_file(f"{d.source}/{d.file}", path, entry["sha256"], rows=len(raw))
        rename = {c: _standard_name(c) for c in raw.columns}
        rename = {k: v for k, v in rename.items() if v}
        expected = {f"{stem}_{m}" for stem in IOD_PREFIXES.values() for m in _MEASURES.values()}
        if set(rename.values()) != expected:
            raise KeyError(
                f"IoD columns not recognised: missing {sorted(expected - set(rename.values()))}"
            )
        df = raw.rename(columns=rename | {"LSOA code (2021)": "lsoa21_code"})
        df = df[["lsoa21_code", *sorted(expected)]]
        step.drop(
            0,
            f"kept {len(expected)} rank/score/decile columns; dropped names and mid-2022 "
            "denominators (not used as population inputs)",
        )
        got = pd.Index(df["lsoa21_code"])
        check(
            ctx,
            "DEP-01",
            "IoD covers exactly the lookup LSOAs (1:1)",
            got.is_unique and got.sort_values().equals(pd.Index(lsoas).sort_values()),
            stage=STAGE,
            metrics={"rows": len(df), "missing": len(pd.Index(lsoas).difference(got))},
        )
        ranks = df["imd_rank"]
        check(
            ctx,
            "DEP-02",
            "IMD ranks are a permutation of 1..N and deciles are 1..10",
            sorted(ranks) == list(range(1, len(df) + 1))
            and set(df["imd_decile"]) == set(range(1, 11)),
            stage=STAGE,
        )
        step.output("iod", df)
    return df.set_index("lsoa21_code").loc[lsoas].reset_index()


def local_quintile(rank: pd.Series, pop: pd.Series, group: pd.Series) -> pd.Series:
    """Population-weighted quintile (1 = most deprived) of each LSOA within its group."""
    df = pd.DataFrame({"rank": rank, "pop": pop.astype(float), "group": group})
    df = df.sort_values(["group", "rank"])
    cum = df.groupby("group")["pop"].cumsum()
    tot = df.groupby("group")["pop"].transform("sum")
    mid = (cum - df["pop"] / 2) / tot.where(tot > 0, 1)
    q = np.minimum(np.floor(mid * 5).astype(int) + 1, 5)
    return pd.Series(q, index=df.index).reindex(rank.index).astype("int8")


def run(ctx: RunContext, population: pd.Series) -> pd.DataFrame:
    """``population``: mid-year total per LSOA (index lsoa21_code), used for the local quintile."""
    from lsc_pop.geography import load_lookup

    cfg = ctx.cfg
    lookup = load_lookup(cfg)
    lsoas = lookup["lsoa21_code"].tolist()
    iod = load_iod(ctx, lsoas)
    with logged_step(ctx, "deprivation.derive", params=cfg.deprivation.model_dump()) as step:
        step.input("iod", iod)
        iod["iod_edition"] = cfg.deprivation.edition
        iod["imd_quintile"] = ((iod["imd_decile"] + 1) // 2).astype("int8")
        iod["core20"] = iod["imd_decile"] <= cfg.deprivation.core20_max_decile
        pop = population.reindex(lsoas).to_numpy()
        if np.isnan(pop).any():
            raise ValueError("population missing for some LSOAs")
        lq = cfg.deprivation.local_quintile
        if lq.enabled:
            grp = lookup["icb_code" if lq.within == "icb" else "lad_code"]
            iod["imd_local_quintile"] = local_quintile(
                iod["imd_rank"], pd.Series(pop), grp
            ).to_numpy()
            iod["imd_local_quintile_within"] = lq.within
            shares = pd.DataFrame({"g": grp, "q": iod["imd_local_quintile"], "p": pop}).groupby(
                ["g", "q"]
            )["p"].sum() / pd.Series(pop).groupby(grp.to_numpy()).sum().reindex(
                grp.unique()
            ).rename_axis("g")
            dev = float((shares - 0.2).abs().max())
            check(
                ctx,
                "DEP-03",
                f"Local IMD quintiles hold ~20% of each {lq.within.upper()}'s "
                "population (soft: |share-20%| <= 5pp)",
                dev <= 0.05,
                stage=STAGE,
                hard=False,
                metrics={"max_abs_deviation": dev},
            )
        core_share = float(pop[iod["core20"].to_numpy()].sum() / pop.sum())
        foc = lookup["in_focus_icb"].to_numpy()
        check(
            ctx,
            "DEP-04",
            "Core20 population share (informational)",
            True,
            stage=STAGE,
            hard=False,
            metrics={
                "england": core_share,
                "focus_icb": float(pop[foc & iod["core20"].to_numpy()].sum() / pop[foc].sum()),
            },
        )
        step.output("iod", iod)
    write_output(
        iod,
        cfg.resolve(cfg.paths.interim) / OUT,
        ctx,
        sources=[{"id": cfg.deprivation.source, "file": cfg.deprivation.file}],
        description="IoD 2025 at LSOA with derived quintiles and Core20 (Stage F)",
    )
    return iod
