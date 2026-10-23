import json
from datetime import UTC, datetime

import duckdb
import httpx
import pytest
from tenacity import wait_none

from ingest.config import Dataset
from ingest.pull import (
    export_to_parquet,
    header_mapping,
    pull_full,
    read_watermark,
    refresh_incremental,
)
from ingest.socrata import SocrataClient

PIN = {
    "id": "aaaa-0001",
    "schema_hash": "s",
    "filter_hash": "f",
    "columns": [
        {"field": "casenumber", "type": "text", "display": "CaseNumber"},
        {"field": "systemmodstamp", "type": "calendar_date", "display": "UpdatedDate"},
        {"field": "locator_gis_returned_address", "type": "text", "display": "Address"},
    ],
}
EXPORT_CSV = (
    "CaseNumber,UpdatedDate,Address\n"
    '02352417,01/08/2026 07:50:54 AM,"1335 N NORMANDIE AVE, LOS ANGELES, CA, 90027"\n'
    "00000042,03/04/2026 04:51:35 PM,\n"
)
PULLED_AT = datetime(2026, 10, 23, 22, 0, tzinfo=UTC)
DATASET = Dataset(
    id="aaaa-0001", name="Test cases", era="current", year=2026, refresh="incremental"
)


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(SocrataClient.get.retry, "wait", wait_none())
    monkeypatch.setattr(SocrataClient.download.retry, "wait", wait_none())


def write_full_pull(tmp_path, out):
    out.mkdir(parents=True, exist_ok=True)
    csv = tmp_path / "export.csv"
    csv.write_text(EXPORT_CSV)
    export_to_parquet(csv, out / "full.parquet", PIN["id"], PIN, PULLED_AT)


def test_header_mapping_renames_display_names():
    assert header_mapping(["CaseNumber", "UpdatedDate", "Address"], PIN) == {
        "CaseNumber": "casenumber",
        "UpdatedDate": "systemmodstamp",
        "Address": "locator_gis_returned_address",
    }


def test_header_mapping_fails_on_unknown_or_missing_columns():
    with pytest.raises(ValueError, match=r"Unknown: \['Owner'\]; missing: \['Address'\]"):
        header_mapping(["CaseNumber", "UpdatedDate", "Owner"], PIN)


def test_export_to_parquet_keeps_values_as_delivered(tmp_path):
    write_full_pull(tmp_path, tmp_path)
    rows = duckdb.sql(
        "SELECT casenumber, systemmodstamp, locator_gis_returned_address, _pull_method "
        f"FROM '{tmp_path / 'full.parquet'}' ORDER BY casenumber"
    ).fetchall()
    assert rows[0] == ("00000042", "03/04/2026 04:51:35 PM", None, "bulk_export")
    assert rows[1][2] == "1335 N NORMANDIE AVE, LOS ANGELES, CA, 90027"


def test_export_to_parquet_fails_on_malformed_lines(tmp_path):
    csv = tmp_path / "export.csv"
    csv.write_text(EXPORT_CSV + "00000043,01/01/2026 12:00:00 AM,addr,unexpected extra field\n")
    with pytest.raises(ValueError, match="failed to parse"):
        export_to_parquet(csv, tmp_path / "full.parquet", PIN["id"], PIN, PULLED_AT)
    assert not (tmp_path / "full.parquet").exists()


def test_read_watermark_handles_both_timestamp_formats(tmp_path):
    write_full_pull(tmp_path, tmp_path)
    assert read_watermark(tmp_path) == datetime(2026, 3, 4, 16, 51, 35)
    duckdb.sql(
        "COPY (SELECT '2026-05-01T10:00:00.000' AS systemmodstamp) "
        f"TO '{tmp_path / 'delta_x.parquet'}' (FORMAT parquet)"
    )
    assert read_watermark(tmp_path) == datetime(2026, 5, 1, 10, 0, 0)


def test_pull_full_reconciles_and_replaces_earlier_deltas(tmp_path):
    out = tmp_path / "raw" / DATASET.id
    out.mkdir(parents=True)
    (out / "delta_old.parquet").write_bytes(b"stale")

    def handler(request):
        if request.url.path.endswith("/rows.csv"):
            return httpx.Response(200, content=EXPORT_CSV.encode())
        return httpx.Response(200, json=[{"n": "2"}])

    with SocrataClient("example.org", transport=httpx.MockTransport(handler)) as client:
        manifest = pull_full(client, DATASET, PIN, tmp_path / "raw")

    assert manifest["rows"] == manifest["live_count_after_pull"] == 2
    assert not (out / "export.csv").exists()
    assert not (out / "delta_old.parquet").exists()
    combined = json.loads((tmp_path / "raw" / "manifest.json").read_text())
    assert combined[DATASET.id]["files"] == {"full.parquet": 2}


def test_refresh_pages_from_watermark_minus_overlap(tmp_path):
    out = tmp_path / "raw" / DATASET.id
    write_full_pull(tmp_path, out)
    (out / "manifest.json").write_text(json.dumps({"files": {"full.parquet": 2}, "deltas": []}))
    header = '":id","casenumber","systemmodstamp","locator_gis_returned_address"\n'
    pages = {
        "0": header + '"row-1","00000042","2026-03-05T09:00:00.000","x"\n'
        '"row-2","00000043","2026-03-05T10:00:00.000",""\n',
        "2": header + '"row-3","00000044","2026-03-05T11:00:00.000",""\n',
    }
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, text=pages[request.url.params["$offset"]])

    with SocrataClient("example.org", transport=httpx.MockTransport(handler)) as client:
        manifest = refresh_incremental(
            client, DATASET, PIN, tmp_path / "raw", overlap_days=3, page_size=2
        )

    assert [p["$offset"] for p in seen] == ["0", "2"]
    assert seen[0]["$where"] == "systemmodstamp >= '2026-03-01T16:51:35'"
    delta = manifest["deltas"][-1]
    assert delta["rows"] == 3
    assert manifest["files"][delta["file"]] == 3
    stored = duckdb.sql(f"SELECT DISTINCT _pull_method FROM '{out / delta['file']}'").fetchall()
    assert stored == [("soda_delta",)]
