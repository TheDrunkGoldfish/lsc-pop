from __future__ import annotations

import gzip
import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest
from conftest import install_raw

from lsc_pop import census
from lsc_pop.mappings import load_ethnicity_mapping
from lsc_pop.provenance import RunContext, read_run_log
from lsc_pop.validate import ValidationFailed

LSOAS = pd.Index(["E01000001", "E01000002"])
BANDS = {1: range(0, 25), 2: range(25, 35), 3: range(35, 50), 4: range(50, 65), 5: range(65, 91)}


@pytest.fixture
def ctx(cfg):
    return RunContext.create(cfg, run_id="t")


def _checks(ctx):
    return {r["check_id"]: r for r in read_run_log(ctx.checks_path)}


# --- synthetic raw tables ------------------------------------------------------------------


def _rm032_csv(value=lambda ls, s, b, e: (e % 3) + b, break_total=False) -> bytes:
    rows = ["GEOGRAPHY_CODE,C2021_ETH_20,C2021_AGE_6,C_SEX,OBS_VALUE,RECORD_COUNT"]
    for ls in LSOAS:
        for b in range(1, 6):
            for s in (1, 2):
                vals = {e: value(ls, s, b, e) for e in range(1, 20)}
                total = sum(vals.values()) + (1 if break_total and b == 1 else 0)
                rows.append(f"{ls},0,{b},{s},{total},0")
                rows += [f"{ls},{e},{b},{s},{v},0" for e, v in vals.items()]
    return ("\n".join(rows) + "\n").encode()


def _rm200_csv(value=lambda ls, s, a: 1 + (a % 4)) -> bytes:
    rows = ["GEOGRAPHY_CODE,C2021_AGE_92,C_SEX,OBS_VALUE,RECORD_COUNT"]
    for ls in LSOAS:
        for s in (1, 2):
            vals = [value(ls, s, a) for a in range(91)]
            rows.append(f"{ls},0,{s},{sum(vals)},0")
            rows += [f"{ls},{a + 1},{s},{v},0" for a, v in enumerate(vals)]
    return ("\n".join(rows) + "\n").encode()


def _ts021_zip(cfg) -> bytes:
    eth = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    cols = {f"Ethnic group: {r.label_19}": r.code_19 for r in eth.itertuples()}
    recs = []
    for ls in [*LSOAS, "W01000001"]:
        rec = {"date": 2021, "geography": ls, "geography code": ls}
        vals = {c: code for c, code in cols.items()}
        rec["Ethnic group: Total: All usual residents"] = sum(vals.values())
        rec["Ethnic group: White"] = 0  # a high-level column, ignored
        rec.update(vals)
        recs.append(rec)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("census2021-ts021-lsoa.csv", pd.DataFrame(recs).to_csv(index=False))
    return buf.getvalue()


def _seed_gz(ltlas, blocked, dim="resident_age_91a", n_age=91, dna=0) -> bytes:
    lines = []
    for b, batch in enumerate([ltlas]):
        obs = []
        for lt in batch:
            if lt in blocked:
                continue
            for e in [-8, *range(1, 20)]:
                for s in (1, 2):
                    ages = range(91) if dim == "resident_age_91a" else range(1, n_age + 1)
                    for a in ages:
                        dims = [{"dimension_id": "ltla", "option_id": lt},
                                {"dimension_id": "ethnic_group_tb_20b", "option_id": str(e)},
                                {"dimension_id": "sex", "option_id": str(s)},
                                {"dimension_id": dim, "option_id": str(a)}]  # fmt: skip
                        obs.append(
                            {"dimensions": dims, "observation": dna if e == -8 else 1 + e % 2}
                        )
        lines.append({"batch": b, "requested": batch, "blocked": blocked,
                      "response": {"observations": obs}})  # fmt: skip
    return gzip.compress("\n".join(json.dumps(x) for x in lines).encode())


# --- loaders -------------------------------------------------------------------------------


def test_load_rm032(project_copy, ctx):
    install_raw(project_copy, "S1", census.RM032[1], _rm032_csv())
    df = census.load_rm032(ctx, LSOAS)
    assert list(df.columns) == ["lsoa21cd", "sex", "band", "eth19", "population"]
    assert len(df) == 2 * 5 * 2 * 19
    assert set(df["sex"]) == {"F", "M"}
    assert df["eth19"].min() == 1 and df["eth19"].max() == 19
    c = _checks(ctx)
    assert c["CEN-01"]["passed"] and c["CEN-02"]["passed"]


def test_rm032_does_not_apply_nonzero_fails(project_copy, ctx):
    install_raw(project_copy, "S1", census.RM032[1], _rm032_csv(break_total=True))
    with pytest.raises(ValidationFailed, match="CEN-01"):
        census.load_rm032(ctx, LSOAS)


def test_rm032_missing_lsoa_fails(project_copy, ctx):
    install_raw(project_copy, "S1", census.RM032[1], _rm032_csv())
    with pytest.raises(ValidationFailed, match="CEN-02"):
        census.load_rm032(ctx, pd.Index([*LSOAS, "E01000003"]))


def test_load_rm200_age_is_code_minus_one(project_copy, ctx):
    install_raw(project_copy, "S2", census.RM200[1], _rm200_csv(lambda ls, s, a: a))
    df = census.load_rm200(ctx, LSOAS)
    assert df["age"].min() == 0 and df["age"].max() == 90
    assert (df["population"] == df["age"]).all()  # value = age, so the shift is exactly right
    assert _checks(ctx)["CEN-03"]["passed"]


def test_load_ts021(project_copy, ctx, cfg):
    install_raw(project_copy, "S4", census.TS021[1], _ts021_zip(cfg))
    df = census.load_ts021(ctx, LSOAS)
    assert len(df) == 2 * 19  # Wales dropped
    assert (df["population"] == df["eth19"]).all()
    assert _checks(ctx)["CEN-05"]["passed"]


def test_load_seed_records_blocked(project_copy, ctx):
    ltlas = ["E06000001", "E06000002", "E06000053"]
    install_raw(project_copy, "S3", census.SEED91[1], _seed_gz(ltlas, ["E06000053"]))
    df, blocked = census.load_seed(ctx, census.SEED91, pd.Index(ltlas))
    assert blocked == ["E06000053"]
    assert set(df["ltla21cd"]) == {"E06000001", "E06000002"}
    assert len(df) == 2 * 19 * 2 * 91
    c = _checks(ctx)
    assert c["CEN-07-age_91a"]["passed"] and c["CEN-08-age_91a"]["passed"]


def test_seed_does_not_apply_nonzero_fails(project_copy, ctx):
    install_raw(project_copy, "S3", census.SEED91[1], _seed_gz(["E06000001"], [], dna=1))
    with pytest.raises(ValidationFailed, match="CEN-07"):
        census.load_seed(ctx, census.SEED91, pd.Index(["E06000001"]))


# --- reconciliation ------------------------------------------------------------------------


def _tidy_rm032(value):
    return pd.DataFrame(
        [(ls, s, b, e, value(ls, s, b, e)) for ls in LSOAS for s in "FM" for b in BANDS
         for e in range(1, 20)],
        columns=["lsoa21cd", "sex", "band", "eth19", "population"],
    )  # fmt: skip


def _tidy_rm200(value):
    return pd.DataFrame(
        [(ls, s, a, value(ls, s, a)) for ls in LSOAS for s in "FM" for a in range(91)],
        columns=["lsoa21cd", "sex", "age", "population"],
    )


def _seed(value=lambda lt, e, s, a: 1.0):
    return pd.DataFrame(
        [("E07000001", e, s, a, value("E07000001", e, s, a)) for e in range(1, 20) for s in "FM"
         for a in range(91)],
        columns=["ltla21cd", "eth19", "sex", "age", "population"],
    )  # fmt: skip


LOOKUP = pd.DataFrame({"lsoa21cd": LSOAS, "ltla21cd": ["E07000001", "E07000001"]})


def _band_sums(m, kind):
    return m[m["kind"] == kind].groupby(["lsoa21cd", "sex", "band"])["population"].sum()


def test_reconcile_rm200_source_keeps_ages_scales_ethnicity(ctx):
    rm032 = _tidy_rm032(lambda ls, s, b, e: 2 if e == 13 else (1 if e == 3 else 0))  # 3 per band
    rm200 = _tidy_rm200(lambda ls, s, a: 1)
    rec = census.reconcile_margins(ctx, rm032, rm200, _seed(), LOOKUP, source="rm200")
    m = rec.margins
    ages = m[m["kind"] == "age"].set_index(["lsoa21cd", "sex", "key"])["population"]
    assert (ages == 1).all()  # RM200 unchanged
    eth = m[(m["kind"] == "eth19") & (m["band"] == 2)].set_index(["lsoa21cd", "sex", "key"])[
        "population"
    ]
    # band 2 has 10 single years -> T = 10; RM032 3 people in ratio 2:1 -> 6.667 and 3.333
    assert eth.xs(13, level="key").iloc[0] == pytest.approx(20 / 3)
    assert eth.xs(3, level="key").iloc[0] == pytest.approx(10 / 3)
    pd.testing.assert_series_equal(_band_sums(m, "eth19"), _band_sums(m, "age"))
    assert rec.summary["rm200_adjustment"]["max_abs"] == 0
    c = _checks(ctx)
    assert c["CEN-10"]["passed"] and c["CEN-11"]["passed"]
    assert not c["CEN-12"]["passed"]  # band 5 adjusted 3 -> 26: flagged (soft only)
    assert c["CEN-12"]["metrics"]["bands_flagged"] > 0


def test_reconcile_mean_source(ctx):
    rm032 = _tidy_rm032(lambda ls, s, b, e: 1 if e == 1 else 0)  # 1 per band
    rm200 = _tidy_rm200(lambda ls, s, a: 3 if a in (0, 30, 40, 55, 70) else 0)  # 3 per band
    rec = census.reconcile_margins(ctx, rm032, rm200, _seed(), LOOKUP, source="mean")
    assert _band_sums(rec.margins, "eth19").unique().tolist() == [2.0]
    assert _band_sums(rec.margins, "age").unique().tolist() == [2.0]


def test_eth_fallback_uses_pooled_lsoa_mix(ctx):
    # RM032 has nobody in band 1 for E01000001/F, but RM200 does: pooled mix over bands 2-5.
    def v032(ls, s, b, e):
        if ls == "E01000001" and s == "F" and b == 1:
            return 0
        return 3 if e == 4 else (1 if e == 13 else 0)

    rm200 = _tidy_rm200(lambda ls, s, a: 1)
    rec = census.reconcile_margins(ctx, _tidy_rm032(v032), rm200, _seed(), LOOKUP, source="rm200")
    assert rec.summary["bands_eth_fallback"] == 1
    assert rec.summary["persons_eth_fallback"] == 25
    m = rec.margins.set_index(["lsoa21cd", "sex", "band", "kind", "key"])["population"]
    assert m[("E01000001", "F", 1, "eth19", 4)] == pytest.approx(25 * 0.75)
    assert m[("E01000001", "F", 1, "eth19", 13)] == pytest.approx(25 * 0.25)
    assert _checks(ctx)["CEN-10"]["passed"]


def test_age_fallback_uses_seed_shape(ctx):
    # RM200 has nobody aged 25-34 for E01000002/M; RM032 has 4 there. Source rm032 keeps them,
    # and the seed's age shape (2x weight at age 30) spreads them over 25..34.
    rm032 = _tidy_rm032(lambda ls, s, b, e: 4 if e == 1 else 0)
    rm200 = _tidy_rm200(
        lambda ls, s, a: 0 if (ls == "E01000002" and s == "M" and 25 <= a <= 34) else 1
    )
    seed = _seed(lambda lt, e, s, a: 2.0 if a == 30 else 1.0)
    rec = census.reconcile_margins(ctx, rm032, rm200, seed, LOOKUP, source="rm032")
    assert rec.summary["bands_age_fallback"] == 1
    m = rec.margins.set_index(["lsoa21cd", "sex", "band", "kind", "key"])["population"]
    assert m[("E01000002", "M", 2, "age", 30)] == pytest.approx(4 * 2 / 11)
    assert m[("E01000002", "M", 2, "age", 25)] == pytest.approx(4 * 1 / 11)
    assert _checks(ctx)["CEN-10"]["passed"]


def test_rm200_zero_band_zeroes_ethnicity_and_reports_it(ctx):
    rm032 = _tidy_rm032(lambda ls, s, b, e: 1 if e == 1 else 0)
    rm200 = _tidy_rm200(lambda ls, s, a: 0 if a >= 65 else 1)
    rec = census.reconcile_margins(ctx, rm032, rm200, _seed(), LOOKUP, source="rm200")
    assert rec.summary["persons_dropped_rm032_zeroed"] == 4  # 2 LSOAs x 2 sexes x 1 person
    assert _band_sums(rec.margins, "eth19").xs(5, level="band").eq(0).all()


def test_margin_source_must_be_valid(ctx):
    with pytest.raises(ValueError, match="margin_source"):
        census.reconcile_margins(ctx, _tidy_rm032(lambda *a: 1), _tidy_rm200(lambda *a: 1),
                                 _seed(), LOOKUP, source="tbd")  # fmt: skip


def test_reconciliation_is_deterministic(ctx):
    rm032 = _tidy_rm032(lambda ls, s, b, e: (e * 7 + b) % 5)
    rm200 = _tidy_rm200(lambda ls, s, a: (a * 3) % 4 + 1)
    a = census.reconcile_margins(ctx, rm032, rm200, _seed(), LOOKUP, source="rm200").margins
    b = census.reconcile_margins(ctx, rm032, rm200, _seed(), LOOKUP, source="rm200").margins
    pd.testing.assert_frame_equal(a, b)
    assert np.isfinite(a["population"]).all()
