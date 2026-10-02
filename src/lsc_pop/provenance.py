"""Provenance: run context, the step logger, dataset hashing and output sidecars.

Every pipeline transformation runs inside :func:`logged_step`, which writes one JSON line per step
to ``outputs/<run_id>/run_log.jsonl``. Each line records row counts and population totals (overall
and by sex) in and out, so ``docs/transformations.md`` can show what every step did to the numbers.

Usage::

    ctx = RunContext.create(cfg)

    with logged_step(ctx, "census.load_rm032", params={"table": "RM032"}) as step:
        step.input("rm032_raw", raw_df)
        df = tidy(raw_df)
        step.drop(12, "Does not apply rows (all zero)")
        step.note("asserted 'Does not apply' == 0 for all LSOAs")
        step.output("rm032", df)

    @logged_step(ctx, "ipf.fit")
    def fit(step, seed, margins): ...

The project is not under git (ADR-0009). Git info is recorded when available and is null
otherwise. Reproducibility rests on the config hash, ``uv.lock`` hash and ``code_hash``.
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import subprocess
import traceback
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from lsc_pop.config import Config

NOT_OFFICIAL_STATEMENT = (
    "Modelled estimates - not official statistics. Produced by combining Census 2021 tables, ONS "
    "small area population estimates and other public sources with statistical modelling (IPF and "
    "share roll-forward). Small cells are highly uncertain. See docs/limitations.md."
)
DOCS_POINTER = "docs/methodology.md; docs/limitations.md; docs/data_dictionary.md"

DEFAULT_VALUE_COL = "population"
DEFAULT_SEX_COL = "sex"


# --------------------------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------------------------


def hash_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def hash_dataframe(df: pd.DataFrame) -> str:
    """Deterministic content hash. Independent of column order; sensitive to row order and dtypes.

    Pipeline stages are expected to sort their outputs, so row order is part of the contract.
    """
    cols = sorted(df.columns.astype(str))
    d = df.copy()
    d.columns = d.columns.astype(str)
    d = d[cols]
    h = hashlib.sha256()
    h.update(json.dumps([(c, str(d[c].dtype)) for c in cols]).encode())
    h.update(pd.util.hash_pandas_object(d, index=False).values.tobytes())
    return h.hexdigest()


def hash_tree(root: Path, pattern: str = "**/*.py") -> str:
    """SHA-256 over sorted (relative path, content) pairs of matching files."""
    h = hashlib.sha256()
    for p in sorted(root.glob(pattern)):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        h.update(p.read_bytes() + b"\0")
    return h.hexdigest()


# --------------------------------------------------------------------------------------------
# Run context
# --------------------------------------------------------------------------------------------


def git_info(cwd: Path) -> dict[str, Any]:
    """Git commit + dirty flag, or nulls when git / a repo is unavailable."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return {"git_available": True, "git_commit": commit, "git_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"git_available": False, "git_commit": None, "git_dirty": None}


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class RunContext:
    cfg: Config
    run_id: str
    out_dir: Path
    config_hash: str
    lock_hash: str | None
    code_hash: str
    git: dict[str, Any]
    started_at: str

    @classmethod
    def create(cls, cfg: Config, run_id: str | None = None) -> RunContext:
        config_hash = cfg.config_hash()
        started = datetime.now(UTC)
        code_hash = hash_tree(Path(__file__).resolve().parent)
        # <UTC start>_<config hash[:8]>_<code hash[:8]>: same config8 = same settings/inputs;
        # same code8 = same package source (see README "Run ids").
        run_id = run_id or f"{started:%Y%m%dT%H%M%SZ}_{config_hash[:8]}_{code_hash[:8]}"
        out_dir = cfg.resolve(cfg.paths.outputs) / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        lock = cfg.root / "uv.lock"
        ctx = cls(
            cfg=cfg,
            run_id=run_id,
            out_dir=out_dir,
            config_hash=config_hash,
            lock_hash=hash_file(lock) if lock.is_file() else None,
            code_hash=code_hash,
            git=git_info(cfg.root),
            started_at=started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        ctx.write_run_metadata()
        return ctx

    @property
    def log_path(self) -> Path:
        return self.out_dir / "run_log.jsonl"

    def base_metadata(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            **self.git,
            "config_hash": self.config_hash,
            "uv_lock_hash": self.lock_hash,
            "code_hash": self.code_hash,
            "reference_date": self.cfg.reference_date,
            "variant": self.cfg.variant,
            "statement": NOT_OFFICIAL_STATEMENT,
            "docs": DOCS_POINTER,
        }

    def write_run_metadata(self) -> Path:
        path = self.out_dir / "metadata.json"
        meta = {**self.base_metadata(), "config": self.cfg.model_dump(mode="json")}
        path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        return path

    def append_log(self, record: dict[str, Any]) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    @property
    def checks_path(self) -> Path:
        return self.out_dir / "validation.jsonl"

    def append_check(self, record: dict[str, Any]) -> None:
        with open(self.checks_path, "a") as f:
            f.write(
                json.dumps({"run_id": self.run_id, **record}, sort_keys=True, default=str) + "\n"
            )


# --------------------------------------------------------------------------------------------
# Step logger
# --------------------------------------------------------------------------------------------


def population_totals(
    df: pd.DataFrame, value_col: str = DEFAULT_VALUE_COL, sex_col: str = DEFAULT_SEX_COL
) -> dict[str, Any] | None:
    """Total and by-sex totals of ``value_col``; None if the frame carries no population column."""
    if value_col not in df.columns:
        return None
    out: dict[str, Any] = {"total": float(df[value_col].sum())}
    if sex_col in df.columns:
        out["by_sex"] = {str(k): float(v) for k, v in df.groupby(sex_col)[value_col].sum().items()}
    return out


@dataclass
class _Dataset:
    name: str
    rows: int
    hash: str
    population: dict[str, Any] | None


@dataclass
class Step:
    """Collects what a step did. Obtained from :func:`logged_step`."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    value_col: str = DEFAULT_VALUE_COL
    sex_col: str = DEFAULT_SEX_COL
    inputs: list[_Dataset] = field(default_factory=list)
    outputs: list[_Dataset] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    added: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def _describe(self, name: str, df: pd.DataFrame) -> _Dataset:
        return _Dataset(
            name=name,
            rows=len(df),
            hash=hash_dataframe(df),
            population=population_totals(df, self.value_col, self.sex_col),
        )

    def input(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        self.inputs.append(self._describe(name, df))
        return df

    def input_file(self, name: str, path: Path | str, sha256: str, rows: int | None = None) -> None:
        """Record a raw file input (hash from the manifest) without loading it as a dataframe."""
        self.inputs.append(_Dataset(name=name, rows=rows or 0, hash=sha256, population=None))

    def output(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        self.outputs.append(self._describe(name, df))
        return df

    def input_cube(self, name: str, cube: Cube) -> Cube:
        self.inputs.append(_cube_dataset(name, cube))
        return cube

    def output_cube(self, name: str, cube: Cube) -> Cube:
        self.outputs.append(_cube_dataset(name, cube))
        return cube

    def drop(self, n_rows: int, reason: str) -> None:
        self.dropped.append({"rows": int(n_rows), "reason": reason})

    def add(self, n_rows: int, reason: str) -> None:
        self.added.append({"rows": int(n_rows), "reason": reason})

    def note(self, text: str) -> None:
        self.notes.append(text)

    def record(self) -> dict[str, Any]:
        def ds(items: list[_Dataset]) -> list[dict[str, Any]]:
            return [vars(d) for d in items]

        return {
            "step": self.name,
            "params": self.params,
            "inputs": ds(self.inputs),
            "outputs": ds(self.outputs),
            "rows_in": sum(d.rows for d in self.inputs),
            "rows_out": sum(d.rows for d in self.outputs),
            "rows_dropped": self.dropped,
            "rows_added": self.added,
            "notes": self.notes,
        }


class logged_step(contextlib.ContextDecorator):  # noqa: N801 - reads as a function
    """Context manager / decorator that logs a pipeline step to the run's JSONL.

    As a decorator, the wrapped function receives the :class:`Step` as its first argument.
    On exception the step is logged with ``status: "error"`` and the exception re-raised.
    """

    def __init__(
        self,
        ctx: RunContext,
        name: str,
        params: dict[str, Any] | None = None,
        value_col: str = DEFAULT_VALUE_COL,
        sex_col: str = DEFAULT_SEX_COL,
    ) -> None:
        self.ctx = ctx
        self.name = name
        self.params = params or {}
        self.value_col = value_col
        self.sex_col = sex_col
        self._stack: list[tuple[Step, str]] = []

    def __enter__(self) -> Step:
        step = Step(self.name, dict(self.params), self.value_col, self.sex_col)
        self._stack.append((step, _utcnow()))
        return step

    def __exit__(self, exc_type, exc, tb) -> bool:
        step, started = self._stack.pop()
        record = {
            "run_id": self.ctx.run_id,
            "started_at": started,
            "finished_at": _utcnow(),
            "status": "ok" if exc is None else "error",
            **step.record(),
        }
        if exc is not None:
            record["error"] = "".join(traceback.format_exception_only(exc_type, exc)).strip()
        self.ctx.append_log(record)
        return False  # never swallow exceptions

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with self as step:
                return func(step, *args, **kwargs)

        return wrapper


def read_run_log(path: Path) -> Iterator[dict[str, Any]]:
    with open(path) as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


# --------------------------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------------------------


def write_output(
    df: pd.DataFrame,
    path: Path | str,
    ctx: RunContext,
    sources: list[dict[str, Any]] | None = None,
    csv: bool = False,
    description: str = "",
) -> Path:
    """Write ``df`` to parquet (``path`` with .parquet suffix) plus a ``.metadata.json`` sidecar."""
    path = Path(path).with_suffix(".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    files = [path.name]
    if csv:
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        files.append(csv_path.name)
    meta = {
        **ctx.base_metadata(),
        "description": description,
        "files": files,
        "rows": len(df),
        "columns": list(map(str, df.columns)),
        "data_hash": hash_dataframe(df),
        "population": population_totals(df),
        "sources": sources or [],
    }
    sidecar = path.with_name(path.stem + ".metadata.json")
    sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n")
    return path


# --------------------------------------------------------------------------------------------
# Dense cubes (LSOA x sex x age x ethnicity): too large for dataframe hashing
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cube:
    """A dense array with named, labelled dimensions, e.g. (lsoa21cd, sex, age, eth19)."""

    data: Any  # numpy.ndarray
    dims: tuple[str, ...]
    coords: dict[str, list]

    def __post_init__(self) -> None:
        if tuple(len(self.coords[d]) for d in self.dims) != self.data.shape:
            raise ValueError(f"coords {self.dims} do not match data shape {self.data.shape}")

    def hash(self) -> str:
        import numpy as np

        h = hashlib.sha256()
        h.update(json.dumps({"dims": self.dims, "coords": self.coords}, default=str).encode())
        h.update(str(self.data.dtype).encode())
        h.update(np.ascontiguousarray(self.data).tobytes())
        return h.hexdigest()

    def totals(self) -> dict[str, Any]:
        out: dict[str, Any] = {"total": float(self.data.sum())}
        if "sex" in self.dims:
            ax = self.dims.index("sex")
            others = tuple(i for i in range(self.data.ndim) if i != ax)
            by = self.data.sum(axis=others)
            out["by_sex"] = {str(k): float(v) for k, v in zip(self.coords["sex"], by, strict=True)}
        return out

    @property
    def rows(self) -> int:
        return int(self.data.size)


def _cube_dataset(name: str, cube: Cube) -> _Dataset:
    return _Dataset(name=name, rows=cube.rows, hash=cube.hash(), population=cube.totals())


def write_cube(
    cube: Cube,
    path: Path | str,
    ctx: RunContext,
    sources: list[dict[str, Any]] | None = None,
    description: str = "",
    value_name: str = "population",
    chunk: int = 2000,
    constants: dict[str, Any] | None = None,
) -> Path:
    """Write a cube as long-format Parquet (C order of ``dims``) plus a metadata sidecar.

    ``constants`` adds columns holding one value on every row (e.g. reference_year, variant).

    The first dimension is written in chunks to bound memory. Row order is the C order of the
    array, so ``read_cube`` can reshape without sorting.
    """
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path).with_suffix(".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = cube.dims[0], cube.dims[1:]
    rest_shape = cube.data.shape[1:]
    n_rest = int(np.prod(rest_shape))
    rest_idx = np.indices(rest_shape).reshape(len(rest_shape), -1)

    def arrow_col(dim: str, idx: np.ndarray) -> pa.Array:
        labels = cube.coords[dim]
        if all(isinstance(v, (int, np.integer)) for v in labels):
            return pa.array(np.asarray(labels, dtype=np.int16)[idx])
        return pa.DictionaryArray.from_arrays(
            pa.array(idx.astype(np.int32)), pa.array([str(v) for v in labels])
        )

    writer = None
    try:
        for start in range(0, cube.data.shape[0], chunk):
            stop = min(start + chunk, cube.data.shape[0])
            n = stop - start
            cols = {first: arrow_col(first, np.repeat(np.arange(start, stop), n_rest))}
            for i, dim in enumerate(rest):
                cols[dim] = arrow_col(dim, np.tile(rest_idx[i], n))
            cols[value_name] = pa.array(cube.data[start:stop].reshape(-1))
            for k, v in (constants or {}).items():
                if isinstance(v, int):
                    cols[k] = pa.array(np.full(n * n_rest, v, dtype=np.int16))
                else:
                    cols[k] = pa.DictionaryArray.from_arrays(
                        pa.array(np.zeros(n * n_rest, dtype=np.int32)), pa.array([str(v)])
                    )
            table = pa.table(cols)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()

    meta = {
        **ctx.base_metadata(),
        "description": description,
        "files": [path.name],
        "rows": cube.rows,
        "dims": list(cube.dims),
        "shape": list(cube.data.shape),
        "coords": {d: cube.coords[d] for d in cube.dims if d != first}
        | {first: f"{len(cube.coords[first])} labels, sorted; see the parquet column"},
        "columns": [*cube.dims, value_name, *(constants or {})],
        "constants": constants or {},
        "data_hash": cube.hash(),
        "population": cube.totals(),
        "sources": sources or [],
    }
    sidecar = path.with_name(path.stem + ".metadata.json")
    sidecar.write_text(json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n")
    return path


def read_cube(path: Path | str, value_name: str = "population") -> Cube:
    """Inverse of :func:`write_cube`."""
    import numpy as np
    import pyarrow.parquet as pq

    path = Path(path).with_suffix(".parquet")
    meta = json.loads(path.with_name(path.stem + ".metadata.json").read_text())
    dims = tuple(meta["dims"])
    table = pq.read_table(path)
    first = table.column(dims[0]).combine_chunks()
    first_labels = first.dictionary.to_pylist()  # all labels, in coord order
    coords = {dims[0]: first_labels} | {d: meta["coords"][d] for d in dims[1:]}
    data = table.column(value_name).to_numpy().reshape(meta["shape"])
    return Cube(np.ascontiguousarray(data), dims, coords)
