from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from lsc_pop import catchments, deprivation
from lsc_pop.ods import read_ods_sheets, sheet_to_frame
from lsc_pop.provenance import RunContext, read_run_log
from lsc_pop.validate import ValidationFailed


@pytest.fixture
def ctx(cfg):
    return RunContext.create(cfg, run_id="t")


# --- ODS reader ----------------------------------------------------------------------------


def _ods(sheets: dict[str, list[list]]) -> bytes:
    t = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    tx = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    o = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    parts = [
        f'<office:document-content xmlns:office="{o}" xmlns:table="{t}" xmlns:text="{tx}">'
        "<office:body><office:spreadsheet>"
    ]
    for name, rows in sheets.items():
        parts.append(f'<table:table table:name="{name}">')
        for row in rows:
            parts.append("<table:table-row>")
            for v in row:
                if isinstance(v, (int, float)):
                    parts.append(
                        f'<table:table-cell office:value-type="float" office:value="{v}">'
                        f"<text:p>{v}</text:p></table:table-cell>"
                    )
                else:
                    lines = "".join(f"<text:p>{x}</text:p>" for x in str(v).split("\n"))
                    parts.append(f"<table:table-cell>{lines}</table:table-cell>")
            parts.append('<table:table-cell table:number-columns-repeated="16000"/>')
            parts.append("</table:table-row>")
        parts.append('<table:table-row table:number-rows-repeated="1000000">')
        parts.append("<table:table-cell/></table:table-row>")
        parts.append("</table:table>")
    parts.append("</office:spreadsheet></office:body></office:document-content>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", "".join(parts))
    return buf.getvalue()


def test_ods_reader_selected_sheets_and_padding(tmp_path):
    p = tmp_path / "x.ods"
    p.write_bytes(
        _ods(
            {"A": [["title"], ["note"], ["Trust\ncode", "Value"], ["RXL", 0.5]], "B": [["ignored"]]}
        )
    )
    out = read_ods_sheets(p, ["A"])
    assert list(out) == ["A"]
    df = sheet_to_frame(out["A"], header_row=2)
    assert list(df.columns) == ["Trust code", "Value"]
    assert df.iloc[0].tolist() == ["RXL", "0.5"]
    with pytest.raises(KeyError, match="C"):
        read_ods_sheets(p, ["C"])


# --- deprivation ---------------------------------------------------------------------------


def test_iod_header_mapping_handles_truncation_and_commas():
    f = deprivation._standard_name
    assert f("Index of Multiple Deprivation (IMD) Rank (where 1 is most deprived)") == "imd_rank"
    assert f("Education, Skills and Training Score") == "education_score"
    assert (
        f("Education\n Skills and Training Decile (where 1 is most deprived 10% of LSOAs)")
        == "education_decile"
    )
    assert f(
        "Children and Young People Sub-domain Decile (where 1 is most deprived 10% of LSO"
    ) == ("sub_children_young_people_decile")
    assert f("Income Deprivation Affecting Children Index (IDACI) Score (rate)") == "idaci_score"
    assert f("Income Score (rate)") == "income_score"
    assert f("Total population: mid 2022") is None


def test_local_quintile_population_weighted():
    # One group, 10 LSOAs ranked 1..10 (1 = most deprived), populations uneven.
    rank = pd.Series(range(1, 11))
    pop = pd.Series([50, 50, 100, 100, 100, 100, 100, 100, 100, 200])
    q = deprivation.local_quintile(rank, pop, pd.Series(["g"] * 10))
    # cumulative midpoints / 1000: .025 .075 .175 .275 .375 .475 .575 .675 .775 .9
    assert q.tolist() == [1, 1, 1, 2, 2, 3, 3, 4, 4, 5]
    share = pop.groupby(q).sum() / pop.sum()
    assert share.between(0.1, 0.3).all()


def test_local_quintile_respects_groups_and_order():
    rank = pd.Series([4, 1, 3, 2, 6, 5])
    pop = pd.Series([1, 1, 1, 1, 1, 1])
    grp = pd.Series(["a", "a", "a", "a", "b", "b"])
    q = deprivation.local_quintile(rank, pop, grp)
    assert q[1] == 1 and q[0] == 5  # within 'a', rank 1 is most deprived, rank 4 least
    assert q[5] == 2 and q[4] == 4  # 'b' ranked separately: midpoints .25 and .75


# --- catchments ----------------------------------------------------------------------------


def _t2(rows):
    return pd.DataFrame(
        rows, columns=["Trust code", "MSOA21CD", catchments.P_COL, "First past the post (FPTP)"]
    )


LOOKUP = pd.DataFrame(
    {
        "lsoa21cd": ["E01000001", "E01000002", "E01000003"],
        "msoa21cd": ["E02000001", "E02000001", "E02000002"],
    }
)


def test_bridge_published_plus_unassigned_and_rescaled(ctx):
    t2 = _t2(
        [
            ("RXL", "E02000001", 0.6, "TRUE"),
            ("RXN", "E02000001", 0.3, "FALSE"),
            ("RXN", "E02000002", 1.0, "TRUE"),
        ]
    )
    b = catchments.build_bridge(ctx, t2, LOOKUP)
    l1 = b[b["lsoa21cd"] == "E01000001"].set_index("trust_code")
    assert l1.loc["UNASSIGNED", "proportion_published"] == pytest.approx(0.1)
    assert l1.loc["RXL", "proportion_rescaled"] == pytest.approx(0.6 / 0.9)
    assert l1.loc["UNASSIGNED", "proportion_rescaled"] == 0
    assert "UNASSIGNED" not in set(b.loc[b["lsoa21cd"] == "E01000003", "trust_code"])
    sums = b.groupby("lsoa21cd")[["proportion_published", "proportion_rescaled"]].sum()
    np.testing.assert_allclose(sums.to_numpy(), 1)
    assert bool(l1.loc["RXL", "fptp"]) and not bool(l1.loc["RXN", "fptp"])


def test_bridge_fails_on_missing_msoa(ctx):
    t2 = _t2([("RXL", "E02000001", 1.0, "TRUE")])
    with pytest.raises(ValidationFailed, match="CAT-01"):
        catchments.build_bridge(ctx, t2, LOOKUP)


def test_bridge_fails_if_proportions_exceed_one(ctx):
    t2 = _t2(
        [
            ("RXL", "E02000001", 0.7, "TRUE"),
            ("RXN", "E02000001", 0.4, "FALSE"),
            ("RXN", "E02000002", 1.0, "TRUE"),
        ]
    )
    with pytest.raises(ValidationFailed, match="CAT-03"):
        catchments.build_bridge(ctx, t2, LOOKUP)


def test_trust_totals_reconcile(ctx):
    t2 = _t2(
        [
            ("RXL", "E02000001", 0.6, "TRUE"),
            ("RXN", "E02000001", 0.3, "FALSE"),
            ("RXN", "E02000002", 1.0, "TRUE"),
        ]
    )
    b = catchments.build_bridge(ctx, t2, LOOKUP)
    pop = pd.Series([100.0, 50.0, 10.0], index=LOOKUP["lsoa21cd"])
    eth5 = pd.DataFrame(
        {"A": [10.0, 0, 5], "B": 0.0, "M": 0.0, "O": 0.0, "W": [90.0, 50, 5]},
        index=LOOKUP["lsoa21cd"],
    )
    frames = {
        "Trust_analysis": pd.DataFrame(
            {"Trust code": ["RXL", "RXN"], "Catchment population": [90, 55]}
        ),
        "Ethnicity": pd.DataFrame(
            {
                "Trust code": ["RXL"] * 2,
                "Selection method": ["All (5% and above)", "First past the post"],
                "Percentage Asian": [0.1, 0.1],
                "Percentage black": 0.0,
                "Percentage mixed": 0.0,
                "Percentage white": [0.9, 0.9],
                "Percentage other": 0.0,
            }
        ),
        "Deprivation": pd.DataFrame({"Trust code": ["RXL", "RXN"], "IMD score": [20.0, 30.0]}),
    }
    imd = pd.Series([20.0, 20.0, 40.0], index=LOOKUP["lsoa21cd"])
    out = catchments.compare_with_ohid(ctx, frames, b, pop, eth5, imd)
    t = out["totals"].set_index("trust_code")
    assert t.loc["RXL", "modelled_published"] == pytest.approx(0.6 * 150)
    assert t.loc["RXN", "modelled_rescaled"] == pytest.approx(150 / 3 + 10)
    checks = {r["check_id"]: r for r in read_run_log(ctx.checks_path)}
    assert checks["CAT-07"]["passed"]
    assert checks["CAT-07"]["metrics"]["unassigned"] == pytest.approx(15)
    e = out["ethnicity"].set_index(["trust_code", "selection_method"])
    assert e.loc[("RXL", "First past the post"), "modelled_pct_A"] == pytest.approx(10 / 150 * 100)
    i = out["imd"].set_index("trust_code")
    assert i.loc["RXN", "modelled_imd_score"] == pytest.approx(
        (0.3 * 150 * 20 + 10 * 40) / (0.3 * 150 + 10)
    )


def test_ohid_diagnostic_identifies_coarse_geography(ctx):
    # 4 LSOAs, 2 ICBs. "OHID" figures use the ICB-level ethnic mix, so the diagnostic picks icb_cd.
    lk = pd.DataFrame(
        {
            "lsoa21cd": ["E01", "E02", "E03", "E04"],
            "msoa21cd": ["M1", "M2", "M3", "M4"],
            "ltla21cd": ["L1", "L2", "L3", "L4"],
            "sicbl_cd": ["S1", "S2", "S3", "S4"],
            "icb_cd": ["I1", "I1", "I2", "I2"],
            "nhser_cd": ["N", "N", "N", "N"],
        }
    )
    eth5 = pd.DataFrame(
        {"A": [90.0, 0, 50, 0], "B": 0.0, "M": 0.0, "O": 0.0, "W": [10.0, 100, 50, 100]},
        index=lk["lsoa21cd"],
    )
    pop = eth5.sum(axis=1)
    bridge = pd.DataFrame(
        {
            "lsoa21cd": ["E01", "E02", "E03", "E04"],
            "msoa21cd": ["M1", "M2", "M3", "M4"],
            "trust_code": ["T1", "T2", "T2", "T2"],
            "proportion_published": [1.0, 1.0, 1.0, 1.0],
            "proportion_rescaled": 1.0,
            "fptp": True,
        }
    )
    # ICB mix: I1 = 45% A, I2 = 25% A. T1 gets E01 (I1) -> 45%; T2 gets E02 (I1) + E03,E04 (I2):
    # (45 + 25 + 25) / 3 = 31.67%
    ohid = pd.DataFrame(
        {
            "trust_code": ["T1", "T2"],
            "selection_method": "All (5% and above)",
            "ohid_pct_A": [45.0, 95 / 3],
            "ohid_pct_B": 0.0,
            "ohid_pct_M": 0.0,
            "ohid_pct_O": 0.0,
            "ohid_pct_W": [55.0, 100 - 95 / 3],
        }
    )
    out = catchments.ohid_5pct_diagnostic(ctx, bridge, lk, pop, eth5, ohid)
    best = out.loc[out["mean_abs_diff_pp"].idxmin(), "ethnic_mix_level"]
    assert best == "icb_cd"
    assert out.set_index("ethnic_mix_level").loc["icb_cd", "mean_abs_diff_pp"] == pytest.approx(
        0, abs=1e-9
    )
