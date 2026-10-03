"""Silver reference tables built from the lsc-pop config: parameters and mappings.

SQL in the pipeline reads every setting from ``silver.params`` (one row), so no value from
``config.yaml`` is duplicated in SQL or bundle YAML.
"""

from __future__ import annotations

import pandas as pd
from pyspark.sql import DataFrame

from lsc_pop import outputs
from lsc_pop.mappings import age_to_code, load_census_age_classifications
from lsc_pop.provenance import hash_tree
from lsc_pop.rollforward import source_ages

from .bronze import arrow_safe
from .params import Names

SENSITIVITY_VARIANTS = {
    # name -> (variant for source_ages, newborn proxy ages or None for config default)
    "cohort": ("cohort", None),
    "static": ("static", None),
    "cohort_newborn_0_4": ("cohort", [0, 1, 2, 3, 4]),
}


PARAMS_SCHEMA = (
    "reference_year int, variant string, shift_years int, max_age int, margin_source string, "
    "warn_abs double, warn_rel double, ipf_tolerance double, seed_floor double, "
    "expected_lsoa_count int, footprint_mode string, footprint_icb_codes array<string>, "
    "focus_icb_codes array<string>, focus_trusts array<string>, core20_max_decile int, "
    "local_quintile_within string, catchment_year int, admission_type string, "
    "host_icb_relationship string, host_icb_target_role string, "
    "nhs_geog_vintage string, iod_edition string, config_hash string, code_hash string, "
    "bundle_target string, git_commit string"
)


def params(spark, n: Names, cfg) -> DataFrame:
    from pathlib import Path

    import lsc_pop

    row = {
        "reference_year": cfg.reference_year,
        "variant": cfg.variant,
        "shift_years": cfg.shift_years,
        "max_age": cfg.age.max_age,
        "margin_source": cfg.reconciliation.margin_source,
        "warn_abs": float(cfg.reconciliation.warn_abs),
        "warn_rel": float(cfg.reconciliation.warn_rel),
        "ipf_tolerance": float(cfg.ipf.tolerance),
        "seed_floor": float(cfg.ipf.seed_floor),
        "expected_lsoa_count": cfg.geography.expected_lsoa_count,
        "footprint_mode": cfg.footprint.mode,
        "footprint_icb_codes": list(cfg.footprint.icb_codes),
        "focus_icb_codes": list(cfg.footprint.focus_icb_codes),
        "focus_trusts": list(cfg.focus_trusts),
        "core20_max_decile": cfg.deprivation.core20_max_decile,
        "local_quintile_within": cfg.deprivation.local_quintile.within,
        "catchment_year": cfg.catchments.catchment_year,
        "admission_type": cfg.catchments.admission_type,
        "host_icb_relationship": cfg.catchments.host_icb.relationship,
        "host_icb_target_role": cfg.catchments.host_icb.target_role,
        "nhs_geog_vintage": cfg.geography.nhs.vintage,
        "iod_edition": cfg.deprivation.edition,
        "config_hash": cfg.config_hash(),
        "code_hash": hash_tree(Path(lsc_pop.__file__).resolve().parent),
        "bundle_target": n.bundle_target,
        "git_commit": n.git_commit,
    }
    return spark.createDataFrame([row], schema=PARAMS_SCHEMA)


def map_ethnicity(spark, cfg) -> DataFrame:
    return spark.createDataFrame(arrow_safe(outputs.dim_ethnicity(cfg)))


def map_age(spark, cfg) -> DataFrame:
    """Single year → RM032 band, 23-category code, 5-/10-year output bands."""
    classes = load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )
    d = outputs.dim_age(cfg)
    d["rm032_band"] = age_to_code(classes, "rm032_5", cfg.age.max_age).to_numpy()
    d["age23"] = age_to_code(classes, "age_23a", cfg.age.max_age).to_numpy()
    return spark.createDataFrame(arrow_safe(d))


def source_age_map(spark, cfg) -> DataFrame:
    """Roll-forward (ADR-0004, ADR-0017): target age ← pooled 2021 source ages, per variant.

    ``src_band`` is the RM032 band of the first source age (the band fallback, level 1).
    """
    classes = load_census_age_classifications(
        cfg.resolve(cfg.age.census_classifications_file), cfg.age.max_age
    )
    a2b = age_to_code(classes, "rm032_5", cfg.age.max_age)
    rows = []
    for name, (variant, proxy) in SENSITIVITY_VARIANTS.items():
        proxy = proxy if proxy is not None else cfg.rollforward.newborn_proxy_ages
        for target, srcs in enumerate(
            source_ages(variant, cfg.shift_years, cfg.age.max_age, proxy)
        ):
            for s in srcs:
                rows.append((name, target, s, int(a2b[srcs[0]])))
    return spark.createDataFrame(
        arrow_safe(pd.DataFrame(rows, columns=["variant", "target_age", "source_age", "src_band"]))
    )
