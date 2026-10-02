"""Loaders and validators for the mapping CSVs in ``config/mappings/``.

Each loader validates the file's structure and fails loudly, so a malformed mapping can't
silently change the numbers.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

N_ETHNIC_GROUPS = 19


def load_ethnicity_mapping(path: Path) -> pd.DataFrame:
    """Census 2021 19 tick-box groups -> 5 high-level groups -> 6-group NHS-style aggregation."""
    df = pd.read_csv(path, dtype={"code_19": int})
    required = ["code_19", "label_19", "code_5", "label_5", "code_6", "label_6"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    if df["code_19"].duplicated().any():
        raise ValueError(f"{path}: duplicate code_19 values")
    if sorted(df["code_19"]) != list(range(1, N_ETHNIC_GROUPS + 1)):
        raise ValueError(f"{path}: code_19 must be exactly 1..{N_ETHNIC_GROUPS}")
    if df[required].isna().any().any():
        raise ValueError(f"{path}: blank values in mapping")
    for code, label in (("code_5", "label_5"), ("code_6", "label_6")):
        if (df.groupby(code)[label].nunique() != 1).any():
            raise ValueError(f"{path}: {code} maps to more than one {label}")
    return df[required]


def _check_tiles(path: Path, df: pd.DataFrame, group: str, label: str, max_age: int) -> None:
    for name, g in df.groupby(group, sort=False):
        g = g.sort_values("age_min")
        ages = [
            a for lo, hi in zip(g["age_min"], g["age_max"], strict=True) for a in range(lo, hi + 1)
        ]
        if ages != list(range(0, max_age + 1)):
            raise ValueError(f"{path}: band set {name!r} does not tile ages 0..{max_age} exactly")
        if g[label].duplicated().any():
            raise ValueError(f"{path}: band set {name!r} has duplicate labels")


def load_age_bands(path: Path, max_age: int, band_sets: list[str] | None = None) -> pd.DataFrame:
    """Age bands. Each band set must tile 0..max_age exactly (no gaps, no overlaps)."""
    df = pd.read_csv(path, dtype={"band_set": str, "band_label": str})
    _check_tiles(path, df, "band_set", "band_label", max_age)
    if band_sets is not None:
        unknown = set(band_sets) - set(df["band_set"])
        if unknown:
            raise ValueError(f"{path}: unknown band sets requested: {sorted(unknown)}")
        df = df[df["band_set"].isin(band_sets)]
    return df.reset_index(drop=True)


def load_census_age_classifications(path: Path, max_age: int) -> pd.DataFrame:
    """Census age classifications by code (RM032 5 bands, ONS API 23 categories).

    Each classification must tile 0..max_age exactly.
    """
    df = pd.read_csv(path, dtype={"classification": str, "label": str})
    _check_tiles(path, df, "classification", "code", max_age)
    return df


def age_to_code(classes: pd.DataFrame, classification: str, max_age: int) -> pd.Series:
    """Series indexed by single year of age 0..max_age giving the classification code."""
    c = classes[classes["classification"] == classification]
    if c.empty:
        raise KeyError(classification)
    out = {a: int(r.code) for r in c.itertuples() for a in range(r.age_min, r.age_max + 1)}
    return pd.Series(out, name=classification).sort_index()
