"""Reader for the NHS ODS directory snapshot (S10, ``ods_api_orgs``).

One function, shared by the local pipeline and the Databricks bronze layer, so both read
relationships identically: ``read_relationships`` flattens every relationship of every organisation
into one row, keeping the ODS ids and dates as published.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pandas as pd

COLUMNS = [
    "org_code",
    "relationship_id",
    "target_code",
    "target_role_id",
    "status",
    "start_date",
    "end_date",
]


def read_relationships(path: Path | str) -> pd.DataFrame:
    """All relationships in the snapshot (active and inactive), sorted for stable output."""
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)["record"]
            for rel in (rec.get("Rels") or {}).get("Rel", []):
                dates = {d["Type"]: d for d in rel.get("Date", [])}
                op = dates.get("Operational", {})
                target = rel["Target"]
                rows.append(
                    (
                        rec["OrgId"]["extension"],
                        rel["id"],
                        target["OrgId"]["extension"],
                        target["PrimaryRoleId"]["id"],
                        rel["Status"],
                        op.get("Start"),
                        op.get("End"),
                    )
                )
    out = pd.DataFrame(rows, columns=COLUMNS).astype(object)
    out = out.sort_values(COLUMNS[:5] + ["start_date"], na_position="first")
    out = out.reset_index(drop=True)
    return out.where(out.notna(), None)  # missing dates are None, not NaN
