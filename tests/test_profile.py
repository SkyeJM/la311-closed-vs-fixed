"""Smoke test: the profiler runs end to end on tiny synthetic pulls shaped by the real pins."""

import csv
import json

import duckdb

from ingest.profile import Profiler
from ingest.schema import load_pin

LEGACY = [
    {
        "srnumber": "1-101",
        "createddate": "01/02/2024 08:00:00 AM",
        "closeddate": "01/03/2024 09:00:00 AM",
        "requesttype": "Bulky Items",
        "status": "Closed",
        "requestsource": "Call",
        "owner": "BOS",
        "latitude": "34.05",
        "longitude": "-118.25",
    },
    {
        "srnumber": "1-102",
        "createddate": "01/05/2024 10:00:00 AM",
        "requesttype": "Graffiti Removal",
        "status": "Open",
        "requestsource": "Mobile App",
        "owner": "OCB",
    },
]
LEGACY_2025 = [
    {
        "srnumber": "1-201",
        "createddate": "05/01/2025 09:00:00 AM",
        "closeddate": "05/01/2025 09:00:00 AM",
        "requesttype": "Graffiti Removal",
        "status": "Closed",
        "requestsource": "Driver Self Report",
        "owner": "OCB",
        "latitude": "34.0500",
        "longitude": "-118.2500",
    },
]
CURRENT_2025 = [
    {
        "casenumber": "00000001",
        "createddate": "05/01/2025 02:00:00 PM",
        "closeddate": "05/02/2025 02:00:00 PM",
        "type": "Graffiti Removal",
        "status": "Closed",
        "origin": "Self Service",
        "department_name__c": "OCB",
        "resolution_code__c": "WC-Work Completed",
        "geolocation__latitude__s": "34.0501",
        "geolocation__longitude__s": "-118.2501",
    },
]
CURRENT_2026 = [
    {
        "casenumber": "00000002",
        "createddate": "04/01/2026 10:00:00 AM",
        "closeddate": "04/01/2026 10:00:30 AM",
        "type": "Information-Only",
        "status": "Closed",
        "origin": "Call",
        "department_name__c": "311",
        "resolution_code__c": "C-Closed",
    },
    {
        "casenumber": "00000003",
        "createddate": "04/02/2026 11:00:00 AM",
        "type": "Item Pickups",
        "status": "Workorder Created",
        "origin": "Self Service",
        "department_name__c": "LASAN",
    },
]


def write_raw(raw, dataset_id, rows):
    fields = [c["field"] for c in load_pin(dataset_id)["columns"]]
    out = raw / dataset_id
    out.mkdir(parents=True)
    source = out / "fixture.csv"
    with source.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(fields)
        writer.writerows([[row.get(f, "") for f in fields] for row in rows])
    duckdb.sql(
        f"COPY (SELECT *, '{dataset_id}' AS _dataset_id FROM read_csv('{source}', header = true, "
        f"all_varchar = true)) TO '{out / 'full.parquet'}' (FORMAT parquet)"
    )
    return {
        "rows": len(rows),
        "live_count_after_pull": len(rows),
        "pulled_at": "2026-10-23T22:00:00+00:00",
    }


def test_profiler_writes_every_section(tmp_path):
    raw, docs = tmp_path / "raw", tmp_path / "docs"
    manifest = {
        "b7dx-7gc3": write_raw(raw, "b7dx-7gc3", LEGACY),
        "h73f-gn57": write_raw(raw, "h73f-gn57", LEGACY_2025),
        "73a2-6ar5": write_raw(raw, "73a2-6ar5", CURRENT_2025),
        "2cy6-i7zn": write_raw(raw, "2cy6-i7zn", CURRENT_2026),
    }
    (raw / "manifest.json").write_text(json.dumps(manifest))
    docs.mkdir()

    report = Profiler(raw, docs).run().read_text()

    for section in range(1, 14):
        assert f"## {section}. " in report
    assert "Total: 6 rows across 4 datasets." in report
    assert "Proposed non-service list: Feedback, Information-Only, Program Research." in report
    assert (docs / "profile" / "resolution_codes.csv").exists()
    assert "1335 N NORMANDIE" not in report  # no addresses are ever loaded
