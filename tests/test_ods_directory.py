from __future__ import annotations

import gzip
import json

from lsc_pop.ods_directory import COLUMNS, read_relationships


def _snapshot(path, records):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for code, rels in records.items():
            rec = (
                {"OrgId": {"extension": code}, "Rels": {"Rel": rels}}
                if rels
                else {"OrgId": {"extension": code}}
            )
            f.write(json.dumps({"org_id": code, "record": rec}) + "\n")


def _rel(rel_id, target, role, status, start, end=None):
    dates = [{"Type": "Operational", "Start": start, **({"End": end} if end else {})}]
    dates.append({"Type": "Legal", "Start": "1999-01-01"})
    return {
        "id": rel_id,
        "Status": status,
        "Date": dates,
        "Target": {"OrgId": {"extension": target}, "PrimaryRoleId": {"id": role}},
    }


def test_read_relationships_flattens_and_keeps_operational_dates(tmp_path):
    p = tmp_path / "s.jsonl.gz"
    _snapshot(
        p,
        {
            "RXN": [
                _rel("RE5", "QE1", "RO261", "Active", "2020-04-01"),
                _rel("RE5", "Q84", "RO210", "Inactive", "2016-04-01", "2020-03-31"),
            ],
            "RXL": None,  # an organisation with no relationships at all
        },
    )
    r = read_relationships(p)
    assert list(r.columns) == COLUMNS
    assert len(r) == 2 and set(r["org_code"]) == {"RXN"}
    active = r[r["status"] == "Active"].iloc[0]
    assert (active["target_code"], active["target_role_id"], active["start_date"]) == (
        "QE1",
        "RO261",
        "2020-04-01",
    )
    assert r[r["status"] == "Inactive"].iloc[0]["end_date"] == "2020-03-31"
    assert active["end_date"] is None
