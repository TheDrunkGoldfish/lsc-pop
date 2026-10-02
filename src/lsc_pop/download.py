"""Stage 0 - Source download.

Sources are registered in ``config/sources.yaml`` (what to fetch and why). This module fetches each
file once into ``data/raw/<source_id>/<file name>`` and records URL, release date, retrieved-at,
size and SHA-256 in ``data/manifest.json``.

Three fetch kinds:

* ``http``: a single file, saved byte-for-byte.
* ``nomis_paged``: a Nomis API CSV query. Nomis returns at most ``page_size`` rows per call, so the
  query is paged with ``recordoffset``. Pages are joined into one CSV (header kept once) and the row
  count is checked against Nomis's own ``RECORD_COUNT`` column. Nothing else is changed.
* ``ons_api_batched``: an ONS "Create a custom dataset" API query. The area list is fetched from the
  API, filtered by code prefix (e.g. ``E`` for England), and requested in batches under the API's
  row cap. Every response is stored verbatim, one JSON object per line, in a gzip file (mtime 0).
  Each line also carries the batch's requested area codes and the codes the API blocked
  (disclosure control).

Raw data is immutable (brief §3.6):

* a file already on disk whose SHA-256 matches its manifest entry is skipped;
* a file on disk that is missing from the manifest, or whose hash no longer matches it, is an
  error. Never overwrite it silently: delete it by hand, deliberately, and re-download;
* downloads are written to a temporary file and renamed into place only once complete, then made
  read-only (0444);
* if a re-download (after deliberate deletion) differs from the manifest hash, that's an error.
  The publisher has changed the data, which has to be reviewed before the manifest entry is removed.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import requests
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from lsc_pop.config import Config

# Cloudflare in front of api.beta.ons.gov.uk rejects library default User-Agents.
USER_AGENT = "lsc-pop/0.1 (population estimates research pipeline)"
CHUNK = 1 << 20
ONS_API = "https://api.beta.ons.gov.uk/v1"

sleep: Callable[[float], None] = time.sleep  # patched in tests


# --------------------------------------------------------------------------------------------
# Source registry
# --------------------------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceFile(_Strict):
    name: str  # file name under data/raw/<source_id>/
    url: str  # for ons_api_batched: base URL *without* area-type (it is added per batch)
    kind: Literal["http", "nomis_paged", "ons_api_batched"] = "http"
    description: str = ""
    expected_sha256: str | None = None
    # nomis_paged
    page_size: int = 25_000
    # ons_api_batched
    area_type: str | None = None
    area_prefix: str = "E"
    batch_size: int | None = None
    expected_rows: int | None = None  # nomis_paged: data rows; ons_api_batched: observations

    @model_validator(mode="after")
    def _kind_fields(self) -> SourceFile:
        if self.kind == "ons_api_batched" and not (self.area_type and self.batch_size):
            raise ValueError(f"{self.name}: ons_api_batched needs area_type and batch_size")
        return self


class Source(_Strict):
    id: str = Field(pattern=r"^S\d+[a-z]?$")
    title: str
    role: str
    publisher: str
    landing_page: str
    licence: str = "Open Government Licence v3.0"
    release_date: str  # ISO date of the edition used
    edition: str
    reference_date: str
    geography: str
    status: Literal[
        "accredited official statistics",
        "official statistics",
        "supporting information",
        "census",
        "lookup",
        "other",
    ]
    enabled: bool = True
    files: list[SourceFile]
    quirks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_names(self) -> Source:
        names = [f.name for f in self.files]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.id}: duplicate file names")
        return self


class SourceRegistry(_Strict):
    sources: list[Source]

    @model_validator(mode="after")
    def _unique_ids(self) -> SourceRegistry:
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source ids")
        return self

    def get(self, source_id: str) -> Source:
        for s in self.sources:
            if s.id == source_id:
                return s
        raise KeyError(source_id)


def load_sources(cfg: Config) -> SourceRegistry:
    path = cfg.resolve(cfg.paths.sources)
    return SourceRegistry.model_validate(yaml.safe_load(path.read_text()))


# --------------------------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------------------------


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "files": []}
    return json.loads(path.read_text())


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["files"] = sorted(manifest["files"], key=lambda e: (e["source_id"], e["file"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def manifest_entry(manifest: dict[str, Any], source_id: str, file: str) -> dict[str, Any] | None:
    for e in manifest["files"]:
        if e["source_id"] == source_id and e["file"] == file:
            return e
    return None


def record_download(manifest: dict[str, Any], entry: dict[str, Any]) -> None:
    """Add or replace the entry keyed by (source_id, file)."""
    manifest["files"] = [
        e
        for e in manifest["files"]
        if not (e["source_id"] == entry["source_id"] and e["file"] == entry["file"])
    ]
    manifest["files"].append(entry)


# --------------------------------------------------------------------------------------------
# Fetchers: each writes to ``tmp`` and returns extra manifest fields
# --------------------------------------------------------------------------------------------


class HttpSession(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


class RawDataError(RuntimeError):
    """Raised when raw data on disk conflicts with the manifest (immutability violation)."""


class FetchError(RuntimeError):
    """Raised when a remote query returns something incomplete or unexpected."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def _get(
    session: HttpSession, url: str, timeout: float, retries: int = 6, backoff: float = 30
) -> Any:
    """GET with retry on HTTP 429 / 5xx. Returns the (entered) response; caller must close it."""
    for attempt in range(retries):
        resp = session.get(url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT})
        status = getattr(resp, "status_code", 200)
        if status == 429 or status >= 500:
            resp.close()
            if attempt == retries - 1:
                break
            sleep(backoff * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    raise FetchError(f"giving up after {retries} attempts (last HTTP {status}): {url}")


def _read_all(resp: Any) -> bytes:
    try:
        return b"".join(resp.iter_content(CHUNK))
    finally:
        resp.close()


def _fetch_http(session: HttpSession, sf: SourceFile, tmp: Path, timeout: float) -> dict:
    resp = _get(session, sf.url, timeout)
    try:
        with open(tmp, "wb") as f:
            for block in resp.iter_content(CHUNK):
                f.write(block)
        headers = dict(resp.headers)
        return {
            "final_url": getattr(resp, "url", sf.url),
            "content_type": headers.get("Content-Type"),
            "last_modified": headers.get("Last-Modified"),
        }
    finally:
        resp.close()


def _fetch_nomis_paged(session: HttpSession, sf: SourceFile, tmp: Path, timeout: float) -> dict:
    sep = "&" if "?" in sf.url else "?"
    offset, n_rows, pages, header, record_count = 0, 0, 0, None, None
    with open(tmp, "w", newline="") as out:
        while True:
            url = f"{sf.url}{sep}recordoffset={offset}"
            text = _read_all(_get(session, url, timeout)).decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(text)))
            if not rows:
                raise FetchError(f"empty Nomis response: {url}")
            page_header, body = rows[0], rows[1:]
            if header is None:
                header = page_header
                csv.writer(out, lineterminator="\n").writerow(header)
                if "RECORD_COUNT" in header and body:
                    record_count = int(body[0][header.index("RECORD_COUNT")])
            elif page_header != header:
                raise FetchError(f"Nomis header changed between pages at offset {offset}")
            csv.writer(out, lineterminator="\n").writerows(body)
            n_rows += len(body)
            pages += 1
            if len(body) < sf.page_size:
                break
            offset += sf.page_size
            sleep(0.2)
    if record_count is not None and n_rows != record_count:
        raise FetchError(f"{sf.name}: got {n_rows} rows but Nomis RECORD_COUNT={record_count}")
    if sf.expected_rows is not None and n_rows != sf.expected_rows:
        raise FetchError(f"{sf.name}: got {n_rows} rows, expected {sf.expected_rows}")
    return {"final_url": sf.url, "content_type": "text/csv", "pages": pages, "rows": n_rows}


def _ons_area_codes(session: HttpSession, area_type: str, prefix: str, timeout: float) -> list:
    url = f"{ONS_API}/population-types/UR/area-types/{area_type}/areas?limit=100000"
    data = json.loads(_read_all(_get(session, url, timeout)))
    if data.get("count") != data.get("total_count"):
        raise FetchError(f"area list truncated: {url}")
    return sorted(a["id"] for a in data["items"] if a["id"].startswith(prefix))


def _fetch_ons_batched(session: HttpSession, sf: SourceFile, tmp: Path, timeout: float) -> dict:
    assert sf.area_type and sf.batch_size
    codes = _ons_area_codes(session, sf.area_type, sf.area_prefix, timeout)
    sep = "&" if "?" in sf.url else "?"
    n_obs, blocked_all = 0, []
    # filename="" and mtime=0 keep the gzip header (and so the SHA-256) deterministic.
    with open(tmp, "wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
        for b, i in enumerate(range(0, len(codes), sf.batch_size)):
            batch = codes[i : i + sf.batch_size]
            url = f"{sf.url}{sep}area-type={sf.area_type},{','.join(batch)}"
            raw = _read_all(_get(session, url, timeout))
            data = json.loads(raw)
            if "errors" in data:
                raise FetchError(f"ONS API error for batch {b}: {data['errors']}")
            obs = data.get("observations") or []
            returned = {o["dimensions"][0]["option_id"] for o in obs}
            blocked = [c for c in batch if c not in returned]
            if len(blocked) != data.get("blocked_areas", len(blocked)):
                raise FetchError(f"batch {b}: blocked-area count mismatch")
            if data.get("total_observations", len(obs)) != len(obs):
                raise FetchError(f"batch {b}: observations truncated")
            line = {"batch": b, "requested": batch, "blocked": blocked, "response": data}
            gz.write(json.dumps(line, sort_keys=True).encode() + b"\n")
            n_obs += len(obs)
            blocked_all += blocked
            sleep(0.6)
    if sf.expected_rows is not None and n_obs != sf.expected_rows:
        raise FetchError(f"{sf.name}: got {n_obs} observations, expected {sf.expected_rows}")
    return {
        "final_url": sf.url,
        "content_type": "application/x-ndjson+gzip",
        "areas_requested": len(codes),
        "areas_blocked": blocked_all,
        "rows": n_obs,
    }


FETCHERS = {
    "http": _fetch_http,
    "nomis_paged": _fetch_nomis_paged,
    "ons_api_batched": _fetch_ons_batched,
}


# --------------------------------------------------------------------------------------------
# Reading raw files (downstream stages)
# --------------------------------------------------------------------------------------------


def raw_file(cfg: Config, source_id: str, name: str, verify: bool = True) -> tuple[Path, dict]:
    """Path and manifest entry of a downloaded raw file. Fails if it is missing or was modified."""
    manifest = load_manifest(cfg.resolve(cfg.paths.manifest))
    entry = manifest_entry(manifest, source_id, name)
    path = cfg.resolve(cfg.paths.raw) / source_id / name
    if entry is None or not path.is_file():
        raise FileNotFoundError(
            f"{source_id}/{name} has not been downloaded; run `lsc-pop download -s {source_id}`"
        )
    if verify and _sha256(path) != entry["sha256"]:
        raise RawDataError(f"{path} no longer matches its manifest SHA-256")
    return path, entry


# --------------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------------


def fetch_file(
    cfg: Config,
    source: Source,
    sf: SourceFile,
    manifest: dict[str, Any],
    session: HttpSession | None = None,
    timeout: float = 600,
) -> tuple[str, dict[str, Any]]:
    """Fetch one file if needed. Returns (action, entry); action is 'skipped' or 'downloaded'."""
    dest = cfg.resolve(cfg.paths.raw) / source.id / sf.name
    entry = manifest_entry(manifest, source.id, sf.name)

    if dest.exists():
        if entry is None:
            raise RawDataError(f"{dest} exists but is not in the manifest; refusing to overwrite")
        actual = _sha256(dest)
        if actual != entry["sha256"]:
            raise RawDataError(
                f"{dest} SHA-256 {actual[:12]} != manifest {entry['sha256'][:12]}; raw data was "
                "modified. Delete it deliberately and re-download."
            )
        return "skipped", entry

    session = session or requests.Session()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".part-", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        info = FETCHERS[sf.kind](session, sf, tmp, timeout)
        sha = _sha256(tmp)
        if sf.expected_sha256 and sha != sf.expected_sha256:
            raise RawDataError(
                f"{source.id}/{sf.name}: SHA-256 {sha[:12]} != expected "
                f"{sf.expected_sha256[:12]}; the publisher may have replaced the file"
            )
        if entry is not None and entry["sha256"] != sha:
            raise RawDataError(
                f"{source.id}/{sf.name}: re-downloaded file differs from manifest "
                f"({sha[:12]} != {entry['sha256'][:12]}). The publisher has changed it: review, "
                "then remove the manifest entry deliberately."
            )
        os.replace(tmp, dest)
        dest.chmod(0o444)  # raw data is read-only once landed
    finally:
        tmp.unlink(missing_ok=True)

    new_entry = {
        "source_id": source.id,
        "file": sf.name,
        "kind": sf.kind,
        "path": dest.relative_to(cfg.root).as_posix(),
        "url": sf.url,
        "release_date": source.release_date,
        "edition": source.edition,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sha256": sha,
        "size_bytes": dest.stat().st_size,
        **info,
    }
    record_download(manifest, new_entry)
    return "downloaded", new_entry


def download(
    cfg: Config,
    source_ids: list[str] | None = None,
    session: HttpSession | None = None,
    log: Any = print,
) -> dict[str, Any]:
    """Fetch every enabled source (or the given ids). The manifest is saved after each file."""
    registry = load_sources(cfg)
    manifest_path = cfg.resolve(cfg.paths.manifest)
    manifest = load_manifest(manifest_path)
    selected = [registry.get(i) for i in source_ids] if source_ids else registry.sources
    session = session or requests.Session()
    for source in selected:
        if not source.enabled:
            log(f"  {source.id:<4} disabled - skipped")
            continue
        for sf in source.files:
            log(f"  {source.id:<4} {sf.name:<52} fetching ({sf.kind}) ...")
            action, entry = fetch_file(cfg, source, sf, manifest, session=session)
            if action == "downloaded":
                save_manifest(manifest_path, manifest)
            extra = f" blocked={len(entry['areas_blocked'])}" if "areas_blocked" in entry else ""
            log(f"  {source.id:<4} {sf.name:<52} {action:<10} {entry['size_bytes']:>13,} B{extra}")
    return manifest
