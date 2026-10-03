"""A tiny, internally consistent synthetic copy of every raw source, in the real file formats.

10 LSOAs in 2 LTLAs (one blocked at single year of age, exercising the regional seed fallback),
3 MSOAs, 1 ICB, 2 sub-ICBs, 2 trusts. Written with the real file names, so both the local
lsc-pop pipeline and the Databricks pipeline (local harness) can run on it and be compared.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from lsc_pop import census
from lsc_pop.config import PROJECT_ROOT
from lsc_pop.mappings import load_ethnicity_mapping

LSOAS = [f"E0100{i:04d}" for i in range(1, 11)]
LTLA = {ls: ("E07000001" if i < 6 else "E07000002") for i, ls in enumerate(LSOAS)}
MSOA = {
    ls: ("E02000001" if i < 3 else "E02000002" if i < 6 else "E02000003")
    for i, ls in enumerate(LSOAS)
}
LAD = {ls: ("E06000001" if i < 6 else "E06000002") for i, ls in enumerate(LSOAS)}
SICBL = {ls: ("E38000001" if i < 5 else "E38000002") for i, ls in enumerate(LSOAS)}
ICB, NHSER, REGION = "E54000001", "E40000001", "E12000002"
TRUSTS = ["RXL", "RXN"]
BANDS = [(1, 0, 24), (2, 25, 34), (3, 35, 49), (4, 50, 64), (5, 65, 90)]


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _xlsx(sheet: str, header: list[str], rows: list[list]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(3):
        ws.append(["title"])
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _ods(sheets: dict[str, list[list]]) -> bytes:
    t = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
    tx = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    o = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
    parts = [
        f'<office:document-content xmlns:office="{o}" xmlns:table="{t}" xmlns:text="{tx}">'
        "<office:body><office:spreadsheet>"
    ]
    for name, rows in sheets.items():
        parts.append(f'<table:table table:name="{name}">')
        for row in rows:
            parts.append("<table:table-row>")
            for v in row:
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    parts.append(
                        f'<table:table-cell office:value-type="float" office:value="{v}">'
                        f"<text:p>{v}</text:p></table:table-cell>"
                    )
                else:
                    parts.append(f"<table:table-cell><text:p>{v}</text:p></table:table-cell>")
            parts.append("</table:table-row>")
        parts.append("</table:table>")
    parts.append("</office:spreadsheet></office:body></office:document-content>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("content.xml", "".join(parts))
    return buf.getvalue()


def make_project(root: Path, seed: int = 7) -> Path:
    """Create ``root/config`` (copied, then adjusted) and ``root/data/raw`` + manifest."""
    rng = np.random.default_rng(seed)
    shutil.copytree(PROJECT_ROOT / "config", root / "config")
    cfg_path = root / "config" / "config.yaml"
    c = yaml.safe_load(cfg_path.read_text())
    c["geography"]["expected_lsoa_count"] = len(LSOAS)
    c["footprint"]["focus_icb_codes"] = [ICB]
    c["focus_trusts"] = TRUSTS
    c["ipf"]["sensitivity_floors"] = [0.5]
    cfg_path.write_text(yaml.safe_dump(c, sort_keys=False))
    raw = root / "data" / "raw"
    eth = load_ethnicity_mapping(root / "config" / "mappings" / "ethnicity_19_to_6.csv")

    # S2 RM200 first (single years), then S1 RM032 with similar band totals (perturbed)
    r200 = {(ls, s, a): int(rng.integers(0, 6)) for ls in LSOAS for s in (1, 2) for a in range(91)}
    lines = ["GEOGRAPHY_CODE,C2021_AGE_92,C_SEX,OBS_VALUE,RECORD_COUNT"]
    for ls in LSOAS:
        for s in (1, 2):
            lines.append(f"{ls},0,{s},{sum(r200[ls, s, a] for a in range(91))},0")
            lines += [f"{ls},{a + 1},{s},{r200[ls, s, a]},0" for a in range(91)]
    _write(raw / "S2" / census.RM200[1], ("\n".join(lines) + "\n").encode())

    lines = ["GEOGRAPHY_CODE,C2021_ETH_20,C2021_AGE_6,C_SEX,OBS_VALUE,RECORD_COUNT"]
    rm032 = {}
    for ls in LSOAS:
        for b, lo, hi in BANDS:
            for s in (1, 2):
                target = sum(r200[ls, s, a] for a in range(lo, hi + 1)) + int(rng.integers(-2, 3))
                w = rng.dirichlet(np.ones(19) * 0.4)
                vals = np.floor(w * max(target, 0)).astype(int)
                rm032.update({(ls, s, b, e): int(vals[e - 1]) for e in range(1, 20)})
                lines.append(f"{ls},0,{b},{s},{int(vals.sum())},0")
                lines += [f"{ls},{e},{b},{s},{int(vals[e - 1])},0" for e in range(1, 20)]
    _write(raw / "S1" / census.RM032[1], ("\n".join(lines) + "\n").encode())

    # S4 TS021 (zip of wide CSVs; only the lsoa file is read)
    cols = {f"Ethnic group: {r.label_19}": r.code_19 for r in eth.itertuples()}
    recs = []
    for ls in LSOAS:
        vals = {
            c: sum(rm032[ls, s, b, code] for s in (1, 2) for b, _, _ in BANDS)
            + int(rng.integers(0, 2))
            for c, code in cols.items()
        }
        recs.append(
            {
                "date": 2021,
                "geography": ls,
                "geography code": ls,
                "Ethnic group: Total: All usual residents": sum(vals.values()),
                **vals,
            }
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(census.TS021[2], pd.DataFrame(recs).to_csv(index=False))
    _write(raw / "S4" / census.TS021[1], buf.getvalue())

    # S3 seeds (ONS API JSON lines); E07000002 blocked at single year -> regional split fallback
    ltlas = sorted(set(LTLA.values()))
    for (sid, file, dim, _cls), n_age, blocked in (
        (census.SEED91, 91, ["E07000002"]),
        (census.SEED23, 23, []),
    ):
        obs = []
        ages = range(91) if n_age == 91 else range(1, 24)
        for lt in ltlas:
            if lt in blocked:
                continue
            for e in [-8, *range(1, 20)]:
                for s in (1, 2):
                    for a in ages:
                        dims = [
                            {"dimension_id": "ltla", "option_id": lt},
                            {"dimension_id": "ethnic_group_tb_20b", "option_id": str(e)},
                            {"dimension_id": "sex", "option_id": str(s)},
                            {"dimension_id": dim, "option_id": str(a)},
                        ]
                        val = 0 if e == -8 else int(rng.integers(0, 8) * (rng.random() > 0.2))
                        obs.append({"dimensions": dims, "observation": val})
        line = {
            "batch": 0,
            "requested": ltlas,
            "blocked": blocked,
            "response": {
                "observations": obs,
                "total_observations": len(obs),
                "blocked_areas": len(blocked),
            },
        }
        data = gzip.compress((json.dumps(line, sort_keys=True) + "\n").encode(), mtime=0)
        _write(raw / sid / file, data)

    # S5 mid-year estimates + S5b broad ages
    mye = {(ls, s, a): int(rng.integers(0, 6)) for ls in LSOAS for s in "FM" for a in range(91)}
    header = [
        "LAD 2023 Code",
        "LAD 2023 Name",
        "LSOA 2021 Code",
        "LSOA 2021 Name",
        "Total",
        *[f"{s}{a}" for s in "FM" for a in range(91)],
    ]
    rows = [
        [
            LAD[ls],
            "lad",
            ls,
            "name",
            sum(mye[ls, s, a] for s in "FM" for a in range(91)),
            *[mye[ls, s, a] for s in "FM" for a in range(91)],
        ]
        for ls in LSOAS
    ]
    _write(raw / "S5" / "sapelsoasyoa20222024.xlsx", _xlsx("Mid-2024 LSOA 2021", header, rows))
    broad = {
        "0 to 15": (0, 15),
        "16 to 29": (16, 29),
        "30 to 44": (30, 44),
        "45 to 64": (45, 64),
        "65 and over": (65, 90),
    }
    header = [
        "LAD 2021 Code",
        "LAD 2021 Name",
        "LSOA 2021 Code",
        "LSOA 2021 Name",
        "Total",
        *[f"{s}{k}" for s in "FM" for k in broad],
    ]
    rows = [
        [
            LAD[ls],
            "lad",
            ls,
            "name",
            0,
            *[
                sum(mye[ls, s, a] for a in range(lo, hi + 1))
                for s in "FM"
                for lo, hi in broad.values()
            ],
        ]
        for ls in LSOAS
    ]
    _write(raw / "S5b" / "sapelsoabroadage20222024.xlsx", _xlsx("Mid-2024 LSOA 2021", header, rows))

    # S7 / S7b / S7c / S7d lookups (UTF-8 with BOM, like ONS)
    bom = b"\xef\xbb\xbf"
    nhs = pd.DataFrame(
        [
            {
                "LSOA21CD": ls,
                "LSOA21NM": f"name {ls}",
                "SICBL26CD": SICBL[ls],
                "SICBL26CDH": SICBL[ls][-3:],
                "SICBL26NM": f"sicbl {SICBL[ls]}",
                "ICB26CD": ICB,
                "ICB26CDH": "QE1",
                "ICB26NM": "ICB one",
                "NHSER26CD": NHSER,
                "NHSER26CDH": "Y62",
                "NHSER26NM": "North West",
                "LAD26CD": LAD[ls],
                "LAD26NM": f"lad {LAD[ls]}",
                "ObjectId": i,
            }
            for i, ls in enumerate(LSOAS, 1)
        ]
    )
    _write(
        raw / "S7" / "lsoa21_sicbl26_icb26_nhser26_lad26.csv",
        bom + nhs.to_csv(index=False).encode(),
    )
    oa = pd.DataFrame(
        [
            {
                "OA21CD": f"E00{i:06d}{k}",
                "LSOA21CD": ls,
                "LSOA21NM": "",
                "LSOA21NMW": "",
                "MSOA21CD": MSOA[ls],
                "MSOA21NM": f"msoa {MSOA[ls]}",
                "MSOA21NMW": "",
                "LAD22CD": LTLA[ls],
                "LAD22NM": f"ltla {LTLA[ls]}",
                "LAD22NMW": "",
                "ObjectId": i,
            }
            for i, ls in enumerate(LSOAS)
            for k in (0, 1)
        ]
    )
    _write(
        raw / "S7b" / "oa21_lsoa21_msoa21_lad22_exactfit_v3.csv",
        bom + oa.to_csv(index=False).encode(),
    )
    rg = pd.DataFrame(
        [
            {
                "LAD22CD": lt,
                "LAD22NM": lt,
                "RGN22CD": REGION,
                "RGN22NM": "North West",
                "ObjectId": i,
            }
            for i, lt in enumerate(ltlas)
        ]
    )
    _write(raw / "S7c" / "lad22_rgn22.csv", bom + rg.to_csv(index=False).encode())
    ut = pd.DataFrame(
        [
            {
                "LTLA22CD": lt,
                "LTLA22NM": lt,
                "UTLA22CD": "E10000001",
                "UTLA22NM": "County",
                "ObjectId": i,
            }
            for i, lt in enumerate(ltlas)
        ]
    )
    _write(raw / "S7d" / "lad22_ctyua22.csv", bom + ut.to_csv(index=False).encode())

    # S8 IoD 2025 File 7 (one LSOA per decile; real header wording)
    from lsc_pop.deprivation import IOD_PREFIXES

    iod = {
        "LSOA code (2021)": LSOAS,
        "LSOA name (2021)": LSOAS,
        "Local Authority District code (2024)": [LAD[x] for x in LSOAS],
        "Local Authority District name (2024)": "lad",
    }
    ranks = rng.permutation(len(LSOAS)) + 1
    for prefix in IOD_PREFIXES:
        iod[f"{prefix} Score"] = np.round(rng.uniform(1, 60, len(LSOAS)), 3)
        iod[f"{prefix} Rank (where 1 is most deprived)"] = ranks
        iod[f"{prefix} Decile (where 1 is most deprived 10% of LSOAs)"] = ranks
    iod["Total population: mid 2022"] = 1500
    _write(
        raw / "S8" / "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv",
        pd.DataFrame(iod).to_csv(index=False).encode(),
    )

    # S9 OHID ODS (title, note, header, rows) for catchment year 2024, all admissions
    msoas = sorted(set(MSOA.values()))
    share = {"E02000001": (0.62, 0.3), "E02000002": (0.25, 0.71), "E02000003": (0.4, 0.55)}
    t2 = [
        ["Table 2"],
        ["note"],
        [
            "Catchment year",
            "Admission type",
            "Trust code",
            "Trust name",
            "MSOA21CD",
            "Patients admitted",
            "Total patients",
            "Patients admitted as a proportion of total patients",
            "First past the post (FPTP)",
        ],
    ]
    for m in msoas:
        a, b = share[m]
        t2 += [
            [2024, "All Admissions", "RXL", "Trust L", m, 10, 20, a, "TRUE" if a > b else "FALSE"],
            [2024, "All Admissions", "RXN", "Trust N", m, 10, 20, b, "TRUE" if b >= a else "FALSE"],
            [2023, "All Admissions", "RXL", "Trust L", m, 10, 20, 0.5, "TRUE"],
        ]
    t1 = [
        ["Table 1"],
        ["note"],
        [
            "Catchment Year",
            "Admission type",
            "Trust code",
            "Trust name",
            "Trust type",
            "Sex",
            "Sex description",
            "Age group",
            "Catchment population",
        ],
    ]
    t1 += [[2024, "All Admissions", t, "x", "Acute", 1, "Male", "00 to 04", 1000] for t in TRUSTS]
    t5 = [
        ["Table 5"],
        ["note"],
        [
            "Catchment year",
            "Admission type",
            "Selection method",
            "Trust code",
            "Trust name",
            "Percentage Asian",
            "Percentage black",
            "Percentage mixed",
            "Percentage white",
            "Percentage other",
        ],
    ]
    t5 += [
        [2024, "All admissions", m, t, "x", 0.1, 0.02, 0.03, 0.8, 0.05]
        for t in TRUSTS
        for m in ("All (5% and above)", "First past the post")
    ]
    t6 = [
        ["Table 6"],
        ["note"],
        [
            "Catchment year",
            "Admission type",
            "Trust code",
            "Trust name",
            "IMD score proportion",
            "Total catchment",
            "IMD score",
            "IMD Rank",
        ],
    ]
    t6 += [[2024, "All Admissions", t, "x", 1, 1, 25.0, 1] for t in TRUSTS]
    t7 = [
        ["Table 7"],
        ["note"],
        [
            "Trust code",
            "Trust name",
            "Commisioning region",
            "Trust type",
            "Lower super output area code (LSOA21CD)",
        ],
    ]
    t7 += [[t, f"Trust {t}", "North West", "Acute - Large", LSOAS[i]] for i, t in enumerate(TRUSTS)]
    _write(
        raw / "S9" / "nhs-acute-hospital-trust-catchment-populations-data_tables-april-2026.ods",
        _ods(
            {
                "Trust_analysis": t1,
                "All_admissions": t2,
                "Ethnicity": t5,
                "Deprivation": t6,
                "Trust_area_lookup": t7,
            }
        ),
    )

    # S10 ODS directory snapshot: each trust has an active RE5 to the ICB, an old inactive RE5 to
    # another ICB, and an RE8 partner link (the pipeline must use only the active RE5).
    def _rel(rel_id, code, status, start, end=None):
        dates = {"Type": "Operational", "Start": start, **({"End": end} if end else {})}
        target = {"OrgId": {"extension": code}, "PrimaryRoleId": {"id": "RO261"}}
        return {"id": rel_id, "Status": status, "Date": [dates], "Target": target}

    lines = []
    for t in TRUSTS:
        rels = [
            _rel("RE5", "QOLD", "Inactive", "2015-04-01", "2020-03-31"),
            _rel("RE5", "QE1", "Active", "2020-04-01"),
            _rel("RE8", "QE1", "Active", "2023-07-01"),
        ]
        rec = {"OrgId": {"extension": t}, "Name": f"Trust {t}", "Rels": {"Rel": rels}}
        lines.append(json.dumps({"org_id": t, "record": rec}, sort_keys=True))
    (raw / "S10").mkdir(parents=True)
    with gzip.GzipFile(raw / "S10" / "ods_nhs_trusts.jsonl.gz", "wb", mtime=0) as gz:
        gz.write(("\n".join(lines) + "\n").encode())

    # Manifest of everything written (as the download stage would record it)
    entries = []
    for p in sorted(raw.rglob("*")):
        if p.is_file():
            entries.append(
                {
                    "source_id": p.parent.name,
                    "file": p.name,
                    "url": "synthetic",
                    "release_date": "",
                    "edition": "synthetic",
                    "retrieved_at": "",
                    "size_bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
    (root / "data" / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": entries})
    )
    return cfg_path
