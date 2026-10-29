"""Synthetic raw pulls for CI: every dataset in sources.yml, shaped by its pinned schema.

Rows are invented (no real requests, no addresses) and written through the real ingest code:
bulk-export CSVs with display-name headers go through `export_to_parquet`, refresh pages through
`soda_csvs_to_parquet`, and each dataset gets a manifest like `make ingest` writes. Each row is
placed to exercise one dbt edge case; tests/test_dbt_fixtures.py checks the results.

    uv run python -m tests.fixtures.synthetic_raw OUT_DIR
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ingest.config import UNIFIED_FIELDS_FILE, load_registry
from ingest.duck import soda_csvs_to_parquet
from ingest.pull import DELTA, export_to_parquet
from ingest.schema import load_pin

PULLED_AT = datetime(2026, 10, 23, 22, 0, tzinfo=UTC)
REFRESHED_AT = datetime(2026, 10, 23, 23, 0, tzinfo=UTC)
HERE = (34.0500, -118.2500)  # an arbitrary downtown point; nothing here is a real address


def legacy(
    sr, created, type_, status="Closed", closed=None, channel="Call", lat=None, lon=None, **extra
):
    row = {
        "request_id": sr,
        "created_at": created,
        "closed_at": closed,
        "updated_at": closed or created,
        "request_type": type_,
        "status": status,
        "channel": channel,
        "department": "LASAN",
        "lat": lat,
        "lon": lon,
        "cd": "1",
        "nc_code": "52",
        "nc_name": "Downtown Los Angeles",
        "zip": "90012",
        "is_anonymous": "N",
    }
    return row | extra


def current(
    case, created, type_, status="Closed", closed=None, code=None, channel="Self Service", **extra
):
    row = {
        "request_id": case,
        "created_at": created,
        "closed_at": closed,
        "updated_at": closed or created,
        "request_type": type_,
        "status": status,
        "channel": channel,
        "department": "LASAN",
        "resolution_code": code,
        "lat": None,
        "lon": None,
        "cd": "14",
        "nc_code": "52",
        "nc_name": "DOWNTOWN LOS ANGELES NC",
        "zip": "90012",
        "is_anonymous": "false",
    }
    return row | extra


def generic_legacy_year(year: int) -> list[dict]:
    return [
        legacy(
            f"1-{year}001",
            f"{year}-06-01 09:00:00",
            "Bulky Items",
            closed=f"{year}-06-02 10:00:00",
            lat=34.10 + (year - 2015) / 100,
            lon=-118.40,
        )
    ]


# Full pulls, by dataset id. Timestamps are written here as ISO and rendered per format below.
FULL = {
    **{
        dataset_id: generic_legacy_year(year)
        for dataset_id, year in [
            ("ms7h-a45h", 2015),
            ("ndkd-k878", 2016),
            ("eq98-9f8w", 2017),
            ("h65r-yf5i", 2018),
            ("pvft-t768", 2019),
            ("rq3b-xjk8", 2020),
            ("97z7-y5bt", 2021),
            ("i5ke-k6by", 2022),
            ("4a4x-mna2", 2023),
        ]
    },
    "b7dx-7gc3": [
        # A pickup, and a second one 17 m away 15 days after it closed: a re-report.
        legacy(
            "1-2024101",
            "2024-06-03 08:00:00",
            "Bulky Items",
            closed="2024-06-05 10:00:00",
            lat=HERE[0],
            lon=HERE[1],
        ),
        legacy(
            "1-2024102",
            "2024-06-20 09:00:00",
            "Bulky Items",
            closed="2024-06-21 09:00:00",
            lat=HERE[0] + 0.00015,
            lon=HERE[1],
        ),
        # A crew self-report, closed the minute it was logged.
        legacy(
            "1-2024103",
            "2024-07-01 10:00:00",
            "Graffiti Removal",
            closed="2024-07-01 10:00:00",
            channel="Driver Self Report",
            lat=34.06,
            lon=-118.26,
            department="OCB",
        ),
        # A date-only streetlight close: stamped midnight, so it lands before creation.
        legacy(
            "1-2024104",
            "2024-08-01 14:30:00",
            "Single Streetlight Issue",
            closed="2024-08-01 00:00:00",
            department="BSL",
        ),
        # Still open, but carrying a closed date (about 1% of legacy Open rows do).
        legacy(
            "1-2024105",
            "2024-09-01 08:00:00",
            "Graffiti Removal",
            status="Open",
            closed="2024-09-01 08:03:00",
        ),
        legacy(
            "1-2024106",
            "2024-10-01 08:00:00",
            "Dead Animal Removal",
            status="Cancelled",
            closed="2024-10-01 09:00:00",
        ),
        legacy("1-2024107", "2024-10-02 08:00:00", "Feedback", closed="2024-10-02 08:30:00"),
        # Junk ZIP, no council district, NC code 0.
        legacy(
            "1-2024108",
            "2024-10-03 08:00:00",
            "Other",
            closed="2024-10-04 08:00:00",
            zip="JR BLVD, 90011",
            cd="",
            nc_code="0",
            nc_name="NOWHERE NC",
        ),
        legacy(
            "1-2024109",
            "2024-10-04 08:00:00",
            "Report Water Waste",
            status="Referred Out",
            closed="2024-10-05 08:00:00",
            department="LADWP",
        ),
    ],
    "h73f-gn57": [
        # Closed just before the cutover, re-reported in the new system (crosswalked category).
        legacy(
            "1-2025101",
            "2025-03-10 08:00:00",
            "Bulky Items",
            closed="2025-03-12 08:00:00",
            lat=34.07,
            lon=-118.30,
        ),
        # The overlap: a crew self-report after the cutover, 14 m and 5 hours from a resident's
        # graffiti case in the new system.
        legacy(
            "1-2025102",
            "2025-05-01 09:00:00",
            "Graffiti Removal",
            closed="2025-05-01 09:00:00",
            channel="Driver Self Report",
            lat=HERE[0],
            lon=HERE[1],
            department="OCB",
        ),
    ],
    "73a2-6ar5": [
        current(
            "00000101",
            "2025-05-01 14:00:00",
            "Graffiti Removal",
            closed="2025-05-02 14:00:00",
            code="WC-Work Completed",
            department="OCB - Normal Cases",
            lat=HERE[0] + 0.0001,
            lon=HERE[1] + 0.0001,
        ),
        current(
            "00000102",
            "2025-04-01 07:00:00",
            "Item Pickups",
            closed="2025-04-03 12:00:00",
            code="QC-Item Not Out",
            lat=34.07001,
            lon=-118.30001,
        ),
        current(
            "00000103",
            "2025-04-02 10:00:00",
            "Information-Only",
            closed="2025-04-02 10:00:30",
            code="C-Closed",
            channel="Call",
            department="ITA",
        ),
        current(
            "00000104",
            "2025-04-03 10:00:00",
            "Homeless Encampment",
            status="Reported",
            closed="2025-04-03 10:00:20",
            code="C-Report has been received",
            department="LSD",
        ),
        current(
            "00000105",
            "2025-04-04 10:00:00",
            "Street Pavement Issues",
            closed="2025-04-09 10:00:00",
            code="SYN-Synthetic code not in the map",
            department="BSS - SMD",
        ),
        current(
            "00000106",
            "2025-04-05 10:00:00",
            "Dead Animal Removal",
            status="Cancelled",
            closed="2025-04-05 11:00:00",
        ),
        # Geocoded to another continent: kept, but out of spatial joins. Updated by the delta.
        current(
            "00000107",
            "2025-04-06 10:00:00",
            "Item Pickups",
            status="Workorder Created",
            lat=-43.5,
            lon=172.6,
        ),
        current(
            "00000108",
            "2025-04-07 10:00:00",
            "Graffiti Removal",
            closed="2025-04-08 10:00:00",
            code="AR-Request Completed",
            cd="0",
            department="OCB - Normal Cases",
        ),
        # A type only the new system has, filed 13 days after the cutover: its 30-day placebo
        # window would start before the system existed, so it isn't re-report eligible.
        current(
            "00000110",
            "2025-04-10 10:00:00",
            "Street Pavement Issues",
            closed="2025-04-11 10:00:00",
            code="R-Repaired",
            department="BSS - SMD",
            lat=34.15,
            lon=-118.45,
        ),
        # Cancelled 3 minutes after it was filed: past the 1-minute instant-close line.
        current(
            "00000111",
            "2025-05-10 10:00:00",
            "Dead Animal Removal",
            status="Cancelled",
            closed="2025-05-10 10:03:00",
            code="CCAN-Cancelled by Customer",
        ),
    ],
    "2cy6-i7zn": [
        current(
            "00000201",
            "2026-01-05 10:00:00",
            "Program Research",
            closed="2026-01-05 10:00:40",
            code="1004-Closed",
        ),
        current(
            "00000202",
            "2026-04-01 10:00:00",
            "Graffiti Removal",
            closed="2026-04-01 10:00:00",
            code="AR-Request Completed",
            channel="Driver Self Reported",
            department="OCB - Normal Cases",
        ),
        # A streetlight closed Feb 10, re-reported 30 m away on Feb 20. A duplicate 10 m away on
        # Feb 15 doesn't count: its outcome lives on another case.
        current(
            "00000203",
            "2026-02-01 10:00:00",
            "Streetlight Repair Services",
            closed="2026-02-10 10:00:00",
            code="R-Repaired",
            department="BSL",
            lat=34.10,
            lon=-118.33,
        ),
        current(
            "00000204",
            "2026-02-20 10:00:00",
            "Streetlight Repair Services",
            status="New",
            department="BSL",
            lat=34.10027,
            lon=-118.33,
        ),
        current(
            "00000206",
            "2026-02-15 10:00:00",
            "Streetlight Repair Services",
            closed="2026-02-15 12:00:00",
            code="DUP-Duplicate",
            department="BSL",
            lat=34.10009,
            lon=-118.33,
        ),
        current(
            "00000205",
            "2026-03-01 10:00:00",
            "Other",
            closed="2026-03-02 10:00:00",
            code="GI-General Information",
            department="ITA",
        ),
        # The latest case: the data's end, so earlier re-report windows are complete.
        current(
            "00000207",
            "2026-06-01 10:00:00",
            "Dead Animal Removal",
            closed="2026-06-01 15:00:00",
            code="GOA-Animal gone on arrival",
        ),
    ],
}

# Incremental refreshes (row API): a newer version of a case, and a case created since the pull.
DELTAS = {
    "73a2-6ar5": [
        current(
            "00000107",
            "2025-04-06 10:00:00",
            "Item Pickups",
            closed="2025-04-09 10:00:00",
            code="AR-Request Completed",
            lat=-43.5,
            lon=172.6,
        )
        | {"updated_at": "2025-04-09 10:00:00"},
        current("00000109", "2025-12-30 10:00:00", "Item Pickups", status="New"),
    ],
}


def field_names(era: str) -> dict[str, str]:
    """Unified column -> this era's Socrata field name (ingest/unified_fields.yml)."""
    fields = yaml.safe_load(UNIFIED_FIELDS_FILE.read_text())["fields"]
    return {unified: names[era] for unified, names in fields.items() if names[era]}


def export_timestamp(value: str | None) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value).strftime("%m/%d/%Y %I:%M:%S %p")


def api_timestamp(value: str | None) -> str:
    return datetime.fromisoformat(value).strftime("%Y-%m-%dT%H:%M:%S.000") if value else ""


def render(row: dict, era: str, timestamp) -> dict[str, str]:
    names = field_names(era)
    out = {}
    for unified, value in row.items():
        if unified in ("created_at", "closed_at", "updated_at"):
            value = timestamp(value)
        out[names[unified]] = "" if value is None else str(value)
    return out


def write_full(raw_root: Path, dataset_id: str, era: str, rows: list[dict]) -> int:
    pin = load_pin(dataset_id)
    out = raw_root / dataset_id
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "export.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([c["display"] for c in pin["columns"]])
        for row in rows:
            values = render(row, era, export_timestamp)
            writer.writerow([values.get(c["field"], "") for c in pin["columns"]])
    count = export_to_parquet(csv_path, out / "full.parquet", dataset_id, pin, PULLED_AT)
    csv_path.unlink()
    return count


def write_delta(raw_root: Path, dataset_id: str, era: str, rows: list[dict]) -> tuple[str, int]:
    pin = load_pin(dataset_id)
    fields = [c["field"] for c in pin["columns"]]
    name = f"delta_{REFRESHED_AT:%Y%m%dT%H%M%SZ}.parquet"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page_00000.csv"
        with page.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([":id", *fields])
            for i, row in enumerate(rows):
                values = render(row, era, api_timestamp)
                writer.writerow([f"row-{i}", *[values.get(f, "") for f in fields]])
        count = soda_csvs_to_parquet(
            [page],
            raw_root / dataset_id / name,
            dataset_id,
            set(fields),
            {
                "_pull_method": f"'{DELTA}'",
                "_pulled_at": f"TIMESTAMPTZ '{REFRESHED_AT.isoformat()}'",
            },
        )
    return name, count


def build(raw_root: Path) -> dict:
    """Write every dataset in sources.yml, with manifests, under raw_root."""
    manifests = {}
    for dataset in load_registry().datasets:
        rows = FULL[dataset.id]
        full_rows = write_full(raw_root, dataset.id, dataset.era, rows)
        manifest = {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "era": dataset.era,
            "pulled_at": PULLED_AT.isoformat(timespec="seconds"),
            "method": "bulk_export",
            "rows": full_rows,
            "live_count_after_pull": full_rows,
            "files": {"full.parquet": full_rows},
            "deltas": [],
        }
        if dataset.id in DELTAS:
            name, delta_rows = write_delta(raw_root, dataset.id, dataset.era, DELTAS[dataset.id])
            ids = {r["request_id"] for r in rows} | {r["request_id"] for r in DELTAS[dataset.id]}
            manifest["files"][name] = delta_rows
            manifest["deltas"].append(
                {
                    "file": name,
                    "pulled_at": REFRESHED_AT.isoformat(timespec="seconds"),
                    "rows": delta_rows,
                    "live_count_after_refresh": len(ids),
                }
            )
        (raw_root / dataset.id / "manifest.json").write_text(json.dumps(manifest, indent=2))
        manifests[dataset.id] = manifest
    (raw_root / "manifest.json").write_text(json.dumps(manifests, indent=2))
    return manifests


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.fixtures.synthetic_raw OUT_DIR")
    out_dir = Path(sys.argv[1])
    build(out_dir)
    print(f"Synthetic raw pulls written to {out_dir}")
