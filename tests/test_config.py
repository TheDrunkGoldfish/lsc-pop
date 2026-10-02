from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lsc_pop.config import DEFAULT_CONFIG_PATH, Config, load_config
from lsc_pop.mappings import load_age_bands, load_ethnicity_mapping


def _edit(project: Path, **changes) -> Path:
    path = project / "config" / "config.yaml"
    data = yaml.safe_load(path.read_text())
    for dotted, value in changes.items():
        node = data
        *parents, leaf = dotted.split("__")
        for p in parents:
            node = node[p]
        node[leaf] = value
    path.write_text(yaml.safe_dump(data))
    return path


def test_default_config_validates():
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert cfg.reference_year == 2024
    assert cfg.variant == "cohort"
    assert cfg.footprint.mode == "england"
    assert cfg.mid2025.enabled is False
    assert cfg.rounding.integerise is False
    assert cfg.reference_date == "2024-06-30"


def test_unknown_key_rejected(project_copy):
    path = _edit(project_copy, bogus=1)
    with pytest.raises(ValidationError):
        load_config(path)


def test_unknown_nested_key_rejected(project_copy):
    path = _edit(project_copy, ipf__bogus=1)
    with pytest.raises(ValidationError):
        load_config(path)


def test_icbs_mode_requires_codes(project_copy):
    path = _edit(project_copy, footprint__mode="icbs")
    with pytest.raises(ValidationError):
        load_config(path)


def test_integerise_not_implemented(project_copy):
    path = _edit(project_copy, rounding__integerise=True)
    with pytest.raises(ValidationError):
        load_config(path)


def test_hash_stable_across_reloads(project_copy):
    path = project_copy / "config" / "config.yaml"
    assert load_config(path).config_hash() == load_config(path).config_hash()


def test_hash_changes_with_value(project_copy, cfg):
    before = cfg.config_hash()
    after = load_config(_edit(project_copy, ipf__tolerance=1e-5)).config_hash()
    assert before != after


def test_hash_changes_with_mapping_file(project_copy, cfg):
    before = cfg.config_hash()
    bands = project_copy / "config" / "mappings" / "age_bands.csv"
    bands.write_text(bands.read_text() + "\n")
    assert load_config(project_copy / "config" / "config.yaml").config_hash() != before


def test_paths_resolve_against_project_root(project_copy, cfg):
    assert cfg.root == project_copy
    assert cfg.resolve(cfg.paths.raw) == project_copy / "data" / "raw"


def test_missing_mapping_file_fails(project_copy):
    (project_copy / "config" / "mappings" / "age_bands.csv").unlink()
    with pytest.raises(FileNotFoundError):
        load_config(project_copy / "config" / "config.yaml")


def test_config_is_frozen(cfg: Config):
    with pytest.raises(ValidationError):
        cfg.variant = "static"


# --- mapping files -------------------------------------------------------------------------


def test_ethnicity_mapping_well_formed(cfg):
    m = load_ethnicity_mapping(cfg.resolve(cfg.ethnicity.mapping_file))
    assert len(m) == 19
    assert m["code_19"].is_unique
    assert m["code_5"].nunique() == 5
    assert m["code_6"].nunique() == 6
    assert set(m.loc[m["code_19"] == 13, "code_6"]) == {"WB"}


def test_ethnicity_mapping_rejects_missing_code(cfg, tmp_path):
    src = cfg.resolve(cfg.ethnicity.mapping_file)
    bad = tmp_path / "bad.csv"
    bad.write_text("\n".join(src.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ValueError, match="exactly"):
        load_ethnicity_mapping(bad)


@pytest.mark.parametrize("band_set", ["5yr", "10yr"])
def test_age_bands_tile_0_to_max(cfg, band_set):
    b = load_age_bands(cfg.resolve(cfg.age.bands_file), cfg.age.max_age, [band_set])
    assert b["age_min"].min() == 0
    assert b["age_max"].max() == cfg.age.max_age
    assert b.iloc[-1]["band_label"] == "90+"


def test_age_bands_reject_gap(tmp_path):
    bad = tmp_path / "bands.csv"
    bad.write_text("band_set,band_label,age_min,age_max\nx,0-4,0,4\nx,6-90,6,90\n")
    with pytest.raises(ValueError, match="tile"):
        load_age_bands(bad, 90)


def test_age_bands_reject_overlap(tmp_path):
    bad = tmp_path / "bands.csv"
    bad.write_text("band_set,band_label,age_min,age_max\nx,0-5,0,5\nx,5-90,5,90\n")
    with pytest.raises(ValueError, match="tile"):
        load_age_bands(bad, 90)


def test_age_bands_unknown_set(cfg):
    with pytest.raises(ValueError, match="unknown"):
        load_age_bands(cfg.resolve(cfg.age.bands_file), 90, ["7yr"])


def test_shift_years_derived_from_reference_year(project_copy):
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert cfg.shift_years == 3
    assert cfg.mye_sheet == "Mid-2024 LSOA 2021"
    cfg25 = load_config(_edit(project_copy, reference_year=2025))
    assert cfg25.shift_years == 4
    assert cfg25.mye_sheet == "Mid-2025 LSOA 2021"
    assert load_config(_edit(project_copy, cohort_shift_years=2)).shift_years == 2


def test_config_hash_ignores_paths(cfg):
    from lsc_pop.config import with_paths

    moved = with_paths(cfg, raw="/Volumes/c/s/v/raw", manifest="/Volumes/c/s/v/manifest.json")
    assert moved.config_hash() == cfg.config_hash()
    assert str(moved.resolve(moved.paths.raw)) == "/Volumes/c/s/v/raw"
    assert moved.root == cfg.root
