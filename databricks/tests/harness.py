"""Local emulator for the lsc-pop Lakeflow Declarative Pipeline (tests only).

Runs the *real* files in ``databricks/src/pipeline/transformations`` against local Spark:

* Python files are executed with a stub ``pyspark.pipelines`` module. ``@dp.table`` /
  ``@dp.materialized_view`` register datasets, and ``@dp.expect*`` register expectations.
* SQL files are parsed statement by statement. ``USE SCHEMA`` is honoured, ``${key}`` is replaced
  from the pipeline configuration, and ``CREATE OR REFRESH ... MATERIALIZED VIEW | STREAMING TABLE
  name (CONSTRAINT ... EXPECT (...) [ON VIOLATION ...]) COMMENT '...' AS query`` is executed as
  ``query`` and saved as a table, then its expectations are evaluated.
* Datasets run in file-name order, then in the order they appear in each file. File names carry
  numeric prefixes that follow the dependency order, so no graph resolution is needed locally.
  The real runtime resolves the graph itself.

Expectation semantics follow Databricks: ``FAIL UPDATE`` / ``expect_or_fail`` raises
:class:`ExpectationFailed`, ``DROP ROW`` drops violating rows, and the plain form only records
them. A row whose constraint evaluates to NULL counts as a violation (stricter than needed).
"""

from __future__ import annotations

import re
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

TRANSFORMATIONS = Path(__file__).resolve().parents[1] / "src" / "pipeline" / "transformations"
PIPELINE_ROOT = TRANSFORMATIONS.parent


class ExpectationFailed(AssertionError):
    pass


class EagerDatasetError(AssertionError):
    """A dataset function ran Spark jobs while *defining* its result (e.g. toPandas/count).

    Databricks calls dataset functions during graph analysis, before upstream tables have data,
    so such functions see empty inputs. They must only describe a lazy DataFrame.
    """


@dataclass
class Expectation:
    dataset: str
    name: str
    constraint: str
    action: str  # "warn" | "drop" | "fail"
    violations: int = -1


@dataclass
class Dataset:
    name: str
    kind: str
    build: Callable  # () -> DataFrame
    expectations: list[tuple[str, str, str]] = field(default_factory=list)


def _stub_pipelines(registry: list[Dataset]) -> types.ModuleType:
    mod = types.ModuleType("pyspark.pipelines")

    def _dataset(kind):
        def deco_factory(*args, name=None, comment=None, **_kw):
            def deco(func):
                exps = getattr(func, "_lsc_expectations", [])
                registry.append(Dataset(name or func.__name__, kind, func, list(reversed(exps))))
                return func

            if args and callable(args[0]) and name is None:  # bare @dp.table
                return deco(args[0])
            return deco

        return deco_factory

    def _expect(action, many=False):
        def factory(*args):
            pairs = list(args[0].items()) if many else [(args[0], args[1])]

            def deco(func):
                func._lsc_expectations = getattr(func, "_lsc_expectations", []) + [
                    (n, c, action) for n, c in pairs
                ]
                return func

            return deco

        return factory

    mod.table = _dataset("streaming_table")
    mod.materialized_view = _dataset("materialized_view")
    mod.temporary_view = _dataset("temporary_view")
    mod.expect = _expect("warn")
    mod.expect_or_drop = _expect("drop")
    mod.expect_or_fail = _expect("fail")
    mod.expect_all = _expect("warn", many=True)
    mod.expect_all_or_drop = _expect("drop", many=True)
    mod.expect_all_or_fail = _expect("fail", many=True)
    return mod


# --- SQL parsing ------------------------------------------------------------------------------

_CREATE = re.compile(
    r"^CREATE\s+OR\s+REFRESH\s+(?:PRIVATE\s+)?(MATERIALIZED\s+VIEW|STREAMING\s+TABLE)\s+([\w.`${}]+)\s*(.*)$",
    re.S | re.I,
)


def _strip_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


def _split_statements(sql: str) -> list[str]:
    out, buf, in_str = [], [], False
    for ch in _strip_comments(sql):
        if ch == "'":
            in_str = not in_str
        if ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _balanced(text: str) -> tuple[str, str]:
    """Split '(... ) rest' into the parenthesised body and the rest."""
    assert text.startswith("(")
    depth, in_str = 0, False
    for i, ch in enumerate(text):
        if ch == "'":
            in_str = not in_str
        if in_str:
            continue
        depth += ch == "("
        depth -= ch == ")"
        if depth == 0:
            return text[1:i], text[i + 1 :].lstrip()
    raise ValueError("unbalanced parentheses")


def _split_top_level(text: str) -> list[str]:
    parts, buf, depth, in_str = [], [], 0, False
    for ch in text:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def parse_create(stmt: str) -> tuple[str, str, list[tuple[str, str, str]], str]:
    """-> (kind, name, expectations[(name, expr, action)], query)."""
    m = _CREATE.match(stmt.strip())
    if not m:
        raise ValueError(f"unsupported statement: {stmt[:80]}")
    kind, name, rest = m.group(1).upper().replace("  ", " "), m.group(2), m.group(3).strip()
    exps = []
    if rest.startswith("("):
        body, rest = _balanced(rest)
        for item in _split_top_level(body):
            cm = re.match(r"CONSTRAINT\s+(\w+)\s+EXPECT\s*(\(.*)", item, re.S | re.I)
            if not cm:
                raise ValueError(f"unsupported column item: {item[:60]}")
            expr, tail = _balanced(cm.group(2).strip())
            tail = tail.upper()
            action = "fail" if "FAIL UPDATE" in tail else "drop" if "DROP ROW" in tail else "warn"
            exps.append((cm.group(1), expr.strip(), action))
    cm = re.match(r"COMMENT\s+'((?:[^']|'')*)'\s*(.*)$", rest, re.S | re.I)
    if cm:
        rest = cm.group(2)
    am = re.match(r"AS\s+(.*)$", rest, re.S | re.I)
    if not am:
        raise ValueError(f"expected AS <query> in: {stmt[:80]}")
    return kind, name, exps, am.group(1)


# --- Runner -----------------------------------------------------------------------------------


class LocalPipeline:
    def __init__(self, spark, conf: dict[str, str]):
        self.spark = spark
        self.conf = conf
        self.expectations: list[Expectation] = []
        self.built: list[str] = []
        for k, v in conf.items():
            spark.conf.set(k, v)
        for layer in ("bronze", "silver", "gold", "audit"):
            spark.sql(f"CREATE DATABASE IF NOT EXISTS {conf[f'lsc_pop.schema_{layer}']}")
        if str(PIPELINE_ROOT) not in sys.path:
            sys.path.insert(0, str(PIPELINE_ROOT))

    def _sub(self, sql: str) -> str:
        return re.sub(r"\$\{([\w.]+)\}", lambda m: self.conf[m.group(1)], sql)

    def _save(self, name: str, df, exps: list[tuple[str, str, str]]):
        for _ename, expr, action in exps:
            if action == "drop":
                df = df.filter(f"coalesce(({expr}), false)")
        df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(name)
        table = self.spark.read.table(name)
        for ename, expr, action in exps:
            bad = table.filter(f"NOT coalesce(({expr}), false)").count() if action != "drop" else 0
            self.expectations.append(Expectation(name, ename, expr, action, bad))
            if action == "fail" and bad:
                raise ExpectationFailed(
                    f"{name}: expectation {ename!r} failed for {bad} rows ({expr})"
                )
        self.built.append(name)

    def run_python(self, path: Path, only: set[str] | None = None) -> None:
        registry: list[Dataset] = []
        stub = _stub_pipelines(registry)
        import pyspark

        saved = sys.modules.get("pyspark.pipelines"), getattr(pyspark, "pipelines", None)
        sys.modules["pyspark.pipelines"] = stub
        pyspark.pipelines = stub
        try:
            code = compile(path.read_text(), str(path), "exec")
            exec(code, {"spark": self.spark, "__name__": path.stem})
        finally:
            if saved[0] is not None:
                sys.modules["pyspark.pipelines"] = saved[0]
            if saved[1] is not None:
                pyspark.pipelines = saved[1]
        sc = self.spark.sparkContext
        for ds in registry:
            if only is None or ds.name.split(".")[-1] in only:
                group = f"lsc_define_{ds.name}"
                sc.setJobGroup(group, f"define {ds.name}")
                df = ds.build()
                eager = sc.statusTracker().getJobIdsForGroup(group)
                sc.setJobGroup("lsc_run", "run")
                if eager:
                    raise EagerDatasetError(
                        f"{ds.name}: ran {len(eager)} Spark job(s) while defining the dataset"
                    )
                self._save(ds.name, df, ds.expectations)

    def run_sql(self, path: Path, only: set[str] | None = None) -> None:
        for stmt in _split_statements(self._sub(path.read_text())):
            head = stmt.strip().upper()
            if head.startswith("USE CATALOG"):
                continue
            if head.startswith("USE SCHEMA"):
                self.spark.sql("USE " + stmt.strip().split()[-1])
                continue
            _kind, name, exps, query = parse_create(stmt)
            if only is None or name.split(".")[-1] in only:
                self._save(name, self.spark.sql(query), exps)

    def run(self, files: list[str] | None = None, only: set[str] | None = None) -> LocalPipeline:
        for path in sorted(TRANSFORMATIONS.iterdir()):
            if files is not None and path.name not in files:
                continue
            if path.suffix == ".py":
                self.run_python(path, only)
            elif path.suffix == ".sql":
                self.run_sql(path, only)
        return self


def local_spark(warehouse: Path, memory: str = "4g", partitions: int = 8, persistent: bool = False):
    """Local Spark. ``persistent=True`` keeps tables between processes (Derby metastore)."""
    from pyspark.sql import SparkSession

    builder = SparkSession.builder
    if persistent:
        builder = builder.enableHiveSupport().config(
            "javax.jdo.option.ConnectionURL",
            f"jdbc:derby:;databaseName={warehouse / 'metastore_db'};create=true",
        )
    return (
        builder.master("local[*]")
        .appName("lsc-pop-local-pipeline")
        .config("spark.sql.warehouse.dir", str(warehouse))
        .config("spark.sql.shuffle.partitions", str(partitions))
        .config("spark.driver.memory", memory)
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )


def local_conf(raw_dir: Path, manifest: Path) -> dict[str, str]:
    return {
        "lsc_pop.catalog": "spark_catalog",
        "lsc_pop.schema_bronze": "bronze",
        "lsc_pop.schema_silver": "silver",
        "lsc_pop.schema_gold": "gold",
        "lsc_pop.schema_audit": "audit",
        "lsc_pop.raw_dir": str(raw_dir),
        "lsc_pop.manifest_path": str(manifest),
        "lsc_pop.bundle_target": "local",
        "lsc_pop.git_commit": "",
        "lsc_pop.local": "true",
    }
