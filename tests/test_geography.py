from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from lsc_pop import geography
from lsc_pop.config import PROJECT_ROOT, load_config
from lsc_pop.download import RawDataError
from lsc_pop.provenance import RunContext, read_run_log
from lsc_pop.validate import ValidationFailed

# Six England LSOAs in two ICBs (QE1-like focus ICB "E54000048" and another), plus one Welsh LSOA.
NHS_ROWS = [
    # LSOA, SICBL, SICBL ODS, ICB, ICB ODS, NHSER, LAD
    ("E01000001", "E38000001", "00Q", "E54000048", "QE1", "E40000010", "E06000008"),
    ("E01000002", "E38000001", "00Q", "E54000048", "QE1", "E40000010", "E06000008"),
    ("E01000003", "E38000002", "00R", "E54000048", "QE1", "E40000010", "E06000009"),
    ("E01000004", "E38000003", "01F", "E54000008", "QYG", "E40000010", "E06000006"),
    ("E01000005", "E38000003", "01F", "E54000008", "QYG", "E40000010", "E06000006"),
    ("E01000006", "E38000003", "01F", "E54000008", "QYG", "E40000010", "E06000006"),
]
CENSUS_ROWS = [
    # OA, LSOA, MSOA, LTLA21
    ("E00000001", "E01000001", "E02000001", "E07000027"),
    ("E00000002", "E01000001", "E02000001", "E07000027"),  # 2 OAs in one LSOA -> dedup
    ("E00000003", "E01000002", "E02000001", "E07000027"),
    ("E00000004", "E01000003", "E02000002", "E07000031"),
    ("E00000005", "E01000004", "E02000003", "E06000006"),
    ("E00000006", "E01000005", "E02000003", "E06000006"),
    ("E00000007", "E01000006", "E02000004", "E06000006"),
    ("W00000001", "W01000001", "W02000001", "W06000001"),
]
REGION_ROWS = [
    ("E07000027", "E12000002"),
    ("E07000031", "E12000002"),
    ("E06000006", "E12000002"),
]


def _frames(nhs=NHS_ROWS, census=CENSUS_ROWS, region=REGION_ROWS):
    nhs_df = pd.DataFrame(
        [
            {
                "LSOA21CD": ls, "LSOA21NM": f"name {ls}", "SICBL26CD": sc, "SICBL26CDH": so,
                "SICBL26NM": f"sicbl {sc}", "ICB26CD": ic, "ICB26CDH": io, "ICB26NM": f"icb {ic}",
                "NHSER26CD": nr, "NHSER26CDH": "Y62", "NHSER26NM": "North West", "LAD26CD": lad,
                "LAD26NM": f"lad {lad}", "ObjectId": i,
            }
            for i, (ls, sc, so, ic, io, nr, lad) in enumerate(nhs, 1)
        ]
    )  # fmt: skip
    census_df = pd.DataFrame(
        [
            {
                "OA21CD": oa, "LSOA21CD": ls, "LSOA21NM": "", "LSOA21NMW": "", "MSOA21CD": ms,
                "MSOA21NM": f"msoa {ms}", "MSOA21NMW": "", "LAD22CD": lt, "LAD22NM": f"ltla {lt}",
                "LAD22NMW": "", "ObjectId": i,
            }
            for i, (oa, ls, ms, lt) in enumerate(census, 1)
        ]
    )  # fmt: skip
    region_df = pd.DataFrame(
        [
            {"LAD22CD": lt, "LAD22NM": f"ltla {lt}", "RGN22CD": rg, "RGN22NM": "North West"}
            for lt, rg in region
        ]
    )
    return nhs_df, census_df, region_df


def _install(project: Path, frames, config_edit=None) -> RunContext:
    """Write fake raw files + manifest into a project copy and return a RunContext."""
    cfg_path = project / "config" / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    data["geography"]["expected_lsoa_count"] = 6
    if config_edit:
        config_edit(data)
    cfg_path.write_text(yaml.safe_dump(data, sort_keys=False))
    cfg = load_config(cfg_path)
    g = cfg.geography
    entries = []
    for spec, df in zip((g.nhs, g.census, g.ltla_region), frames, strict=True):
        path = project / "data" / "raw" / spec.source / spec.file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xef\xbb\xbf" + df.to_csv(index=False).encode())  # BOM, like ONS
        entries.append(
            {"source_id": spec.source, "file": spec.file,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )  # fmt: skip
    (project / "data" / "manifest.json").write_text(json.dumps({"files": entries}))
    return RunContext.create(cfg, run_id="t")


def _checks(ctx):
    return {r["check_id"]: r for r in read_run_log(ctx.checks_path)}


def test_builds_lookup_england(project_copy):
    ctx = _install(project_copy, _frames())
    lk = geography.run(ctx)
    assert list(lk.columns) == geography.OUTPUT_COLUMNS
    assert lk["lsoa21_code"].tolist() == [r[0] for r in NHS_ROWS]  # sorted, Wales dropped
    assert lk["in_footprint"].all()
    assert lk["in_focus_icb"].sum() == 3
    assert set(lk["nhs_geog_vintage"]) == {"2026-04"}
    row = lk.set_index("lsoa21_code").loc["E01000003"]
    assert (row["msoa21_code"], row["ltla21_code"], row["rgn21_code"]) == (
        "E02000002",
        "E07000031",
        "E12000002",
    )
    checks = _checks(ctx)
    assert all(c["passed"] for c in checks.values())
    assert checks["GEO-10"]["metrics"]["lads_split"] == 0
    out = project_copy / "data" / "interim" / "geography" / "lsoa_lookup"
    assert out.with_suffix(".parquet").is_file() and out.with_suffix(".csv").is_file()
    meta = json.loads((out.parent / "lsoa_lookup.metadata.json").read_text())
    assert {s["id"] for s in meta["sources"]} == {"S7", "S7b", "S7c"}
    steps = [r["step"] for r in read_run_log(ctx.log_path)]
    assert steps == ["geography.read_nhs", "geography.read_census", "geography.read_ltla_region",
                     "geography.build_lookup"]  # fmt: skip
    census_step = next(
        r for r in read_run_log(ctx.log_path) if r["step"] == "geography.read_census"
    )
    reasons = {d["reason"]: d["rows"] for d in census_step["rows_dropped"]}
    assert reasons == {
        "exact duplicate rows after column selection (e.g. OA rows)": 1,
        "non-England LSOAs": 1,
    }
    pd.testing.assert_frame_equal(geography.load_lookup(ctx.cfg), lk)


def test_icbs_footprint_mode(project_copy):
    def edit(d):
        d["footprint"]["mode"] = "icbs"
        d["footprint"]["icb_codes"] = ["E54000008"]

    lk = geography.run(_install(project_copy, _frames(), edit))
    assert lk.loc[lk["in_footprint"], "lsoa21_code"].tolist() == [
        "E01000004",
        "E01000005",
        "E01000006",
    ]
    assert len(geography.load_lookup(load_config(project_copy / "config/config.yaml"), True)) == 3


def test_unknown_icb_code_fails(project_copy):
    def edit(d):
        d["footprint"]["focus_icb_codes"] = ["E54999999"]

    with pytest.raises(ValueError, match="E54999999"):
        geography.run(_install(project_copy, _frames(), edit))


def test_lsoa_missing_from_census_lookup_fails(project_copy):
    census = [r for r in CENSUS_ROWS if r[1] != "E01000006"]
    with pytest.raises(ValidationFailed, match="GEO-01"):
        geography.run(_install(project_copy, _frames(census=census)))


def test_expected_count_mismatch_fails(project_copy):
    def edit(d):
        d["geography"]["expected_lsoa_count"] = 7

    ctx = _install(project_copy, _frames())
    ctx2 = _install(project_copy, _frames(), edit)
    assert ctx.cfg.geography.expected_lsoa_count == 6
    with pytest.raises(ValidationFailed, match="GEO-02"):
        geography.run(ctx2)


def test_sicbl_in_two_icbs_fails(project_copy):
    nhs = list(NHS_ROWS)
    ls, sc, so, _, _, nr, lad = nhs[3]
    nhs[3] = (ls, "E38000002", "00R", "E54000008", "QYG", nr, lad)
    with pytest.raises(ValidationFailed, match="GEO-05"):
        geography.run(_install(project_copy, _frames(nhs=nhs)))


def test_ltla_missing_region_fails(project_copy):
    with pytest.raises(ValidationFailed, match="GEO-04"):
        geography.run(_install(project_copy, _frames(region=REGION_ROWS[:2])))


def test_lad_split_across_icbs_is_informational(project_copy):
    nhs = list(NHS_ROWS)
    ls, *_, nr, lad = nhs[1]
    nhs[1] = (ls, "E38000003", "01F", "E54000008", "QYG", nr, lad)  # LAD E06000008 in both ICBs
    ctx = _install(project_copy, _frames(nhs=nhs))
    geography.run(ctx)
    assert _checks(ctx)["GEO-10"]["metrics"]["lads_split"] == 1


def test_new_lookup_vintage_is_config_only(project_copy):
    """A renamed-column lookup (e.g. a 2027 vintage) works by editing config alone."""
    nhs_df, census_df, region_df = _frames()
    nhs_df = nhs_df.rename(columns=lambda c: c.replace("26", "27"))

    def edit(d):
        d["geography"]["nhs"]["vintage"] = "2027-04"
        d["geography"]["nhs"]["columns"] = {
            k.replace("26", "27"): v for k, v in d["geography"]["nhs"]["columns"].items()
        }

    lk = geography.run(_install(project_copy, (nhs_df, census_df, region_df), edit))
    assert set(lk["nhs_geog_vintage"]) == {"2027-04"}
    assert lk["icb_code"].notna().all()


def test_column_mismatch_gives_actionable_error(project_copy):
    nhs_df, census_df, region_df = _frames()
    nhs_df = nhs_df.rename(columns={"ICB26CD": "ICB27CD"})
    with pytest.raises(KeyError, match="ICB26CD.*update config.geography"):
        geography.run(_install(project_copy, (nhs_df, census_df, region_df)))


def test_tampered_raw_file_rejected(project_copy):
    ctx = _install(project_copy, _frames())
    raw = project_copy / "data" / "raw" / "S7" / ctx.cfg.geography.nhs.file
    raw.write_bytes(raw.read_bytes() + b"\n")
    with pytest.raises(RawDataError):
        geography.run(ctx)


# --- real data (skipped unless downloaded) -------------------------------------------------

REAL_RAW = PROJECT_ROOT / "data" / "raw" / "S7"


@pytest.mark.skipif(not REAL_RAW.exists(), reason="real S7 not downloaded")
def test_real_lookup(tmp_path):
    cfg = load_config(PROJECT_ROOT / "config" / "config.yaml")
    ctx = RunContext.create(cfg, run_id="pytest_real_geography")
    try:
        lk = geography.build_lookup(ctx)
        assert len(lk) == 33_755
        focus = lk[lk["in_focus_icb"]]
        assert len(focus) == 1_060
        assert set(focus["icb_ods_code"]) == {"QE1"}
        assert focus["sicbl_code"].nunique() == 8
        assert {"E07000027", "E07000031"} <= set(focus["ltla21_code"])  # Barrow, South Lakeland
        assert lk["icb_code"].nunique() == 36
    finally:
        import shutil

        shutil.rmtree(ctx.out_dir)
