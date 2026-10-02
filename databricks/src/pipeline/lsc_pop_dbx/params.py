"""Pipeline configuration: table names and the lsc-pop config shipped inside the wheel.

Bundle variables reach the pipeline as Spark conf keys (``resources/lsc_pop.pipeline.yml``):

=========================  ==========================================================
``lsc_pop.catalog``        Unity Catalog catalog (must already exist)
``lsc_pop.schema_<layer>`` schema for bronze / silver / gold / audit (must already exist)
``lsc_pop.raw_dir``        folder of raw files, e.g. ``/Volumes/<cat>/<schema>/<vol>/raw``
``lsc_pop.manifest_path``  manifest JSON written by the ingest task
``lsc_pop.bundle_target``  dev / test / prod (provenance only)
``lsc_pop.git_commit``     git commit of the deployed bundle (provenance only)
``lsc_pop.local``          ``true`` only in the local test harness (batch reads, no Auto Loader)
=========================  ==========================================================

Every setting that changes the numbers comes from the lsc-pop ``config.yaml`` bundled in the
wheel (``lsc_pop.config.load_config``), never from the bundle, so Databricks and local runs share
one config and one config hash (ADR-0023).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from lsc_pop.config import Config, load_config

LAYERS = ("bronze", "silver", "gold", "audit")


@dataclass(frozen=True)
class Names:
    catalog: str
    schemas: dict[str, str]
    raw_dir: str
    manifest_path: str
    bundle_target: str
    git_commit: str
    local: bool

    def fq(self, layer: str, table: str) -> str:
        """Fully qualified ``catalog.schema.table`` (default publishing mode, multi-schema)."""
        return f"{self.catalog}.{self.schemas[layer]}.{table}"

    def raw(self, source_id: str, file: str) -> str:
        return f"{self.raw_dir.rstrip('/')}/{source_id}/{file}"


def names_from_conf(spark) -> Names:
    get = spark.conf.get
    return Names(
        catalog=get("lsc_pop.catalog"),
        schemas={layer: get(f"lsc_pop.schema_{layer}") for layer in LAYERS},
        raw_dir=get("lsc_pop.raw_dir"),
        manifest_path=get("lsc_pop.manifest_path", ""),
        bundle_target=get("lsc_pop.bundle_target", "local"),
        git_commit=get("lsc_pop.git_commit", ""),
        local=get("lsc_pop.local", "false").lower() == "true",
    )


@lru_cache(maxsize=1)
def config() -> Config:
    """The lsc-pop config: the copy bundled in the wheel (or the repo checkout locally).

    ``LSC_POP_CONFIG`` (environment variable) points elsewhere; it's used by the tests only.
    """
    return load_config(os.environ.get("LSC_POP_CONFIG") or None)
