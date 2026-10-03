"""Final outputs: a star schema for SQL/Databricks (ADR-0018).

Writes ``outputs/<run_id>/tables/``:

* ``fact_population``: lsoa21_code, sex, age, eth19, population, reference_year. One Parquet
  file, plus one CSV per ICB in ``fact_population_csv/`` (ADR-0013);
* ``dim_lsoa``, ``dim_ethnicity``, ``dim_age``, ``dim_trust``, ``bridge_lsoa_trust``: Parquet + CSV;
* the geography levels snowflaked off ``dim_lsoa`` (ADR-0025): ``dim_msoa``, ``dim_ltla``,
  ``dim_region``, ``dim_lad``, ``dim_sub_icb``, ``dim_icb``, ``dim_nhs_region``;
* ``schema.sql``: DDL and example queries.

Every file has a ``.metadata.json`` sidecar. Referential-integrity and reconciliation checks run
here (OUT-01 to OUT-07).
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


# Geography levels snowflaked off dim_lsoa (ADR-0025): table -> (columns of the lookup, renames).
# The first column is the key; a later *_code column is the parent level's key (FK).
GEOGRAPHY_DIMS = {
    "dim_region": ["rgn21_code", "rgn21_name"],
    "dim_ltla": ["ltla21_code", "ltla21_name", "rgn21_code"],
    "dim_msoa": ["msoa21_code", "msoa21_name", "ltla21_code"],
    "dim_lad": ["lad_code", "lad_name"],
    "dim_nhs_region": ["nhser_code", "nhser_ods_code", "nhser_name"],
    "dim_icb": [
        "icb_code",
        "icb_ods_code",
        "icb_name",
        "nhser_code",
        "in_footprint",
        "in_focus_icb",
    ],
    "dim_sub_icb": ["sicbl_code", "sicbl_ods_code", "sicbl_name", "icb_code"],
}
LEVEL_TABLE = {  # key column -> the dimension it identifies
    "msoa21_code": "dim_msoa",
    "ltla21_code": "dim_ltla",
    "lad_code": "dim_lad",
    "sicbl_code": "dim_sub_icb",
    "icb_code": "dim_icb",
    "rgn21_code": "dim_region",
    "nhser_code": "dim_nhs_region",
}
FK_LINKS = [  # (child table, key column): the child's values must exist in the level's dimension
    ("dim_lsoa", "msoa21_code"),
    ("dim_lsoa", "ltla21_code"),
    ("dim_lsoa", "lad_code"),
    ("dim_lsoa", "sicbl_code"),
    ("dim_lsoa", "icb_code"),
    ("dim_msoa", "ltla21_code"),
    ("dim_ltla", "rgn21_code"),
    ("dim_icb", "nhser_code"),
    ("dim_sub_icb", "icb_code"),
]
GEOGRAPHY_DIM_RENAMES = {"in_footprint": "is_footprint", "in_focus_icb": "is_focus"}
# dim_lsoa keeps its own name and the keys of the levels it joins (the ICB key is a deliberate
# shortcut: ICB is the main reporting split and the IMD quintile grouping).
LSOA_GEOGRAPHY_COLUMNS = [
    "lsoa21_code",
    "lsoa21_name",
    "msoa21_code",
    "ltla21_code",
    "lad_code",
    "sicbl_code",
    "icb_code",
    "nhs_geog_vintage",
]


def geography_dims(lk: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for name, cols in GEOGRAPHY_DIMS.items():
        d = lk[cols].drop_duplicates().sort_values(cols[0]).reset_index(drop=True)
        if not d[cols[0]].is_unique:
            raise ValueError(f"{name}: attributes are not a function of {cols[0]}")
        out[name] = d.rename(columns=GEOGRAPHY_DIM_RENAMES)
    return out


def read_lookup(cfg: Config) -> pd.DataFrame:
    return pd.read_parquet(cfg.resolve(cfg.paths.interim) / "geography" / "lsoa_lookup.parquet")


def dim_lsoa(cfg: Config, population: pd.Series, lk: pd.DataFrame) -> pd.DataFrame:
    iod = pd.read_parquet(cfg.resolve(cfg.paths.interim) / "deprivation" / "iod.parquet")
    d = lk[LSOA_GEOGRAPHY_COLUMNS].merge(iod, on="lsoa21_code", how="left", validate="1:1")
    d[f"population_mid{cfg.reference_year}"] = d["lsoa21_code"].map(population)
    return d


def write_fact_csv_by_icb(cube: Cube, icb_of_lsoa: pd.Series, out_dir, ref_year: int):
    """One CSV per ICB (ADR-0013). Returns {icb_code: rows}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lsoas = np.array(cube.coords["lsoa21_code"])
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
                "lsoa21_code": np.repeat(lsoas[idx], n_rest),
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
    pop = pd.Series(cube.data.sum((1, 2, 3)), index=cube.coords["lsoa21_code"])
    interim = cfg.resolve(cfg.paths.interim)
    bridge = pd.read_parquet(interim / "catchments" / "bridge_lsoa_trust.parquet")
    trust = pd.read_parquet(interim / "catchments" / "dim_trust.parquet")
    lk = read_lookup(cfg)
    dl, de, da = dim_lsoa(cfg, pop, lk), dim_ethnicity(cfg), dim_age(cfg)
    geo = geography_dims(lk)
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
            cfg.catchments.host_icb.source,
        )
    ]

    with logged_step(ctx, "outputs.validate") as step:
        step.input_cube("estimates", cube)
        lsoas = set(dl["lsoa21_code"])
        fk = {
            "fact.lsoa in dim_lsoa": set(cube.coords["lsoa21_code"]) <= lsoas,
            "fact.eth19 in dim_ethnicity": set(cube.coords["eth19"]) <= set(de["eth19"]),
            "fact.age in dim_age": set(cube.coords["age"]) <= set(da["age"]),
            "bridge.lsoa in dim_lsoa": set(bridge["lsoa21_code"]) <= lsoas,
            "bridge.trust in dim_trust": set(bridge["trust_code"]) <= set(trust["trust_code"]),
            "dim_lsoa unique": dl["lsoa21_code"].is_unique
            and len(dl) == len(cube.coords["lsoa21_code"]),
            "dim_trust.host_icb_code in dim_icb": set(trust["host_icb_code"].dropna())
            <= set(geo["dim_icb"]["icb_code"]),
        }
        for child, key in FK_LINKS:
            child_df = dl if child == "dim_lsoa" else geo[child]
            parent = geo[LEVEL_TABLE[key]]
            fk[f"{child}.{key} in {LEVEL_TABLE[key]}"] = set(child_df[key]) <= set(parent[key])
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
        icb_fact = pop.groupby(
            dl.set_index("lsoa21_code").loc[pop.index, "icb_code"].to_numpy()
        ).sum()
        icb_dim = dl.groupby("icb_code")[f"population_mid{cfg.reference_year}"].sum()
        gap = float((icb_fact - icb_dim.reindex(icb_fact.index)).abs().max())
        check(
            ctx,
            "OUT-03",
            "ICB totals from fact = sum of dim_lsoa populations",
            gap < 1e-6,
            stage=STAGE,
            metrics={"max_abs_gap": gap, "icbs": len(icb_fact)},
        )
        trust_tot = (bridge["proportion_published"] * bridge["lsoa21_code"].map(pop)).sum()
        check(
            ctx,
            "OUT-04",
            "Σ over trusts incl. UNASSIGNED = England total",
            abs(trust_tot - pop.sum()) < 1e-6 * pop.sum(),
            stage=STAGE,
            metrics={"trust_total": float(trust_tot), "population": float(pop.sum())},
        )
        # The shortcut keys kept in dim_lsoa must agree with the path through the hierarchy.
        via_sub_icb = dl["sicbl_code"].map(geo["dim_sub_icb"].set_index("sicbl_code")["icb_code"])
        via_msoa = dl["msoa21_code"].map(geo["dim_msoa"].set_index("msoa21_code")["ltla21_code"])
        bad = {
            "icb_code vs sub-ICB parent": int((via_sub_icb != dl["icb_code"]).sum()),
            "ltla21_code vs MSOA parent": int((via_msoa != dl["ltla21_code"]).sum()),
        }
        check(
            ctx,
            "OUT-07",
            "dim_lsoa shortcut keys agree with the geography hierarchy",
            not any(bad.values()),
            stage=STAGE,
            metrics=bad,
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
            dl.set_index("lsoa21_code").loc[cube.coords["lsoa21_code"], "icb_code"],
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
        geo_desc = {
            "dim_region": "Region dimension (ONS region 2021)",
            "dim_ltla": "Lower-tier local authority 2021 dimension (-> region)",
            "dim_msoa": "MSOA 2021 dimension (-> LTLA 2021)",
            "dim_lad": "Local authority district dimension (current, April 2026 lookup)",
            "dim_nhs_region": "NHS England region dimension",
            "dim_icb": "ICB dimension (-> NHS region) with the footprint and focus flags",
            "dim_sub_icb": "Sub-ICB location dimension (-> ICB)",
        }
        for name, df, desc in (
            ("dim_lsoa", dl, "LSOA dimension: geography keys, IoD 2025, mid-year population"),
            *((n, geo[n], geo_desc[n]) for n in GEOGRAPHY_DIMS),
            ("dim_ethnicity", de, "Ethnic group dimension (19 -> 6 -> 5)"),
            ("dim_age", da, "Age dimension (single year -> 5yr, 10yr, RM032 band)"),
            (
                "dim_trust",
                trust,
                "Acute trust dimension (OHID) incl. UNASSIGNED, with host ICB (ODS)",
            ),
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
