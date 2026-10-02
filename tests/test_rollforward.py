from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from conftest import install_raw

from lsc_pop import rollforward as rf
from lsc_pop.base import DIMS, ETH, SEXES
from lsc_pop.provenance import Cube, RunContext, read_run_log
from lsc_pop.validate import ValidationFailed

LSOAS = ["E01000001", "E01000002", "E01000003"]


@pytest.fixture
def ctx(cfg):
    return RunContext.create(cfg, run_id="t")


def test_source_ages_cohort():
    src = rf.source_ages("cohort", 3, 90, [0])
    assert src[0] == src[1] == src[2] == [0]  # born after Census day
    assert src[3] == [0] and src[50] == [47] and src[89] == [86]
    assert src[90] == [87, 88, 89, 90]  # 90+ pools the 2021 cohorts aged 87+
    assert rf.source_ages("cohort", 4, 90, [0, 1])[3] == [0, 1]


def test_source_ages_static():
    assert rf.source_ages("static", 3, 90, [0]) == [[a] for a in range(91)]


def _base(rng, zero_cells=()):
    b = rng.uniform(0, 5, (len(LSOAS), 2, 91, 19))
    for idx in zero_cells:
        b[idx] = 0
    return b


def test_shares_sum_to_one_and_follow_cohort(ctx):
    rng = np.random.default_rng(0)
    b = _base(rng)
    src = rf.source_ages("cohort", 3, 90, [0])
    shares, level = rf.compute_shares(ctx.cfg, b, np.array([0, 0, 1]), src)
    np.testing.assert_allclose(shares.sum(3), 1)
    np.testing.assert_allclose(shares[1, 0, 50], b[1, 0, 47] / b[1, 0, 47].sum())
    pooled = b[2, 1, 87:91].sum(0)
    np.testing.assert_allclose(shares[2, 1, 90], pooled / pooled.sum())
    assert (level == 0).all()


def test_shares_fallback_hierarchy(ctx):
    rng = np.random.default_rng(1)
    b = _base(rng)
    b[0, 0, 47] = 0  # nobody aged 47 (F) in LSOA 0 in 2021 -> band 50-64? no: band of 47 = 35-49
    b[1, 1] = 0  # LSOA 1 has no males at all -> all-ages fallback (level 2) fails -> level 3
    src = rf.source_ages("cohort", 3, 90, [0])
    shares, level = rf.compute_shares(ctx.cfg, b, np.array([0, 0, 1]), src)
    assert level[0, 0, 50] == 1
    band = b[0, 0, 35:50].sum(0)
    np.testing.assert_allclose(shares[0, 0, 50], band / band.sum())
    assert (level[1, 1] == 3).all()
    allp = b[1].sum((0, 1))
    np.testing.assert_allclose(shares[1, 1, 10], allp / allp.sum())
    np.testing.assert_allclose(shares.sum(3), 1)


def test_ltla_fallback_when_lsoa_empty(ctx):
    rng = np.random.default_rng(2)
    b = _base(rng)
    b[2] = 0  # LSOA 2 empty in 2021 (e.g. new development): LTLA level
    shares, level = rf.compute_shares(
        ctx.cfg, b, np.array([0, 1, 1]), rf.source_ages("static", 3, 90, [0])
    )
    assert (level[2] == 4).all()
    np.testing.assert_allclose(shares[2, 0, 30], b[1, 0, 30] / b[1, 0, 30].sum())


def _cube(b):
    return Cube(b, DIMS, {"lsoa21cd": LSOAS, "sex": SEXES, "age": list(range(91)), "eth19": ETH})


def test_roll_forward_sums_exactly_to_mye(ctx):
    rng = np.random.default_rng(3)
    b = _base(rng)
    mye = rng.integers(0, 30, (3, 2, 91)).astype(float)
    est, shares, level, fb = rf.roll_forward(ctx, _cube(b), mye, np.array([0, 0, 1]), "cohort")
    rf.validate_estimates(ctx, est, shares, mye, fb, "cohort")
    np.testing.assert_allclose(est.sum(3), mye, atol=1e-12)
    checks = {r["check_id"]: r for r in read_run_log(ctx.checks_path)}
    assert all(checks[c]["passed"] for c in ("ROL-05", "ROL-06", "ROL-07"))
    static = rf.roll_forward(ctx, _cube(b), mye, np.array([0, 0, 1]), "static")[0]
    assert not np.allclose(static, est)


def test_validate_catches_bad_estimates(ctx):
    mye = np.ones((3, 2, 91))
    shares = np.full((3, 2, 91, 19), 1 / 19)
    est = mye[..., None] * shares
    est[0, 0, 0, 0] += 1
    with pytest.raises(ValidationFailed, match="ROL-05"):
        rf.validate_estimates(ctx, est, shares, mye, {}, "cohort")


def _mye_xlsx(sheet="Mid-2024 LSOA 2021", total_off=0) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(3):
        ws.append(["title row"])
    cols = [f"{s}{a}" for s in SEXES for a in range(91)]
    ws.append(
        ["LAD 2023 Code", "LAD 2023 Name", "LSOA 2021 Code", "LSOA 2021 Name", "Total", *cols]
    )
    for i, ls in enumerate([*LSOAS, "W01000001"]):
        vals = [(i + a) % 7 for a in range(182)]
        ws.append(["E06", "x", ls, "n", sum(vals) + total_off, *vals])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_load_mye(project_copy, ctx):
    install_raw(project_copy, "S5", ctx.cfg.mye.file, _mye_xlsx())
    arr = rf.load_mye(ctx, LSOAS)
    assert arr.shape == (3, 2, 91)
    assert arr[1, 0, 0] == 1 and arr[1, 1, 0] == (1 + 91) % 7  # F0 then M0 of LSOA index 1
    checks = {r["check_id"]: r for r in read_run_log(ctx.checks_path)}
    assert checks["ROL-01"]["passed"] and checks["ROL-02"]["passed"]


def test_load_mye_wrong_sheet_is_actionable(project_copy, ctx):
    install_raw(project_copy, "S5", ctx.cfg.mye.file, _mye_xlsx(sheet="Mid-2025 LSOA 2021"))
    with pytest.raises(KeyError, match="config.mye"):
        rf.load_mye(ctx, LSOAS)


def test_load_mye_total_mismatch_fails(project_copy, ctx):
    install_raw(project_copy, "S5", ctx.cfg.mye.file, _mye_xlsx(total_off=1))
    with pytest.raises(ValidationFailed, match="ROL-02"):
        rf.load_mye(ctx, LSOAS)


def test_summarise_shapes(ctx):
    rng = np.random.default_rng(4)
    est = rng.uniform(size=(3, 2, 91, 19))
    lk = pd.DataFrame({"lsoa21cd": LSOAS, "in_focus_icb": [True, False, True]})
    s = rf.summarise(ctx.cfg, est, lk, LSOAS)
    eng = s[s["geography"] == "England"]["population"].sum()
    foc = s[s["geography"] == "Focus ICB"]["population"].sum()
    assert eng == pytest.approx(est.sum()) and foc == pytest.approx(est[[0, 2]].sum())
    assert set(s["age_band"]) == {f"{b}-{b + 9}" for b in range(0, 90, 10)} | {"90+"}
