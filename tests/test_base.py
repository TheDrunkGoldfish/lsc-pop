from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lsc_pop import base
from lsc_pop.provenance import Cube, RunContext, read_cube, write_cube

AGES = list(range(91))


@pytest.fixture
def ctx(cfg):
    return RunContext.create(cfg, run_id="t")


def _seed91(ltlas, value=lambda lt, e, s, a: 1 + (e % 3) * (a % 5)):
    return pd.DataFrame(
        [
            (lt, e, s, a, value(lt, e, s, a))
            for lt in ltlas
            for e in base.ETH
            for s in "FM"
            for a in AGES
        ],
        columns=["ltla21cd", "eth19", "sex", "age", "population"],
    )


def _seed23(ltlas, value=lambda lt, e, s, k: 10):
    return pd.DataFrame(
        [(lt, e, s, k, value(lt, e, s, k)) for lt in ltlas for e in base.ETH for s in "FM"
         for k in range(1, 24)],
        columns=["ltla21cd", "eth19", "sex", "age23", "population"],
    )  # fmt: skip


def _lookup():
    return pd.DataFrame(
        {
            "lsoa21cd": ["E01000001", "E01000002", "E01000003", "E01000004"],
            "ltla21cd": ["E07000001", "E07000002", "E07000003", "E06000053"],
            "rgn21cd": ["E12000002", "E12000002", "E12000002", "E12000009"],
            "in_focus_icb": [True, True, False, False],
        }
    )


def _blocked(rows):
    return pd.DataFrame(rows, columns=["ltla21cd", "classification"])


def test_seed_region_split_and_substitute(ctx):
    lk = _lookup()
    # E07000003 is blocked at single year; E06000053 at both and substitutes E07000001.
    s91 = _seed91(["E07000001", "E07000002"])
    s23 = _seed23(["E07000001", "E07000002", "E07000003"])
    blocked = _blocked(
        [("E07000003", "age_91a"), ("E06000053", "age_91a"), ("E06000053", "age_23a")]
    )
    # default maps E06000053 -> E06000052; override via a copy
    cfg = ctx.cfg.model_copy(update={"ipf": ctx.cfg.ipf.model_copy(
        update={"seed_substitutes": {"E06000053": "E07000001"}})})  # fmt: skip
    cfg._root = ctx.cfg.root
    ctx.cfg = cfg
    seed, ltlas, src = base.build_seed(ctx, s91, s23, blocked, lk)
    assert ltlas == ["E06000053", "E07000001", "E07000002", "E07000003"]
    srcs = dict(zip(src["ltla21cd"], src["seed_source"], strict=True))
    assert srcs == {"E06000053": "substitute:E07000001", "E07000001": "age91",
                    "E07000002": "age91", "E07000003": "age23_region_split"}  # fmt: skip
    i3 = ltlas.index("E07000003")
    # 23-category counts preserved: e.g. category 10 = ages 25..29 sums to 10
    assert seed[i3, 0, 0, 25:30].sum() == pytest.approx(10)
    # split follows the regional shape for the same eth x sex: region = E07000001 + E07000002
    reg = seed[[ltlas.index("E07000001"), ltlas.index("E07000002")]].sum(0)[0, 1, 25:30]
    np.testing.assert_allclose(seed[i3, 0, 1, 25:30], 10 * reg / reg.sum())
    np.testing.assert_array_equal(seed[ltlas.index("E06000053")], seed[ltlas.index("E07000001")])


def test_missing_substitute_fails(ctx):
    lk = _lookup()
    blocked = _blocked([("E07000003", "age_91a"), ("E07000003", "age_23a")])
    cfg = ctx.cfg.model_copy(
        update={"ipf": ctx.cfg.ipf.model_copy(update={"seed_substitutes": {}})}
    )
    cfg._root = ctx.cfg.root
    ctx.cfg = cfg
    with pytest.raises(ValueError, match="blocked at all fine ages"):
        base.build_seed(
            ctx, _seed91(["E07000001", "E07000002", "E06000053"]), _seed23([]), blocked, lk
        )


def _margins(lsoas, rng):
    rows = []
    for ls in lsoas:
        for s in "FM":
            ages = rng.integers(0, 6, 91).astype(float)
            for a, v in enumerate(ages):
                band = 1 if a <= 24 else 2 if a <= 34 else 3 if a <= 49 else 4 if a <= 64 else 5
                rows.append((ls, s, band, "age", a, v))
            for b, (lo, hi) in enumerate([(0, 24), (25, 34), (35, 49), (50, 64), (65, 90)], 1):
                t = ages[lo : hi + 1].sum()
                w = rng.dirichlet(np.ones(19) * 0.3)
                rows += [(ls, s, b, "eth19", e, t * w[e - 1]) for e in base.ETH]
    return pd.DataFrame(rows, columns=["lsoa21cd", "sex", "band", "kind", "key", "population"])


def test_fit_reproduces_both_margins(ctx):
    rng = np.random.default_rng(0)
    lk = _lookup()
    lsoas = lk["lsoa21cd"].tolist()
    m = _margins(lsoas, rng)
    eth_m, age_m = base.margin_arrays(ctx.cfg, m, lsoas)
    seed = rng.uniform(0, 3, (4, 2, 19, 91)) * (rng.uniform(size=(4, 2, 19, 91)) > 0.5)
    b, diag = base.fit_base(ctx, seed, np.arange(4), eth_m, age_m, floor=0.5)
    assert b.shape == (4, 2, 91, 19)
    np.testing.assert_allclose(b.sum(3), age_m, atol=1e-9)
    by_band = np.stack(
        [
            b[:, :, lo : hi + 1, :].sum(2)
            for lo, hi in [(0, 24), (25, 34), (35, 49), (50, 64), (65, 90)]
        ],
        axis=2,
    )
    np.testing.assert_allclose(by_band, eth_m, atol=1e-5)
    assert set(diag) == {1, 2, 3, 4, 5}


def test_zero_floor_with_sparse_seed_can_be_infeasible(ctx):
    from lsc_pop.ipf import IPFInfeasible

    rng = np.random.default_rng(0)
    lsoas = _lookup()["lsoa21cd"].tolist()
    eth_m, age_m = base.margin_arrays(ctx.cfg, _margins(lsoas, rng), lsoas)
    with pytest.raises(IPFInfeasible):
        base.fit_base(ctx, np.zeros((4, 2, 19, 91)), np.arange(4), eth_m, age_m, floor=0.0)


def test_cube_roundtrip_and_hash(ctx, tmp_path):
    rng = np.random.default_rng(0)
    data = rng.uniform(size=(5, 2, 3, 4))
    cube = Cube(data, ("lsoa21cd", "sex", "age", "eth19"),
                {"lsoa21cd": [f"E0100000{i}" for i in range(5)], "sex": ["F", "M"],
                 "age": [0, 1, 2], "eth19": [1, 2, 3, 4]})  # fmt: skip
    path = write_cube(cube, tmp_path / "c", ctx, chunk=2)
    back = read_cube(path)
    np.testing.assert_array_equal(back.data, data)
    assert back.coords == cube.coords and back.hash() == cube.hash()
    df = pd.read_parquet(path)
    assert len(df) == 5 * 2 * 3 * 4
    row = df.iloc[1 * 24 + 1 * 12 + 2 * 4 + 3]
    assert (row["lsoa21cd"], row["sex"], row["age"], row["eth19"]) == ("E01000001", "M", 2, 4)
    assert row["population"] == data[1, 1, 2, 3]
    assert Cube(data + 1e-12, cube.dims, cube.coords).hash() != cube.hash()
    assert cube.totals()["by_sex"]["F"] == pytest.approx(data[:, 0].sum())
