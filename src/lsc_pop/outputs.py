"""Final outputs: a star schema for SQL/Databricks (ADR-0018).

Writes ``outputs/<run_id>/tables/``:

* ``fact_population``: lsoa21cd, sex, age, eth19, population, reference_year. One Parquet
  file, plus one CSV per ICB in ``fact_population_csv/`` (ADR-0013);
* ``dim_lsoa``, ``dim_ethnicity``, ``dim_age``, ``dim_trust``, ``bridge_lsoa_trust``: Parquet + CSV;
* ``schema.sql``: DDL and example queries.

Every file has a ``.metadata.json`` sidecar. Referential-integrity and reconciliation checks run
here (OUT-01 to OUT-06).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv

from lsc_pop.config import Config
from lsc_pop.mappings import (
    age_to_code,
    load_age_bands,
    load_census_age_classifications,
    load_ethnicity_mapping,
)
from lsc_pop.provenance import Cube, RunContext, logged_step, read_cube, write_cube, write_output
from lsc_pop.validate import check

STAGE = "outputs"


def dim_ethnicity(cfg: Config) -> pd.DataFrame:
    m = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    return m.rename(columns={"code_19": "eth19"}).assign(sort_order=lambda d: d["eth19"])


def dim_age(cfg: Config) -> pd.DataFrame:
    bands = load_age_bands(cfg.resolve(cfg.age.bands_file), cfg.age.max_age, cfg.age.band_sets)
    out = pd.DataFrame({"age": range(cfg.age.max_age + 1)})
    out["age_label"] = out["age"].map(lambda a: f"{a}+" if a == cfg.age.max_age else str(a))
    for bs, g in bands.groupby("band_set", sort=False):
        lab = {a: r.band_label for r in g.itertuples() for a in range(r.age_min, r.age_max + 1)}
        lo = {a: r.age_min for r in g.itertuples() for a in range(r.age_min, r.age_max + 1)}
        out[f"age_{bs}"] = out["age"].map(lab)
        out[f"age_{bs}_sort"] = out["age"].map(lo).astype("int16")
    classes = load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )
    a2b = age_to_code(classes, "rm032_5", cfg.age.max_age)
    labels = classes[classes["classification"] == "rm032_5"].set_index("code")["label"]
    out["census_band_rm032"] = out["age"].map(a2b).map(labels)
    return out


def dim_lsoa(cfg: Config, population: pd.Series) -> pd.DataFrame:
    lk = pd.read_parquet(cfg.resolve(cfg.paths.interim) / "geography" / "lsoa_lookup.parquet")
    iod = pd.read_parquet(cfg.resolve(cfg.paths.interim) / "deprivation" / "iod.parquet")
    d = lk.merge(iod, on="lsoa21cd", how="left", validate="1:1")
    d[f"population_mid{cfg.reference_year}"] = d["lsoa21cd"].map(population)
    return d


def write_fact_csv_by_icb(cube: Cube, icb_of_lsoa: pd.Series, out_dir, ref_year: int):
    """One CSV per ICB (ADR-0013). Returns {icb_cd: rows}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lsoas = np.array(cube.coords["lsoa21cd"])
    n_rest = int(np.prod(cube.data.shape[1:]))
    rest_idx = np.indices(cube.data.shape[1:]).reshape(3, -1)
    sex = np.array(cube.coords["sex"])[rest_idx[0]]
    age = np.array(cube.coords["age"], dtype=np.int16)[rest_idx[1]]
    eth = np.array(cube.coords["eth19"], dtype=np.int16)[rest_idx[2]]
    rows = {}
    for icb, idx in icb_of_lsoa.groupby(icb_of_lsoa.to_numpy()).indices.items():
        idx = np.sort(idx)
        n = len(idx)
        table = pa.table(
            {
                "lsoa21cd": np.repeat(lsoas[idx], n_rest),
                "sex": np.tile(sex, n),
                "age": np.tile(age, n),
                "eth19": np.tile(eth, n),
                "population": cube.data[idx].reshape(-1),
                "reference_year": np.full(n * n_rest, ref_year, dtype=np.int16),
            }
        )
        pacsv.write_csv(table, out_dir / f"icb={icb}.csv")
        rows[icb] = n * n_rest
    return rows


SCHEMA_SQL = Path(__file__).with_name("templates") / "schema.sql"


def run(ctx: RunContext) -> dict:
    from lsc_pop.rollforward import _processed

    cfg = ctx.cfg
    tables = ctx.out_dir / "tables"
    cube = read_cube(_processed(cfg) / "estimates")
    pop = pd.Series(cube.data.sum((1, 2, 3)), index=cube.coords["lsoa21cd"])
    interim = cfg.resolve(cfg.paths.interim)
    bridge = pd.read_parquet(interim / "catchments" / "bridge_lsoa_trust.parquet")
    trust = pd.read_parquet(interim / "catchments" / "dim_trust.parquet")
    dl, de, da = dim_lsoa(cfg, pop), dim_ethnicity(cfg), dim_age(cfg)
    srcs = [
        {"id": i}
        for i in (
            "S1",
            "S2",
            "S3",
            "S4",
            cfg.mye.source,
            "S7",
            "S7b",
            "S7c",
            cfg.deprivation.source,
            cfg.catchments.source,
        )
    ]

    with logged_step(ctx, "outputs.validate") as step:
        step.input_cube("estimates", cube)
        lsoas = set(dl["lsoa21cd"])
        fk = {
            "fact.lsoa in dim_lsoa": set(cube.coords["lsoa21cd"]) <= lsoas,
            "fact.eth19 in dim_ethnicity": set(cube.coords["eth19"]) <= set(de["eth19"]),
            "fact.age in dim_age": set(cube.coords["age"]) <= set(da["age"]),
            "bridge.lsoa in dim_lsoa": set(bridge["lsoa21cd"]) <= lsoas,
            "bridge.trust in dim_trust": set(bridge["trust_code"]) <= set(trust["trust_code"]),
            "dim_lsoa unique": dl["lsoa21cd"].is_unique and len(dl) == len(cube.coords["lsoa21cd"]),
        }
        check(
            ctx,
            "OUT-01",
            "Referential integrity of the star schema",
            all(fk.values()),
            stage=STAGE,
            metrics=fk,
        )
        blanks = int(
            dl.drop(columns=["imd_local_quintile_within"], errors="ignore").isna().sum().sum()
        )
        check(
            ctx,
            "OUT-02",
            "dim_lsoa has no missing values (every LSOA has geography and IoD)",
            blanks == 0,
            stage=STAGE,
            metrics={"missing_cells": blanks},
        )
        # Reconciliation: every footprint aggregate = sum of its LSOAs; trusts + unassigned = total.
        icb_fact = pop.groupby(dl.set_index("lsoa21cd").loc[pop.index, "icb_cd"].to_numpy()).sum()
        icb_dim = dl.groupby("icb_cd")[f"population_mid{cfg.reference_year}"].sum()
        gap = float((icb_fact - icb_dim.reindex(icb_fact.index)).abs().max())
        check(
            ctx,
            "OUT-03",
            "ICB totals from fact = sum of dim_lsoa populations",
            gap < 1e-6,
            stage=STAGE,
            metrics={"max_abs_gap": gap, "icbs": len(icb_fact)},
        )
        trust_tot = (bridge["proportion_published"] * bridge["lsoa21cd"].map(pop)).sum()
        check(
            ctx,
            "OUT-04",
            "Σ over trusts incl. UNASSIGNED = England total",
            abs(trust_tot - pop.sum()) < 1e-6 * pop.sum(),
            stage=STAGE,
            metrics={"trust_total": float(trust_tot), "population": float(pop.sum())},
        )
        step.note(f"fact rows {cube.rows:,}; dim_lsoa {len(dl)}; bridge {len(bridge)}")

    with logged_step(ctx, "outputs.write") as step:
        step.output_cube("fact_population", cube)
        write_cube(
            cube,
            tables / "fact_population",
            ctx,
            sources=srcs,
            constants={"reference_year": cfg.reference_year},
            description="Fact: modelled population by LSOA x sex x single year x eth19",
        )
        rows = write_fact_csv_by_icb(
            cube,
            dl.set_index("lsoa21cd").loc[cube.coords["lsoa21cd"], "icb_cd"],
            tables / "fact_population_csv",
            cfg.reference_year,
        )
        check(
            ctx,
            "OUT-05",
            "fact CSVs (one per ICB) cover every fact row exactly once",
            sum(rows.values()) == cube.rows,
            stage=STAGE,
            metrics={"files": len(rows), "rows": sum(rows.values())},
        )
        for name, df, desc in (
            ("dim_lsoa", dl, "LSOA dimension: geography, IoD 2025, flags, mid-year population"),
            ("dim_ethnicity", de, "Ethnic group dimension (19 -> 6 -> 5)"),
            ("dim_age", da, "Age dimension (single year -> 5yr, 10yr, RM032 band)"),
            ("dim_trust", trust, "Acute trust dimension (OHID) incl. UNASSIGNED"),
            ("bridge_lsoa_trust", bridge, "LSOA x trust catchment proportions (ADR-0019)"),
        ):
            step.output(name, df)
            write_output(df, tables / name, ctx, sources=srcs, csv=True, description=desc)
        (tables / "schema.sql").write_text(
            SCHEMA_SQL.read_text().format(
                ref=f"mid-{cfg.reference_year}", variant=cfg.variant, run_id=ctx.run_id
            )
        )
    hashes = {
        p.stem.replace(".metadata", ""): json.loads(p.read_text())["data_hash"]
        for p in sorted(tables.glob("*.metadata.json"))
    }
    (ctx.out_dir / "output_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")
    check(
        ctx,
        "OUT-06",
        "Output data hashes recorded (compare across runs for reproducibility)",
        True,
        stage=STAGE,
        hard=False,
        metrics=hashes,
    )
    return {"tables": tables, "rows": cube.rows, "hashes": hashes}
