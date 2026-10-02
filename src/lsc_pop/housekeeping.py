"""Housekeeping: free disk space taken by previous runs' output tables.

Each run writes ~4.5 GB of tables to ``outputs/<run_id>/tables/``. Everything else in a run
directory (metadata, run log, checks, hashes, sensitivity/comparison CSVs) is small and is the
run's provenance, so by default only ``tables/`` is removed and the rest is kept.

Nothing is deleted unless ``apply=True`` (CLI: ``lsc-pop clean --yes``).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from lsc_pop.config import Config


@dataclass(frozen=True)
class CleanupItem:
    run_id: str
    path: Path
    bytes: int
    reason: str


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def run_dirs(cfg: Config) -> list[Path]:
    """Run directories, oldest first (run ids start with a UTC timestamp, so names sort)."""
    out = cfg.resolve(cfg.paths.outputs)
    return (
        sorted((p for p in out.iterdir() if p.is_dir()), key=lambda p: p.name)
        if out.is_dir()
        else []
    )


def plan_cleanup(
    cfg: Config, keep: int = 1, include_latest: bool = False, whole_runs: bool = False
) -> list[CleanupItem]:
    """What would be deleted.

    * ``keep``: number of most recent runs *with tables* whose tables are kept (default 1, i.e. the
      latest). ``include_latest=True`` sets it to 0, so even the latest run's tables are removed.
    * ``whole_runs``: delete entire run directories (logs and checks too), not just ``tables/``.
      Runs inside the ``keep`` window are always left intact.
    """
    keep = 0 if include_latest else max(keep, 0)
    runs = run_dirs(cfg)
    with_tables = [r for r in runs if (r / "tables").is_dir()]
    protected = {r.name for r in with_tables[len(with_tables) - keep :]} if keep else set()
    items: list[CleanupItem] = []
    for r in runs:
        if r.name in protected:
            continue
        if whole_runs:
            items.append(CleanupItem(r.name, r, _size(r), "whole run directory"))
        elif (r / "tables").is_dir():
            items.append(CleanupItem(r.name, r / "tables", _size(r / "tables"), "tables/"))
    return items


def apply_cleanup(items: list[CleanupItem]) -> int:
    freed = 0
    for it in items:
        if it.path.exists():
            shutil.rmtree(it.path)
            freed += it.bytes
    return freed


def human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    raise AssertionError
