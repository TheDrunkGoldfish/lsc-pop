"""Audit: OHID comparisons (reusing the local pipeline's code) and run metadata.

``lsc_pop.catchments.compare_with_ohid`` and ``ohid_5pct_diagnostic`` are called unchanged with a
small context object that collects their checks (CAT-07 to CAT-11). The comparison is therefore
computed identically in both implementations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from lsc_pop import catchments
from lsc_pop.mappings import load_ethnicity_mapping
from lsc_pop.ods import sheet_to_frame

from .bronze import _ohid_sheets, arrow_safe
from .params import Names


@dataclass
class CollectingContext:
    """Stands in for ``RunContext`` where lsc_pop code records checks."""

    cfg: Any
    checks: list = field(default_factory=list)

    def append_check(self, record: dict) -> None:
        self.checks.append(record)


def _ohid_frames(n: Names, cfg) -> dict[str, pd.DataFrame]:
    c = cfg.catchments
    sheets = _ohid_sheets(n.raw(c.source, c.file))
    frames = {k: sheet_to_frame(v, header_row=2) for k, v in sheets.items()}
    year, adm = str(c.catchment_year), c.admission_type.lower()
    for k in ("All_admissions", "Trust_analysis", "Ethnicity", "Deprivation"):
        f = frames[k]
        ycol = next(col for col in f.columns if col.lower() == "catchment year")
        keep = (f[ycol].astype(str) == year) & (catchments._norm(f["Admission type"]) == adm)
        frames[k] = f[keep].reset_index(drop=True)
    return frames


_CACHE: dict[str, tuple[dict[str, pd.DataFrame], list]] = {}


def _comparison(spark, n: Names) -> tuple[dict[str, pd.DataFrame], list]:
    """Compute once per pipeline process; each audit table reads its part."""
    key = f"{n.catalog}|{sorted(n.schemas.items())}|{n.raw_dir}"
    if key in _CACHE:
        return _CACHE[key]
    from .params import config

    cfg = config()
    t = lambda layer, name: spark.read.table(n.fq(layer, name))  # noqa: E731
    eth = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    e5 = (
        t("gold", "fact_population")
        .join(
            spark.createDataFrame(arrow_safe(eth[["code_19", "code_5"]])).withColumnRenamed(
                "code_19", "eth19"
            ),
            "eth19",
        )
        .groupBy("lsoa21cd")
        .pivot("code_5", ["A", "B", "M", "O", "W"])
        .agg(F.sum("population"))
        .toPandas()
        .set_index("lsoa21cd")
        .fillna(0.0)
    )
    pop = e5.sum(axis=1)
    bridge = t("gold", "bridge_lsoa_trust").toPandas()
    lookup = t("silver", "lsoa_geography").toPandas()
    imd = (
        t("silver", "iod")
        .select("lsoa21cd", "imd_score")
        .toPandas()
        .set_index("lsoa21cd")["imd_score"]
    )
    ctx = CollectingContext(cfg)
    frames = _ohid_frames(n, cfg)
    comp = catchments.compare_with_ohid(ctx, frames, bridge, pop, e5, imd)
    comp["ethnicity_diagnostic"] = catchments.ohid_5pct_diagnostic(
        ctx, bridge, lookup, pop, e5, comp["ethnicity"]
    )
    _CACHE[key] = (comp, ctx.checks)
    return _CACHE[key]


def write_ohid_tables(spark, n: Names) -> dict[str, int]:
    """Compute the OHID comparisons and write them to the audit schema (audit job task).

    Eager by design: runs after the pipeline, when the gold tables exist.
    """
    _CACHE.clear()
    written = {}
    comp, _ = _comparison(spark, n)
    for which in ("totals", "ethnicity", "imd", "ethnicity_diagnostic"):
        df = ohid_comparison(spark, n, which)
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
            n.fq("audit", f"ohid_comparison_{which}")
        )
        written[which] = len(comp[which])
    ohid_checks(spark, n).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        n.fq("audit", "ohid_checks")
    )
    return written


def ohid_comparison(spark, n: Names, which: str) -> DataFrame:
    comp, _ = _comparison(spark, n)
    return spark.createDataFrame(arrow_safe(comp[which]))


def ohid_checks(spark, n: Names) -> DataFrame:
    _, checks = _comparison(spark, n)
    rows = [
        {
            "check_id": c["check_id"],
            "stage": c["stage"],
            "description": c["description"],
            "hard": bool(c["hard"]),
            "passed": bool(c["passed"]),
            "metrics": json.dumps(c.get("metrics"), default=str),
        }
        for c in checks
    ]
    return spark.createDataFrame(arrow_safe(pd.DataFrame(rows)))
