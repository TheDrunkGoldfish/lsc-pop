from __future__ import annotations

import hashlib
import json

import pytest
import yaml

from lsc_pop import download as dl
from lsc_pop.config import load_config


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status_code = body, status
        self.headers = {
            "Content-Type": "text/csv",
            "Last-Modified": "Wed, 01 Oct 2026 00:00:00 GMT",
        }
        self.url = "https://example.test/final"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk):
        for i in range(0, len(self.body), 3):  # several chunks
            yield self.body[i : i + 3]


class FakeSession:
    def __init__(self, bodies, status: int = 200):
        # bodies: dict url -> bytes, or a callable url -> bytes | (bytes, status)
        self.bodies, self.status, self.calls = bodies, status, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        out = self.bodies(url) if callable(self.bodies) else self.bodies[url]
        body, status = out if isinstance(out, tuple) else (out, self.status)
        return FakeResponse(body, status)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(dl, "sleep", lambda s: None)


BODY = b"a,b\n1,2\n"


def _registry(project, expected_sha=None, files=None):
    src = {
        "id": "S99",
        "title": "Test source",
        "role": "test",
        "publisher": "Nobody",
        "landing_page": "https://example.test",
        "release_date": "2026-01-01",
        "edition": "v1",
        "reference_date": "2024-06-30",
        "geography": "LSOA 2021",
        "status": "other",
        "files": [{"name": "t.csv", "url": "https://example.test/t.csv"}],
    }
    if files is not None:
        src["files"] = files
    if expected_sha:
        src["files"][0]["expected_sha256"] = expected_sha
    (project / "config" / "sources.yaml").write_text(yaml.safe_dump({"sources": [src]}))
    return load_config(project / "config" / "config.yaml")


def test_real_registry_validates(cfg):
    reg = dl.load_sources(cfg)
    ids = [s.id for s in reg.sources]
    assert len(ids) == len(set(ids))
    assert {"S1", "S2", "S5", "S7", "S8", "S9"} <= set(ids)


def test_download_writes_file_and_manifest(project_copy):
    cfg = _registry(project_copy)
    session = FakeSession({"https://example.test/t.csv": BODY})
    dl.download(cfg, session=session, log=lambda *_: None)
    raw = project_copy / "data" / "raw" / "S99" / "t.csv"
    assert raw.read_bytes() == BODY
    manifest = json.loads((project_copy / "data" / "manifest.json").read_text())
    (entry,) = manifest["files"]
    assert entry["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert entry["size_bytes"] == len(BODY)
    assert entry["path"] == "data/raw/S99/t.csv"
    assert entry["release_date"] == "2026-01-01"
    assert not list(raw.parent.glob(".part-*"))


def test_second_run_skips(project_copy):
    cfg = _registry(project_copy)
    session = FakeSession({"https://example.test/t.csv": BODY})
    dl.download(cfg, session=session, log=lambda *_: None)
    dl.download(cfg, session=session, log=lambda *_: None)
    assert len(session.calls) == 1


def test_modified_raw_file_is_an_error(project_copy):
    cfg = _registry(project_copy)
    session = FakeSession({"https://example.test/t.csv": BODY})
    dl.download(cfg, session=session, log=lambda *_: None)
    raw = project_copy / "data" / "raw" / "S99" / "t.csv"
    assert raw.stat().st_mode & 0o777 == 0o444
    raw.chmod(0o644)
    raw.write_bytes(b"tampered")
    with pytest.raises(dl.RawDataError, match="modified"):
        dl.download(cfg, session=session, log=lambda *_: None)


def test_unmanifested_file_not_overwritten(project_copy):
    cfg = _registry(project_copy)
    raw = project_copy / "data" / "raw" / "S99" / "t.csv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"precious")
    with pytest.raises(dl.RawDataError, match="not in the manifest"):
        dl.download(cfg, session=FakeSession({}), log=lambda *_: None)
    assert raw.read_bytes() == b"precious"


def test_expected_sha_mismatch_rejected(project_copy):
    cfg = _registry(project_copy, expected_sha="0" * 64)
    with pytest.raises(dl.RawDataError, match="expected"):
        dl.download(
            cfg, session=FakeSession({"https://example.test/t.csv": BODY}), log=lambda *_: None
        )
    assert not (project_copy / "data" / "raw" / "S99" / "t.csv").exists()


def test_publisher_change_detected_on_redownload(project_copy):
    cfg = _registry(project_copy)
    dl.download(cfg, session=FakeSession({"https://example.test/t.csv": BODY}), log=lambda *_: None)
    (project_copy / "data" / "raw" / "S99" / "t.csv").unlink()
    with pytest.raises(dl.RawDataError, match="publisher has changed"):
        dl.download(
            cfg, session=FakeSession({"https://example.test/t.csv": b"new"}), log=lambda *_: None
        )


def test_http_error_leaves_no_partial(project_copy):
    cfg = _registry(project_copy)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        dl.download(
            cfg,
            session=FakeSession({"https://example.test/t.csv": BODY}, status=404),
            log=lambda *_: None,
        )
    d = project_copy / "data" / "raw" / "S99"
    assert not d.exists() or not list(d.iterdir())


# --- nomis_paged ---------------------------------------------------------------------------

NOMIS_URL = "https://nomis.test/data.csv?x=1"


def _nomis_pages(total: int, page_size: int, record_count: int | None = None):
    record_count = total if record_count is None else record_count

    def body(url):
        offset = int(url.split("recordoffset=")[1])
        lines = ['"GEOGRAPHY_CODE","OBS_VALUE","RECORD_COUNT"']
        for i in range(offset, min(offset + page_size, total)):
            lines.append(f'"E{i:08d}",{i},{record_count}')
        return ("\n".join(lines) + "\n").encode()

    return body


def _nomis_file(**kw):
    return [{"name": "n.csv", "kind": "nomis_paged", "url": NOMIS_URL, "page_size": 4, **kw}]


def test_nomis_pages_joined_with_single_header(project_copy):
    cfg = _registry(project_copy, files=_nomis_file(expected_rows=10))
    session = FakeSession(_nomis_pages(10, 4))
    dl.download(cfg, session=session, log=lambda *_: None)
    lines = (project_copy / "data/raw/S99/n.csv").read_text().splitlines()
    assert lines[0] == "GEOGRAPHY_CODE,OBS_VALUE,RECORD_COUNT"
    assert len(lines) == 11
    assert [u.split("recordoffset=")[1] for u in session.calls] == ["0", "4", "8"]
    entry = json.loads((project_copy / "data/manifest.json").read_text())["files"][0]
    assert entry["pages"] == 3 and entry["rows"] == 10


def test_nomis_exact_multiple_of_page_size(project_copy):
    cfg = _registry(project_copy, files=_nomis_file())
    session = FakeSession(_nomis_pages(8, 4))
    dl.download(cfg, session=session, log=lambda *_: None)
    assert len((project_copy / "data/raw/S99/n.csv").read_text().splitlines()) == 9


def test_nomis_record_count_mismatch_fails(project_copy):
    cfg = _registry(project_copy, files=_nomis_file())
    with pytest.raises(dl.FetchError, match="RECORD_COUNT"):
        dl.download(cfg, session=FakeSession(_nomis_pages(10, 4, 11)), log=lambda *_: None)
    assert not (project_copy / "data/raw/S99/n.csv").exists()


def test_nomis_expected_rows_mismatch_fails(project_copy):
    cfg = _registry(project_copy, files=_nomis_file(expected_rows=9))
    with pytest.raises(dl.FetchError, match="expected 9"):
        dl.download(cfg, session=FakeSession(_nomis_pages(10, 4)), log=lambda *_: None)


def test_rate_limit_retried(project_copy):
    cfg = _registry(project_copy)
    calls = {"n": 0}

    def body(url):
        calls["n"] += 1
        return (b"", 429) if calls["n"] == 1 else BODY

    dl.download(cfg, session=FakeSession(body), log=lambda *_: None)
    assert calls["n"] == 2


# --- ons_api_batched -----------------------------------------------------------------------

AREAS = ["E06000001", "E06000002", "E06000003", "W06000001", "E06000004"]


def _ons_body(blocked=()):
    def body(url):
        if "/areas?" in url:
            items = [{"id": a, "label": a, "area_type": "ltla"} for a in AREAS]
            return json.dumps({"count": 5, "total_count": 5, "items": items}).encode()
        codes = url.split("area-type=ltla,")[1].split(",")
        obs = [
            {"dimensions": [{"option_id": c}, {"option_id": "1"}], "observation": 7}
            for c in codes
            if c not in blocked
        ]
        n_blocked = sum(c in blocked for c in codes)
        return json.dumps(
            {
                "observations": obs or None,
                "total_observations": len(obs),
                "blocked_areas": n_blocked,
                "areas_returned": len(codes) - n_blocked,
            }
        ).encode()

    return body


def _ons_file(**kw):
    return [
        {
            "name": "o.jsonl.gz",
            "kind": "ons_api_batched",
            "url": "https://api.test/obs?dimensions=a,b",
            "area_type": "ltla",
            "batch_size": 3,
            **kw,
        }
    ]


def test_ons_batches_england_only_and_records_blocked(project_copy):
    import gzip

    cfg = _registry(project_copy, files=_ons_file())
    session = FakeSession(_ons_body(blocked={"E06000003"}))
    dl.download(cfg, session=session, log=lambda *_: None)
    lines = [
        json.loads(x)
        for x in gzip.decompress(
            (project_copy / "data/raw/S99/o.jsonl.gz").read_bytes()
        ).splitlines()
    ]
    assert [ln["requested"] for ln in lines] == [
        ["E06000001", "E06000002", "E06000003"],
        ["E06000004"],
    ]
    assert lines[0]["blocked"] == ["E06000003"]
    entry = json.loads((project_copy / "data/manifest.json").read_text())["files"][0]
    assert entry["areas_requested"] == 4
    assert entry["areas_blocked"] == ["E06000003"]
    assert entry["rows"] == 3


def test_ons_output_is_deterministic(project_copy):
    cfg = _registry(project_copy, files=_ons_file())
    dl.download(cfg, session=FakeSession(_ons_body()), log=lambda *_: None)
    raw = project_copy / "data/raw/S99/o.jsonl.gz"
    first = raw.read_bytes()
    raw.unlink()
    # same content -> same hash, so the re-download is accepted against the manifest
    dl.download(cfg, session=FakeSession(_ons_body()), log=lambda *_: None)
    assert raw.read_bytes() == first


def test_ons_api_error_fails(project_copy):
    cfg = _registry(project_copy, files=_ons_file())

    def body(url):
        if "/areas?" in url:
            return _ons_body()(url)
        return json.dumps({"errors": ["too large"]}).encode()

    with pytest.raises(dl.FetchError, match="too large"):
        dl.download(cfg, session=FakeSession(body), log=lambda *_: None)


def test_verify_only_accepts_placed_files_and_rejects_bad_ones(project_copy):
    cfg = _registry(project_copy)
    dl.download(cfg, session=FakeSession({"https://example.test/t.csv": BODY}), log=lambda *_: None)
    dl.verify(cfg, log=lambda *_: None)  # passes
    raw = project_copy / "data" / "raw" / "S99" / "t.csv"
    raw.chmod(0o644)
    raw.write_bytes(b"different")
    with pytest.raises(dl.RawDataError, match="SHA-256 differs"):
        dl.verify(cfg, log=lambda *_: None)
    raw.unlink()
    with pytest.raises(dl.RawDataError, match="missing"):
        dl.verify(cfg, log=lambda *_: None)


def test_seed_manifest_copies_reference_once(project_copy, tmp_path):
    from lsc_pop.config import with_paths

    cfg = _registry(project_copy)
    ref = project_copy / "data" / "manifest.json"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text('{"schema_version": 1, "files": []}')
    moved = with_paths(cfg, manifest=tmp_path / "vol" / "manifest.json")
    target = dl.seed_manifest(moved, ref)
    assert target.read_text() == ref.read_text()
    target.write_text("changed")
    dl.seed_manifest(moved, ref)
    assert target.read_text() == "changed"  # never overwritten


# --- ODS directory (ods_api_orgs) -------------------------------------------------------------

ODS_SEARCH = "https://ods.test/organisations?PrimaryRoleId=RO197&Status=Active&Limit=1000"


def _ods_body(codes):
    def body(url):
        if url == ODS_SEARCH:
            orgs = [{"OrgId": c, "OrgLink": f"https://ods.test/organisations/{c}"} for c in codes]
            return json.dumps({"Organisations": orgs}).encode()
        code = url.rsplit("/", 1)[1]
        return json.dumps({"Organisation": {"OrgId": {"extension": code}, "Name": code}}).encode()

    return body


def _ods_file(**kw):
    return [{"name": "o.jsonl.gz", "kind": "ods_api_orgs", "url": ODS_SEARCH, **kw}]


def test_ods_orgs_stored_verbatim_sorted_by_code(project_copy):
    import gzip

    cfg = _registry(project_copy, files=_ods_file(expected_rows=3))
    dl.download(cfg, session=FakeSession(_ods_body(["RXN", "R0A", "RXL"])), log=lambda *a: None)
    path = project_copy / "data" / "raw" / "S99" / "o.jsonl.gz"
    with gzip.open(path, "rt") as f:
        lines = [json.loads(x) for x in f]
    assert [x["org_id"] for x in lines] == ["R0A", "RXL", "RXN"]
    assert lines[0]["record"]["Name"] == "R0A"


def test_ods_orgs_output_is_deterministic(project_copy):
    cfg = _registry(project_copy, files=_ods_file())
    dl.download(cfg, session=FakeSession(_ods_body(["RXN", "RXL"])), log=lambda *a: None)
    first = dl.load_manifest(cfg.resolve(cfg.paths.manifest))["files"][0]["sha256"]
    (project_copy / "data" / "raw" / "S99" / "o.jsonl.gz").chmod(0o644)
    (project_copy / "data" / "raw" / "S99" / "o.jsonl.gz").unlink()
    m = dl.load_manifest(cfg.resolve(cfg.paths.manifest))
    m["files"] = []
    dl.save_manifest(cfg.resolve(cfg.paths.manifest), m)
    dl.download(cfg, session=FakeSession(_ods_body(["RXL", "RXN"])), log=lambda *a: None)
    assert dl.load_manifest(cfg.resolve(cfg.paths.manifest))["files"][0]["sha256"] == first


def test_ods_orgs_expected_rows_mismatch_fails(project_copy):
    import pytest

    cfg = _registry(project_copy, files=_ods_file(expected_rows=5))
    with pytest.raises(dl.FetchError, match="expected 5"):
        dl.download(cfg, session=FakeSession(_ods_body(["RXL"])), log=lambda *a: None)
