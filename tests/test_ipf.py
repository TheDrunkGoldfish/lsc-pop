from __future__ import annotations

import numpy as np
import pytest

from lsc_pop.ipf import IPFInfeasible, IPFNotConverged, ipf_fit


def _one(seed, row, col, **kw):
    res = ipf_fit(np.array([seed], float), np.array([row], float), np.array([col], float), **kw)
    return res.x[0], res


def test_uniform_seed_gives_independence_solution():
    row, col = [30.0, 70.0], [20.0, 50.0, 30.0]
    x, res = _one(np.ones((2, 3)), row, col)
    np.testing.assert_allclose(x, np.outer(row, col) / 100, atol=1e-9)
    assert res.n_iter <= 2


def test_known_textbook_solution():
    # Deming & Stephan style 2x2: seed odds ratio must be preserved; margins matched.
    seed = np.array([[1.0, 2.0], [3.0, 4.0]])
    x, _ = _one(seed, [10.0, 20.0], [12.0, 18.0], tol=1e-12)
    np.testing.assert_allclose(x.sum(1), [10, 20], atol=1e-10)
    np.testing.assert_allclose(x.sum(0), [12, 18], atol=1e-10)
    odds = lambda m: m[0, 0] * m[1, 1] / (m[0, 1] * m[1, 0])  # noqa: E731
    assert odds(x) == pytest.approx(odds(seed), rel=1e-9)
    # Closed form for 2x2 with given odds ratio theta: solve for a = x00
    theta, r0, c0, t = odds(seed), 10.0, 12.0, 30.0
    # a(t - r0 - c0 + a) = theta (r0 - a)(c0 - a)
    coeffs = [1 - theta, (t - r0 - c0) + theta * (r0 + c0), -theta * r0 * c0]
    a = [z.real for z in np.roots(coeffs) if 0 < z.real < min(r0, c0)][0]
    assert x[0, 0] == pytest.approx(a, rel=1e-9)


def test_odds_ratios_preserved_larger_table():
    rng = np.random.default_rng(0)
    seed = rng.uniform(0.5, 5, (4, 5))
    row = rng.uniform(1, 10, 4)
    col = rng.uniform(1, 10, 5)
    col *= row.sum() / col.sum()
    x, _ = _one(seed, row, col, tol=1e-12)
    lx, ls = np.log(x), np.log(seed)
    # double-centred log tables are equal <=> all odds ratios equal
    dc = lambda m: m - m.mean(0) - m.mean(1)[:, None] + m.mean()  # noqa: E731
    np.testing.assert_allclose(dc(lx), dc(ls), atol=1e-8)


def test_zero_row_and_column_margins_give_structural_zeros():
    seed = np.ones((3, 3))
    x, _ = _one(seed, [5.0, 0.0, 5.0], [0.0, 4.0, 6.0])
    assert (x[1] == 0).all() and (x[:, 0] == 0).all()
    np.testing.assert_allclose(x.sum(1), [5, 0, 5], atol=1e-9)
    np.testing.assert_allclose(x.sum(0), [0, 4, 6], atol=1e-9)


def test_all_zero_table():
    x, res = _one(np.ones((2, 2)), [0.0, 0.0], [0.0, 0.0])
    assert (x == 0).all() and res.iterations[0] == 1


def test_seed_zero_cells_stay_zero_when_feasible():
    seed = np.array([[1.0, 0.0], [1.0, 1.0]])
    x, _ = _one(seed, [3.0, 7.0], [6.0, 4.0], tol=1e-10)
    assert x[0, 1] == 0
    np.testing.assert_allclose(x, [[3, 0], [3, 4]], atol=1e-8)


def test_infeasible_seed_raises():
    seed = np.array([[0.0, 0.0], [1.0, 1.0]])  # row 0 has no support but margin 3
    with pytest.raises(IPFInfeasible):
        _one(seed, [3.0, 7.0], [5.0, 5.0])


def test_margin_total_mismatch_raises():
    with pytest.raises(ValueError, match="row total != column total"):
        _one(np.ones((2, 2)), [3.0, 7.0], [5.0, 6.0])


def test_non_convergence_raises():
    # Zero pattern that forces slow convergence; with max_iter=1 it cannot meet the tolerance.
    seed = np.array([[1.0, 1.0, 0.0], [0.0, 1.0, 1.0], [1.0, 0.0, 1.0]])
    with pytest.raises(IPFNotConverged, match="did not converge"):
        _one(seed, [10.0, 1.0, 1.0], [1.0, 1.0, 10.0], max_iter=1, tol=1e-9)


def test_negative_input_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _one(-np.ones((2, 2)), [1.0, 1.0], [1.0, 1.0])


def test_batch_equals_separate_fits():
    rng = np.random.default_rng(1)
    n = 50
    seed = rng.uniform(0, 3, (n, 6, 4)) * (rng.uniform(size=(n, 6, 4)) > 0.2) + 0.01
    row = rng.integers(0, 20, (n, 6)).astype(float)
    col = rng.uniform(0, 1, (n, 4))
    col = col / col.sum(1, keepdims=True) * row.sum(1, keepdims=True)
    batch = ipf_fit(seed, row, col, tol=1e-10).x
    for i in range(n):
        single = ipf_fit(seed[i : i + 1], row[i : i + 1], col[i : i + 1], tol=1e-10).x[0]
        np.testing.assert_allclose(batch[i], single, atol=1e-8)


def test_scaling_margins_scales_solution():
    """The ADR-0015 invariance: a common rescaling of both margins rescales the fit."""
    rng = np.random.default_rng(2)
    seed = rng.uniform(0.1, 2, (1, 5, 7))
    row = rng.uniform(1, 9, (1, 5))
    col = rng.uniform(1, 9, (1, 7))
    col *= row.sum() / col.sum()
    a = ipf_fit(seed, row, col, tol=1e-12).x
    b = ipf_fit(seed, row * 1.37, col * 1.37, tol=1e-12).x
    np.testing.assert_allclose(b, a * 1.37, rtol=1e-9)


def test_reports_iterations_and_errors():
    rng = np.random.default_rng(3)
    seed = rng.uniform(0.1, 2, (10, 3, 4))
    row = rng.uniform(1, 9, (10, 3))
    col = rng.uniform(1, 9, (10, 4))
    col *= (row.sum(1) / col.sum(1))[:, None]
    res = ipf_fit(seed, row, col, tol=1e-8)
    assert (res.iterations >= 1).all() and res.n_iter == res.iterations.max()
    assert (res.max_row_error < 1e-8).all() and (res.max_col_error < 1e-9).all()
