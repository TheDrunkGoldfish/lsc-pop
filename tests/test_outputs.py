from __future__ import annotations

import numpy as np
import pandas as pd

from lsc_pop import outputs
from lsc_pop.provenance import Cube


def test_dim_age(cfg):
    d = outputs.dim_age(cfg)
    assert len(d) == 91 and d["age"].tolist() == list(range(91))
    row = d.set_index("age").loc[37]
    assert (row["age_5yr"], row["age_10yr"], row["age_5yr_sort"]) == ("35-39", "30-39", 35)
    assert d.set_index("age").loc[90, "age_label"] == "90+"
    assert d.set_index("age").loc[90, "age_5yr"] == "90+"
    assert d.set_index("age").loc[24, "census_band_rm032"] == "Aged 24 years and under"


def test_dim_ethnicity(cfg):
    d = outputs.dim_ethnicity(cfg)
    assert d["eth19"].tolist() == list(range(1, 20))
    assert d.set_index("eth19").loc[13, "code_6"] == "WB"


def test_fact_csv_split_by_icb(tmp_path):
    rng = np.random.default_rng(0)
    data = rng.uniform(size=(3, 2, 2, 2))
    cube = Cube(
        data,
        ("lsoa21cd", "sex", "age", "eth19"),
        {"lsoa21cd": ["E01", "E02", "E03"], "sex": ["F", "M"], "age": [0, 1], "eth19": [1, 2]},
    )
    icb = pd.Series(["X", "Y", "X"], index=["E01", "E02", "E03"])
    rows = outputs.write_fact_csv_by_icb(cube, icb, tmp_path, 2024)
    assert rows == {"X": 16, "Y": 8}
    x = pd.read_csv(tmp_path / "icb=X.csv")
    assert set(x["lsoa21cd"]) == {"E01", "E03"}
    assert np.isclose(x["population"].sum(), data[[0, 2]].sum())
    r = x[(x["lsoa21cd"] == "E03") & (x["sex"] == "M") & (x["age"] == 1) & (x["eth19"] == 2)]
    assert np.isclose(r["population"].iloc[0], data[2, 1, 1, 1])
    assert set(x["reference_year"]) == {2024} and "variant" not in x.columns


def test_schema_template_formats():
    sql = outputs.SCHEMA_SQL.read_text().format(ref="mid-2024", variant="cohort", run_id="r")
    assert "CREATE TABLE fact_population" in sql and "{" not in sql
