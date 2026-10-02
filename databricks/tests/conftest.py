"""Fixtures for the Databricks-implementation tests (local Spark)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[0] / "src" / "pipeline"))

# Local Spark needs Java 17+. Use JAVA_HOME if set, else a Homebrew OpenJDK 17 if present.
if not os.environ.get("JAVA_HOME") and not shutil.which("java"):
    brew = Path("/opt/homebrew/opt/openjdk@17")
    if brew.exists():
        os.environ["JAVA_HOME"] = str(brew)
HAVE_JAVA = bool(os.environ.get("JAVA_HOME") or shutil.which("java"))
requires_spark = pytest.mark.skipif(not HAVE_JAVA, reason="local Spark needs Java 17+")


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    if not HAVE_JAVA:
        pytest.skip("local Spark needs Java 17+")
    from harness import local_spark

    s = local_spark(tmp_path_factory.mktemp("warehouse"), memory="4g", partitions=4)
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()
