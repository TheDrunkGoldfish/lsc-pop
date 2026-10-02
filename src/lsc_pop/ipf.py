"""Iterative proportional fitting (raking) of many small 2-D tables at once.

Pure numpy and deliberately small, so it can be read in full (ADR-0003). Stage C (``base.py``) calls
:func:`ipf_fit` once per RM032 age band, with one table per LSOA × sex:

* rows    = 19 ethnic groups      (margin: reconciled RM032 ethnic counts in the band)
* columns = single years in band  (margin: reconciled RM200 counts)
* seed    = the LTLA's ethnicity × age counts in the band (+ floor), giving the age shape

Algorithm, for each table independently::

    x = seed, with rows/columns whose margin is 0 set to 0 (structural zeros)
    repeat:
        scale each row so it sums to its row margin
        scale each column so it sums to its column margin      (columns now exact)
        stop when every table's max |row sum - row margin| < tolerance

Each table converges to the unique table that matches both margins while keeping the seed's odds
ratios (the minimum-discrimination-information solution). Inputs are validated first:

* row and column margins of each table must have the same total (reconciled in Stage B);
* every positive row (column) must have at least one positive seed cell in a positive column (row),
  or the table is infeasible and :class:`IPFInfeasible` is raised;
* failing to converge within ``max_iter`` raises :class:`IPFNotConverged`. Nothing is silent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class IPFError(RuntimeError):
    pass


class IPFInfeasible(IPFError):
    pass


class IPFNotConverged(IPFError):
    pass


@dataclass(frozen=True)
class IPFResult:
    x: np.ndarray  # (N, R, C) fitted tables
    iterations: np.ndarray  # (N,) iteration at which each table first met the tolerance
    max_row_error: np.ndarray  # (N,) final max |row sum - margin|
    max_col_error: np.ndarray  # (N,) final max |col sum - margin|
    n_iter: int  # iterations run (the slowest table)


def _safe_ratio(target: np.ndarray, current: np.ndarray) -> np.ndarray:
    out = np.zeros_like(current)
    np.divide(target, current, out=out, where=current > 0)
    return out


def ipf_fit(
    seed: np.ndarray,
    row: np.ndarray,
    col: np.ndarray,
    tol: float = 1e-6,
    max_iter: int = 1000,
    total_rtol: float = 1e-9,
) -> IPFResult:
    """Fit N tables. ``seed`` (N, R, C) >= 0; ``row`` (N, R) and ``col`` (N, C) >= 0."""
    seed = np.asarray(seed, dtype=float)
    row = np.asarray(row, dtype=float)
    col = np.asarray(col, dtype=float)
    n, r, c = seed.shape
    if row.shape != (n, r) or col.shape != (n, c):
        raise ValueError(f"shape mismatch: seed {seed.shape}, row {row.shape}, col {col.shape}")
    for name, arr in (("seed", seed), ("row", row), ("col", col)):
        if not np.isfinite(arr).all() or (arr < 0).any():
            raise ValueError(f"{name} must be finite and non-negative")

    rt, ct = row.sum(1), col.sum(1)
    bad = np.abs(rt - ct) > total_rtol * np.maximum(1.0, np.maximum(rt, ct))
    if bad.any():
        i = int(np.flatnonzero(bad)[0])
        raise ValueError(
            f"{int(bad.sum())} tables have row total != column total (e.g. table {i}: "
            f"{rt[i]} vs {ct[i]}); reconcile margins first"
        )

    x = seed * (row > 0)[:, :, None] * (col > 0)[:, None, :]
    row_support = x.sum(2)
    col_support = x.sum(1)
    infeasible = ((row > 0) & (row_support == 0)).any(1) | ((col > 0) & (col_support == 0)).any(1)
    if infeasible.any():
        raise IPFInfeasible(
            f"{int(infeasible.sum())} tables have a positive margin with no positive seed cell "
            f"(e.g. table {int(np.flatnonzero(infeasible)[0])}); use a seed floor"
        )

    iterations = np.full(n, -1, dtype=np.int32)
    row_err = np.full(n, np.inf)
    it = 0
    for it in range(1, max_iter + 1):
        x *= _safe_ratio(row, x.sum(2))[:, :, None]
        x *= _safe_ratio(col, x.sum(1))[:, None, :]
        row_err = np.abs(x.sum(2) - row).max(1)
        newly = (iterations < 0) & (row_err < tol)
        iterations[newly] = it
        if (iterations >= 0).all():
            break
    col_err = np.abs(x.sum(1) - col).max(1)
    if (iterations < 0).any():
        worst = int(np.argmax(row_err))
        raise IPFNotConverged(
            f"{int((iterations < 0).sum())} of {n} tables did not converge in {max_iter} "
            f"iterations (worst table {worst}: max row error {row_err[worst]:.3g}, tol {tol})"
        )
    return IPFResult(x, iterations, row_err, col_err, it)
