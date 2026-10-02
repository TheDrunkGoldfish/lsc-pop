"""Minimal streaming reader for OpenDocument spreadsheets (.ods).

The OHID catchment file (S9) has a ~550 MB ``content.xml``. pandas/odfpy load the whole DOM and are
very slow, so this module streams the XML from inside the zip and returns only the requested sheets
as lists of rows. Numeric cells come back as their ``office:value`` string; text cells as text.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_MAX_REPEAT = 1000  # cap for repeated empty cells/rows (ODS pads sheets with huge repeats)


def read_ods_sheets(path: Path | str, sheets: list[str]) -> dict[str, list[list[str]]]:
    wanted = set(sheets)
    out: dict[str, list[list[str]]] = {}
    current: str | None = None
    with zipfile.ZipFile(path) as z, z.open("content.xml") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = el.tag
            if ev == "start" and tag == _T + "table":
                name = el.get(_T + "name")
                current = name if name in wanted else None
                if current:
                    out[current] = []
            elif ev == "end" and tag == _T + "table-row":
                if current:
                    row: list[str] = []
                    for c in el:
                        if c.tag not in (_T + "table-cell", _T + "covered-table-cell"):
                            continue
                        rep = min(int(c.get(_T + "number-columns-repeated", "1")), _MAX_REPEAT)
                        v = c.get(_O + "value")
                        if v is None:
                            v = "\n".join("".join(p.itertext()) for p in c.findall(_X + "p"))
                        row += [v] * rep
                    while row and row[-1] == "":
                        row.pop()
                    if row:
                        rep_r = min(int(el.get(_T + "number-rows-repeated", "1")), _MAX_REPEAT)
                        out[current] += [row] * rep_r
                el.clear()
            elif ev == "end" and tag == _T + "table":
                current = None
                el.clear()
    missing = wanted - set(out)
    if missing:
        raise KeyError(f"{Path(path).name}: sheets not found: {sorted(missing)}")
    return out


def sheet_to_frame(rows: list[list[str]], header_row: int) -> pd.DataFrame:
    """Rows -> DataFrame using ``rows[header_row]`` as header (whitespace-normalised)."""
    header = [" ".join(h.split()) for h in rows[header_row]]
    body = [r + [""] * (len(header) - len(r)) for r in rows[header_row + 1 :]]
    return pd.DataFrame([r[: len(header)] for r in body], columns=header)
