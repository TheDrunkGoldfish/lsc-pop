"""Configuration loading, validation and hashing.

Everything that changes the numbers lives in ``config/config.yaml``. It is validated here with
pydantic (unknown keys are rejected) and hashed into every run's metadata. The hash covers the
validated config *and* the content of every mapping file it references, so editing a mapping
changes the hash just as editing a value does.

Relative paths in the config are resolved against the project root: the parent of the directory
holding the config file (i.e. ``<root>/config/config.yaml``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Mid2025(_Strict):
    enabled: bool = False


class Footprint(_Strict):
    mode: Literal["england", "icbs"] = "england"
    icb_codes: list[str] = Field(default_factory=list)
    focus_icb_codes: list[str] = Field(default_factory=list)
    extra_lsoas_from_trust_catchments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_mode(self) -> Footprint:
        if self.mode == "icbs" and not self.icb_codes:
            raise ValueError(
                "footprint.mode == 'icbs' requires at least one footprint.icb_codes entry"
            )
        if self.mode == "england" and self.extra_lsoas_from_trust_catchments:
            raise ValueError(
                "footprint.extra_lsoas_from_trust_catchments has no effect when mode == 'england'"
            )
        return self


class Age(_Strict):
    max_age: int = Field(90, ge=1)
    bands_file: Path
    census_classifications_file: Path = Path("config/mappings/census_age_classifications.csv")
    band_sets: list[str] = Field(default_factory=lambda: ["5yr", "10yr"])


class Ethnicity(_Strict):
    mapping_file: Path
    levels: list[Literal["19", "6", "5"]] = Field(default_factory=lambda: ["19", "6"])


class IPF(_Strict):
    tolerance: float = Field(1e-6, gt=0)  # max abs row-margin error (persons) at convergence
    max_iter: int = Field(1000, ge=1)
    # Added to every LTLA seed count before fitting so that ethnic groups/ages with no seed
    # people can still receive the people their margins require (ADR-0016).
    seed_floor: float = Field(0.5, ge=0)
    # LTLAs blocked at every useful age detail borrow another LTLA's seed (ADR-0011).
    seed_substitutes: dict[str, str] = Field(default_factory=lambda: {"E06000053": "E06000052"})
    # Seed floors compared in the Stage C sensitivity run (focus ICB only; ADR-0016).
    sensitivity_floors: list[float] = Field(default_factory=lambda: [0.01, 0.5, 2.0])


class Rollforward(_Strict):
    """Stage D (ADR-0004, ADR-0017)."""

    # 2021 ages whose pooled ethnic shares stand in for cohorts born after Census day
    # (ages 0..shift-1 at the reference date). Brief default: age 0 only.
    newborn_proxy_ages: list[int] = Field(default_factory=lambda: [0])


class Reconciliation(_Strict):
    """Census margin reconciliation (ADR-0015)."""

    margin_source: Literal["rm032", "rm200", "mean"] = "rm200"
    # Soft check CEN-12 flags bands where |adjustment| > max(warn_abs persons, warn_rel x total).
    warn_abs: float = Field(10, ge=0)
    warn_rel: float = Field(0.05, ge=0)


class Rounding(_Strict):
    integerise: bool = False
    seed: int = 20240630

    @model_validator(mode="after")
    def _not_implemented(self) -> Rounding:
        if self.integerise:
            raise ValueError("rounding.integerise is not implemented (ADR-0005: floats only)")
        return self


class LocalQuintile(_Strict):
    enabled: bool = True
    within: Literal["icb", "lad"] = "icb"


class Deprivation(_Strict):
    """Stage F (ADR-0008). New IoD edition: register it and point source/file here."""

    source: str = "S8"
    file: str = "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"
    edition: str = "IoD 2025"
    core20_max_decile: int = Field(2, ge=1, le=10)
    local_quintile: LocalQuintile = Field(default_factory=LocalQuintile)


class Catchments(_Strict):
    """Stage G trust catchments (ADR-0019)."""

    source: str = "S9"
    file: str = "nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods"
    catchment_year: int = 2024
    admission_type: Literal["All admissions"] = "All admissions"


class Paths(_Strict):
    raw: Path = Path("data/raw")
    interim: Path = Path("data/interim")
    processed: Path = Path("data/processed")
    outputs: Path = Path("outputs")
    manifest: Path = Path("data/manifest.json")
    sources: Path = Path("config/sources.yaml")


class LookupSpec(_Strict):
    """One raw lookup file and how its columns map to the pipeline's standard names."""

    source: str  # source id in config/sources.yaml
    file: str  # file name under data/raw/<source>/
    vintage: str  # e.g. "2026-04"; recorded in outputs
    key: str = "lsoa21cd"  # standard name of the join key (after renaming)
    columns: dict[str, str]  # raw column name -> standard name (only these are kept)

    @model_validator(mode="after")
    def _key_present(self) -> LookupSpec:
        if self.key not in self.columns.values():
            raise ValueError(f"lookup key {self.key!r} is not among the renamed columns")
        if len(set(self.columns.values())) != len(self.columns):
            raise ValueError("two raw columns map to the same standard name")
        return self


REQUIRED_NHS_COLUMNS = {
    "lsoa21cd", "lsoa21nm", "sicbl_cd", "sicbl_ods", "sicbl_nm", "icb_cd", "icb_ods", "icb_nm",
    "nhser_cd", "nhser_nm", "lad_cd", "lad_nm",
}  # fmt: skip
REQUIRED_CENSUS_COLUMNS = {"lsoa21cd", "msoa21cd", "msoa21nm", "ltla21cd", "ltla21nm"}
REQUIRED_REGION_COLUMNS = {"ltla21cd", "rgn21cd", "rgn21nm"}


class Geography(_Strict):
    """Lookups (ADR-0012/0014). A new vintage = new source entry + edit here; no code change."""

    expected_lsoa_count: int = Field(33_755, ge=1)
    nhs: LookupSpec  # LSOA21 -> sub-ICB -> ICB -> NHS region -> LAD (current vintage)
    census: LookupSpec  # LSOA21 -> MSOA21 -> LTLA 2021 (fixed: Census 2021 geography)
    ltla_region: LookupSpec  # LTLA 2021 -> ONS region

    @model_validator(mode="after")
    def _required(self) -> Geography:
        for name, spec, req in (
            ("nhs", self.nhs, REQUIRED_NHS_COLUMNS),
            ("census", self.census, REQUIRED_CENSUS_COLUMNS),
            ("ltla_region", self.ltla_region, REQUIRED_REGION_COLUMNS),
        ):
            missing = req - set(spec.columns.values())
            if missing:
                raise ValueError(f"geography.{name}.columns must produce {sorted(missing)}")
        return self


class MYE(_Strict):
    """Current-year LSOA SYOA x sex population estimates (S5). New years: docs/updating.md."""

    source: str = "S5"
    file: str
    sheet_template: str = "Mid-{year} LSOA 2021"  # formatted with reference_year
    header_row: int = Field(3, ge=0)  # 0-based row of the column header
    edition: str  # human-readable; recorded in outputs


class Config(_Strict):
    reference_year: int = Field(2024, ge=2021)
    variant: Literal["cohort", "static"] = "cohort"
    # None -> reference_year - 2021 (Census day 21 Mar 2021 -> 30 Jun of reference year). ADR-0004.
    cohort_shift_years: int | None = Field(None, ge=0)
    mid2025: Mid2025 = Field(default_factory=Mid2025)
    mye: MYE
    footprint: Footprint = Field(default_factory=Footprint)
    focus_trusts: list[str] = Field(default_factory=list)
    age: Age
    ethnicity: Ethnicity
    ipf: IPF = Field(default_factory=IPF)
    rollforward: Rollforward = Field(default_factory=Rollforward)
    reconciliation: Reconciliation = Field(default_factory=Reconciliation)
    rounding: Rounding = Field(default_factory=Rounding)
    deprivation: Deprivation = Field(default_factory=Deprivation)
    catchments: Catchments = Field(default_factory=Catchments)
    geography: Geography
    paths: Paths = Field(default_factory=Paths)

    _root: Path = PrivateAttr(default=PROJECT_ROOT)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, p: Path | str) -> Path:
        """Resolve a config-relative path against the project root."""
        p = Path(p)
        return p if p.is_absolute() else self._root / p

    @property
    def shift_years(self) -> int:
        """Cohort-ageing shift in whole years (ADR-0004)."""
        if self.cohort_shift_years is not None:
            return self.cohort_shift_years
        return self.reference_year - 2021

    @property
    def mye_sheet(self) -> str:
        return self.mye.sheet_template.format(year=self.reference_year)

    @property
    def reference_date(self) -> str:
        return f"{self.reference_year}-06-30"

    def mapping_files(self) -> dict[str, Path]:
        return {
            "age.bands_file": self.resolve(self.age.bands_file),
            "age.census_classifications_file": self.resolve(self.age.census_classifications_file),
            "ethnicity.mapping_file": self.resolve(self.ethnicity.mapping_file),
            "paths.sources": self.resolve(self.paths.sources),
        }

    def config_hash(self) -> str:
        """SHA-256 over the canonical JSON of the config plus referenced mapping file contents.

        ``paths`` is excluded: where files live doesn't change the numbers, and excluding it lets a
        local run and a Databricks run (paths under /Volumes) share a config hash (ADR-0023).
        """
        h = hashlib.sha256()
        payload = self.model_dump(mode="json", exclude={"paths"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        h.update(canonical.encode())
        for key, path in sorted(self.mapping_files().items()):
            h.update(f"\n{key}\n".encode())
            h.update(path.read_bytes())
        return h.hexdigest()


def with_paths(cfg: Config, **paths: Path | str) -> Config:
    """Copy of ``cfg`` with some ``paths`` replaced (e.g. raw=/Volumes/...). Hash unaffected."""
    new = cfg.model_copy(
        update={"paths": cfg.paths.model_copy(update={k: Path(v) for k, v in paths.items()})}
    )
    new._root = cfg.root
    return new


BUNDLED_DIR = Path(__file__).resolve().parent / "_bundled"


def default_config_path() -> Path:
    """The repo's config when running from a checkout; the copy bundled in the wheel otherwise.

    The wheel ships ``config/`` and ``data/manifest.json`` under ``lsc_pop/_bundled/`` so an
    installed package (e.g. on Databricks) loads exactly the same config, mappings and manifest.
    """
    if DEFAULT_CONFIG_PATH.is_file():
        return DEFAULT_CONFIG_PATH
    bundled = BUNDLED_DIR / "config" / "config.yaml"
    if bundled.is_file():
        return bundled
    raise FileNotFoundError("no config/config.yaml in the checkout or the installed package")


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate a config file. Raises ``pydantic.ValidationError`` on bad input."""
    path = Path(path if path is not None else default_config_path()).resolve()
    raw = yaml.safe_load(path.read_text()) or {}
    cfg = Config.model_validate(raw)
    cfg._root = path.parent.parent
    for key, p in cfg.mapping_files().items():
        if not p.is_file():
            raise FileNotFoundError(f"{key} not found: {p}")
    return cfg
