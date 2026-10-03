from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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
        ("lsoa21_code", "sex", "age", "eth19"),
        {"lsoa21_code": ["E01", "E02", "E03"], "sex": ["F", "M"], "age": [0, 1], "eth19": [1, 2]},
    )
    icb = pd.Series(["X", "Y", "X"], index=["E01", "E02", "E03"])
    rows = outputs.write_fact_csv_by_icb(cube, icb, tmp_path, 2024)
    assert rows == {"X": 16, "Y": 8}
    x = pd.read_csv(tmp_path / "icb=X.csv")
    assert set(x["lsoa21_code"]) == {"E01", "E03"}
    assert np.isclose(x["population"].sum(), data[[0, 2]].sum())
    r = x[(x["lsoa21_code"] == "E03") & (x["sex"] == "M") & (x["age"] == 1) & (x["eth19"] == 2)]
    assert np.isclose(r["population"].iloc[0], data[2, 1, 1, 1])
    assert set(x["reference_year"]) == {2024} and "variant" not in x.columns


def test_schema_template_formats():
    sql = outputs.SCHEMA_SQL.read_text().format(ref="mid-2024", variant="cohort", run_id="r")
    assert "CREATE TABLE fact_population" in sql and "{" not in sql


def _lookup():
    return pd.DataFrame(
        {
            "lsoa21_code": ["L1", "L2", "L3"],
            "lsoa21_name": ["a", "b", "c"],
            "msoa21_code": ["M1", "M1", "M2"],
            "msoa21_name": ["m1", "m1", "m2"],
            "ltla21_code": ["T1", "T1", "T2"],
            "ltla21_name": ["t1", "t1", "t2"],
            "rgn21_code": ["R1", "R1", "R1"],
            "rgn21_name": ["r1", "r1", "r1"],
            "lad_code": ["D1", "D1", "D2"],
            "lad_name": ["d1", "d1", "d2"],
            "sicbl_code": ["S1", "S1", "S2"],
            "sicbl_ods_code": ["s1", "s1", "s2"],
            "sicbl_name": ["sub1", "sub1", "sub2"],
            "icb_code": ["I1", "I1", "I2"],
            "icb_ods_code": ["i1", "i1", "i2"],
            "icb_name": ["icb1", "icb1", "icb2"],
            "nhser_code": ["N1", "N1", "N1"],
            "nhser_ods_code": ["n1", "n1", "n1"],
            "nhser_name": ["nhs1", "nhs1", "nhs1"],
            "in_footprint": [True, True, True],
            "in_focus_icb": [True, True, False],
        }
    )


def test_geography_dims_have_one_row_per_code_and_parent_keys():
    geo = outputs.geography_dims(_lookup())
    assert set(geo) == set(outputs.GEOGRAPHY_DIMS)
    for name, d in geo.items():
        assert d[outputs.GEOGRAPHY_DIMS[name][0]].is_unique, name
    assert geo["dim_icb"]["icb_code"].tolist() == ["I1", "I2"]
    assert geo["dim_icb"].set_index("icb_code")["is_focus"].to_dict() == {"I1": True, "I2": False}
    assert geo["dim_sub_icb"].set_index("sicbl_code")["icb_code"].to_dict() == {
        "S1": "I1",
        "S2": "I2",
    }
    assert geo["dim_msoa"].set_index("msoa21_code")["ltla21_code"].to_dict() == {
        "M1": "T1",
        "M2": "T2",
    }
    # names are held once per level, not on every LSOA
    assert "icb_name" not in outputs.LSOA_GEOGRAPHY_COLUMNS


def test_geography_dims_reject_inconsistent_attributes():
    lk = _lookup()
    lk.loc[1, "icb_name"] = "a different name for I1"
    with pytest.raises(ValueError, match="dim_icb"):
        outputs.geography_dims(lk)


def test_every_fk_link_has_a_dimension():
    assert {k for _, k in outputs.FK_LINKS} <= set(outputs.LEVEL_TABLE)
    assert set(outputs.LEVEL_TABLE.values()) == set(outputs.GEOGRAPHY_DIMS)
