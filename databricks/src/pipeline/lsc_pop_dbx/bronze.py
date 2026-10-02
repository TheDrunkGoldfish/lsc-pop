"""Bronze: raw source files → rows, as faithful to the source as practical.

* Formats Spark reads natively (the Nomis CSVs and the ONS-API JSON lines) use **Auto Loader**
  (``cloudFiles``) streaming reads on Databricks, and plain batch reads in the local harness.
* xlsx (ONS mid-year estimates), ODS (OHID catchments), the zipped TS021 CSV and the small
  BOM-prefixed lookup CSVs are parsed with the same Python code as the local pipeline
  (``lsc_pop``), so both implementations read identical values.

Every bronze table carries ``_source_file`` and ``_ingested_at``. Hashes are in
``audit.source_manifest`` (written by the ingest task, checked against the committed manifest).
"""

from __future__ import annotations

import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path

import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T

from lsc_pop import census, deprivation
from lsc_pop.mappings import load_ethnicity_mapping
from lsc_pop.ods import read_ods_sheets, sheet_to_frame
from lsc_pop.rollforward import _read_sheet

from .params import Names

RM032_SCHEMA = T.StructType(
    [
        T.StructField(c, t)
        for c, t in (
            ("GEOGRAPHY_CODE", T.StringType()),
            ("C2021_ETH_20", T.IntegerType()),
            ("C2021_AGE_6", T.IntegerType()),
            ("C_SEX", T.IntegerType()),
            ("OBS_VALUE", T.LongType()),
            ("RECORD_COUNT", T.LongType()),
        )
    ]
)
RM200_SCHEMA = T.StructType(
    [
        T.StructField(c, t)
        for c, t in (
            ("GEOGRAPHY_CODE", T.StringType()),
            ("C2021_AGE_92", T.IntegerType()),
            ("C_SEX", T.IntegerType()),
            ("OBS_VALUE", T.LongType()),
            ("RECORD_COUNT", T.LongType()),
        )
    ]
)
_DIM = T.StructType(
    [T.StructField("dimension_id", T.StringType()), T.StructField("option_id", T.StringType())]
)
_OBS = T.StructType(
    [T.StructField("dimensions", T.ArrayType(_DIM)), T.StructField("observation", T.LongType())]
)
SEED_SCHEMA = T.StructType(
    [
        T.StructField("batch", T.LongType()),
        T.StructField("requested", T.ArrayType(T.StringType())),
        T.StructField("blocked", T.ArrayType(T.StringType())),
        T.StructField(
            "response",
            T.StructType(
                [
                    T.StructField("observations", T.ArrayType(_OBS)),
                    T.StructField("total_observations", T.LongType()),
                    T.StructField("blocked_areas", T.LongType()),
                ]
            ),
        ),
    ]
)
SEED_FILES = {"age_91a": census.SEED91, "age_23a": census.SEED23}


def _with_meta(df: DataFrame) -> DataFrame:
    return df.withColumn("_source_file", F.col("_metadata.file_path")).withColumn(
        "_ingested_at", F.current_timestamp()
    )


def _read(spark, n: Names, source_id: str, file: str, fmt: str, schema, streaming: bool, **opts):
    """Auto Loader stream on Databricks; batch read in the local harness."""
    folder = f"{n.raw_dir.rstrip('/')}/{source_id}/"
    if streaming and not n.local:
        reader = (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", fmt)
            .option("pathGlobFilter", file)
            .schema(schema)
        )
    else:
        reader = spark.read.format(fmt).option("pathGlobFilter", file).schema(schema)
    for k, v in opts.items():
        reader = reader.option(k, v)
    return _with_meta(reader.load(folder))


def arrow_safe(pdf: pd.DataFrame) -> pd.DataFrame:
    """pandas 3 string columns -> object, so Spark's Arrow conversion works on any pandas."""
    text = [c for c in pdf.columns if pd.api.types.is_string_dtype(pdf[c])]
    return pdf.astype({c: object for c in text}) if text else pdf


def _from_pandas(spark, pdf: pd.DataFrame, source_file: str) -> DataFrame:
    return (
        spark.createDataFrame(arrow_safe(pdf))
        .withColumn("_source_file", F.lit(source_file))
        .withColumn("_ingested_at", F.current_timestamp())
    )


def snake(name: str) -> str:
    """Column-name normaliser for spreadsheet headers ('Trust code' -> 'trust_code')."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", " ".join(str(name).split())).strip("_").lower()
    return s or "col"


# --- Census (Nomis CSV, ONS API JSON lines, Nomis bulk zip) ----------------------------------


def rm032_raw(spark, n: Names, streaming: bool = True) -> DataFrame:
    sid, file = census.RM032
    return _read(spark, n, sid, file, "csv", RM032_SCHEMA, streaming, header="true")


def rm200_raw(spark, n: Names, streaming: bool = True) -> DataFrame:
    sid, file = census.RM200
    return _read(spark, n, sid, file, "csv", RM200_SCHEMA, streaming, header="true")


def _seed_lines(spark, n: Names, classification: str, streaming: bool) -> DataFrame:
    sid, file, _dim, _cls = SEED_FILES[classification]
    return _read(spark, n, sid, file, "json", SEED_SCHEMA, streaming).withColumn(
        "classification", F.lit(classification)
    )


def seed_raw(spark, n: Names, streaming: bool = True) -> DataFrame:
    """ONS-API observations, one row per LTLA × ethnic group × sex × age category."""
    parts = []
    for cls, (_sid, _file, dim, _c) in SEED_FILES.items():
        lines = _seed_lines(spark, n, cls, streaming)
        obs = lines.select(
            "classification",
            "_source_file",
            "_ingested_at",
            F.explode("response.observations").alias("o"),
        )
        dims = F.map_from_entries(
            F.transform("o.dimensions", lambda d: F.struct(d["dimension_id"], d["option_id"]))
        )
        parts.append(
            obs.select(
                dims["ltla"].alias("ltla21cd"),
                dims["ethnic_group_tb_20b"].cast("int").alias("eth_code"),
                dims["sex"].cast("int").alias("sex_code"),
                dims[dim].cast("int").alias("age_code"),
                F.col("o.observation").alias("population"),
                "classification",
                "_source_file",
                "_ingested_at",
            )
        )
    return parts[0].unionByName(parts[1])


def seed_blocked_raw(spark, n: Names, streaming: bool = True) -> DataFrame:
    """LTLAs the ONS API blocked (disclosure control), per classification."""
    parts = [
        _seed_lines(spark, n, cls, streaming).select(
            F.explode("blocked").alias("ltla21cd"), "classification", "_source_file", "_ingested_at"
        )
        for cls in SEED_FILES
    ]
    return parts[0].unionByName(parts[1])


def seed_requested_raw(spark, n: Names) -> DataFrame:
    """Areas requested per classification (for the 'returned + blocked = requested' check)."""
    parts = [
        _seed_lines(spark, n, cls, streaming=False).select(
            F.explode("requested").alias("ltla21cd"), "classification"
        )
        for cls in SEED_FILES
    ]
    return parts[0].unionByName(parts[1])


def ts021_raw(spark, n: Names, cfg) -> DataFrame:
    """TS021 (zipped wide CSV) → long rows: lsoa21cd, label, population (labels as published)."""
    sid, zname, member = census.TS021
    path = n.raw(sid, zname)
    with zipfile.ZipFile(path) as z:
        wide = pd.read_csv(z.open(member))
    long = wide.drop(columns=["date", "geography"]).melt(
        id_vars="geography code", var_name="label", value_name="population"
    )
    long = long.rename(columns={"geography code": "lsoa21cd"})
    long["population"] = long["population"].astype("int64")
    return _from_pandas(spark, long, f"{path}!{member}")


# --- Lookups, IoD, mid-year estimates, OHID ---------------------------------------------------


def lookup_raw(spark, n: Names, spec) -> DataFrame:
    """A geography lookup with its configured columns renamed to standard names (ADR-0014)."""
    path = n.raw(spec.source, spec.file)
    raw = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    missing = set(spec.columns) - set(raw.columns)
    if missing:
        raise KeyError(
            f"{spec.source}/{spec.file} lacks {sorted(missing)}; update config.geography"
        )
    return _from_pandas(spark, raw[list(spec.columns)].rename(columns=spec.columns), path)


def iod_raw(spark, n: Names, cfg) -> DataFrame:
    d = cfg.deprivation
    path = n.raw(d.source, d.file)
    raw = pd.read_csv(path, dtype={"LSOA code (2021)": str})
    rename = {c: deprivation._standard_name(c) for c in raw.columns}
    rename = {k: v for k, v in rename.items() if v} | {"LSOA code (2021)": "lsoa21cd"}
    return _from_pandas(spark, raw[list(rename)].rename(columns=rename), path)


def mye_raw(spark, n: Names, cfg) -> DataFrame:
    """ONS mid-year LSOA estimates (S5) for the reference year: wide, as published."""
    path = n.raw(cfg.mye.source, cfg.mye.file)
    df = _read_sheet(Path(path), cfg.mye_sheet, cfg.mye.header_row)
    df = df.rename(columns={"LSOA 2021 Code": "lsoa21cd", "Total": "total"})
    cols = ["lsoa21cd", "total"] + [
        f"{s}{a}" for s in ("F", "M") for a in range(cfg.age.max_age + 1)
    ]
    out = df[cols].copy()
    out["lsoa21cd"] = out["lsoa21cd"].astype(str)
    out[cols[1:]] = out[cols[1:]].astype("float64")
    return _from_pandas(spark, out, f"{path}!{cfg.mye_sheet}")


def mye_broad_raw(spark, n: Names, cfg) -> DataFrame:
    """Accredited broad-age file (S5b), for the ROL-04 check."""
    path = n.raw("S5b", "sapelsoabroadage20222024.xlsx")
    df = _read_sheet(Path(path), cfg.mye_sheet, cfg.mye.header_row)
    df = df.rename(columns={"LSOA 2021 Code": "lsoa21cd"})
    keep = ["lsoa21cd"] + [c for c in df.columns if re.match(r"^[FM]\d", str(c))]
    out = df[keep].rename(columns={c: snake(c) for c in keep[1:]})
    out["lsoa21cd"] = out["lsoa21cd"].astype(str)
    out[out.columns[1:]] = out[out.columns[1:]].astype("float64")
    return _from_pandas(spark, out, f"{path}!{cfg.mye_sheet}")


OHID_SHEETS = {
    "ohid_t1_raw": "Trust_analysis",
    "ohid_t2_raw": "All_admissions",
    "ohid_t5_raw": "Ethnicity",
    "ohid_t6_raw": "Deprivation",
    "ohid_t7_raw": "Trust_area_lookup",
}


@lru_cache(maxsize=2)
def _ohid_sheets(path: str) -> dict:
    """Parse the ~550 MB ODS once per process (all five sheets)."""
    return read_ods_sheets(path, list(OHID_SHEETS.values()))


def ohid_raw(spark, n: Names, cfg, table: str) -> DataFrame:
    """One OHID sheet, all rows as text, snake_case headers (types are applied in silver)."""
    path = n.raw(cfg.catchments.source, cfg.catchments.file)
    frame = sheet_to_frame(_ohid_sheets(path)[OHID_SHEETS[table]], header_row=2)
    frame.columns = [snake(c) for c in frame.columns]
    return _from_pandas(spark, frame.astype(str), f"{path}!{OHID_SHEETS[table]}")


def source_manifest(spark, n: Names) -> DataFrame:
    """The ingest task's manifest (URL, release, SHA-256, size per raw file)."""
    with open(n.manifest_path) as f:
        entries = json.load(f)["files"]
    keep = [
        "source_id",
        "file",
        "url",
        "release_date",
        "edition",
        "retrieved_at",
        "sha256",
        "size_bytes",
    ]
    pdf = pd.DataFrame([{k: e.get(k) for k in keep} for e in entries], columns=keep)
    pdf["size_bytes"] = pdf["size_bytes"].astype("int64")
    return spark.createDataFrame(
        arrow_safe(pdf.astype({c: str for c in keep if c != "size_bytes"}))
    )


def ethnicity_labels(cfg) -> pd.DataFrame:
    """TS021 column label → eth19 (labels as in the Census table)."""
    m = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    return pd.DataFrame({"label": "Ethnic group: " + m["label_19"], "eth19": m["code_19"]})
