"""Full pulls (bulk CSV export) and incremental refreshes (SODA row API) into data/raw/.

Per dataset, everything is Parquet with values kept exactly as delivered (strings):

    data/raw/{id}/full.parquet          the latest full pull, from the bulk export
    data/raw/{id}/delta_<UTC>.parquet   incremental refreshes since then, from the row API
    data/raw/{id}/manifest.json         what's on disk now (history.jsonl keeps every run)
    data/raw/manifest.json              all datasets, for dbt's row-count reconciliation

The export uses display names as headers and renders timestamps as "MM/DD/YYYY hh:mm:ss AM";
the row API uses field names and ISO timestamps. Columns are renamed to API field names here,
values are not reformatted, and `_pull_method` tells staging which timestamp format a row has.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from ingest.config import RAW_DIR, Dataset
from ingest.duck import soda_csvs_to_parquet, sql_list, sql_str
from ingest.socrata import SocrataClient

EXPORT = "bulk_export"
DELTA = "soda_delta"
EXPORT_TIMESTAMP_FORMAT = "%m/%d/%Y %I:%M:%S %p"

_manifest_lock = threading.Lock()


def header_mapping(header: list[str], pin: dict) -> dict[str, str]:
    """Export header (display names) -> API field names via the pin; fails on any mismatch."""
    by_display = {c["display"]: c["field"] for c in pin["columns"]}
    if len(by_display) != len(pin["columns"]):
        raise ValueError(f"{pin['id']}: display names in the pin are not unique")
    unknown = sorted(set(header) - by_display.keys())
    missing = sorted(by_display.keys() - set(header))
    if unknown or missing:
        raise ValueError(
            f"{pin['id']}: export header differs from the pin. Unknown: {unknown}; "
            f"missing: {missing}"
        )
    return {display: by_display[display] for display in header}


def export_to_parquet(
    csv_path: Path, dest: Path, dataset_id: str, pin: dict, pulled_at: datetime
) -> int:
    """Convert a bulk-export CSV to Parquet with API field names; fails on any unparseable line."""
    con = duckdb.connect()
    source = (
        f"read_csv({sql_str(str(csv_path))}, header = true, all_varchar = true, delim = ',', "
        "quote = '\"', escape = '\"', store_rejects = true)"
    )
    header = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    select = ", ".join(f'"{d}" AS "{f}"' for d, f in header_mapping(header, pin).items())
    partial = dest.with_name(dest.name + ".tmp")
    con.execute(
        f"COPY (SELECT {select}, {sql_str(dataset_id)} AS _dataset_id, "
        f"'{EXPORT}' AS _pull_method, TIMESTAMPTZ {sql_str(pulled_at.isoformat())} AS _pulled_at "
        f"FROM {source}) TO {sql_str(str(partial))} (FORMAT parquet, COMPRESSION zstd)"
    )
    rejected = con.execute("SELECT count(*) FROM reject_errors").fetchone()[0]
    if rejected:
        sample = con.execute("SELECT line, error_message FROM reject_errors LIMIT 3").fetchall()
        partial.unlink()
        raise ValueError(f"{dataset_id}: {rejected} export lines failed to parse, e.g. {sample}")
    partial.replace(dest)
    return con.execute(f"SELECT count(*) FROM read_parquet({sql_str(str(dest))})").fetchone()[0]


def live_row_count(client: SocrataClient, dataset_id: str) -> int:
    rows = client.get(f"/resource/{dataset_id}.json", params={"$select": "count(*) AS n"}).json()
    return int(rows[0]["n"])


def combine_manifests(raw_root: Path) -> dict:
    combined = {
        path.parent.name: json.loads(path.read_text())
        for path in sorted(raw_root.glob("*/manifest.json"))
    }
    (raw_root / "manifest.json").write_text(json.dumps(combined, indent=2) + "\n")
    return combined


def write_manifest(dataset_dir: Path, manifest: dict) -> None:
    with _manifest_lock:
        (dataset_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        with (dataset_dir / "history.jsonl").open("a") as fh:
            fh.write(json.dumps(manifest) + "\n")
        combine_manifests(dataset_dir.parent)


def pull_full(
    client: SocrataClient,
    dataset: Dataset,
    live_pin: dict,
    raw_root: Path = RAW_DIR,
    keep_csv: bool = False,
) -> dict:
    """Download the bulk export, convert it to Parquet, and reconcile against a live count."""
    out = raw_root / dataset.id
    out.mkdir(parents=True, exist_ok=True)
    pulled_at = datetime.now(UTC)
    started = time.perf_counter()
    csv_path = out / "export.csv"
    download = client.download(
        f"/api/views/{dataset.id}/rows.csv", csv_path, params={"accessType": "DOWNLOAD"}
    )
    rows = export_to_parquet(csv_path, out / "full.parquet", dataset.id, live_pin, pulled_at)
    live_count = live_row_count(client, dataset.id)
    for stale in out.glob("delta_*.parquet"):  # a full pull supersedes earlier refreshes
        stale.unlink()
    if not keep_csv:
        csv_path.unlink()
    manifest = {
        "dataset_id": dataset.id,
        "name": dataset.name,
        "era": dataset.era,
        "pulled_at": pulled_at.isoformat(timespec="seconds"),
        "method": EXPORT,
        "source_url": f"https://{client.domain}/api/views/{dataset.id}/rows.csv?accessType=DOWNLOAD",
        "source_last_modified": download["last_modified"],
        "rows": rows,
        "live_count_after_pull": live_count,
        "schema_hash": live_pin["schema_hash"],
        "filter_hash": live_pin["filter_hash"],
        "csv_bytes": download["bytes"],
        "seconds": round(time.perf_counter() - started, 1),
        "files": {"full.parquet": rows},
        "deltas": [],
    }
    write_manifest(out, manifest)
    return manifest


def read_watermark(dataset_dir: Path) -> datetime:
    """Latest `systemmodstamp` across the full pull and any deltas (either timestamp format)."""
    files = sorted(dataset_dir.glob("*.parquet"))
    return duckdb.sql(
        f"SELECT max(coalesce(try_strptime(systemmodstamp, '{EXPORT_TIMESTAMP_FORMAT}'), "
        f"try_cast(systemmodstamp AS TIMESTAMP))) "
        f"FROM read_parquet({sql_list(files)}, union_by_name = true)"
    ).fetchall()[0][0]


def refresh_incremental(
    client: SocrataClient,
    dataset: Dataset,
    live_pin: dict,
    raw_root: Path = RAW_DIR,
    overlap_days: int = 3,
    page_size: int = 50_000,
) -> dict:
    """Pull rows modified since the watermark (minus an overlap) into a new delta file.

    The overlap re-reads recent days because modifications can reach the portal out of order;
    staging keeps the latest version of each case. Deleted or re-filtered cases are invisible to
    deltas, so a periodic full pull is still needed.
    """
    if dataset.refresh != "incremental":
        raise ValueError(f"{dataset.id} is not marked `refresh: incremental` in sources.yml")
    out = raw_root / dataset.id
    if not (out / "full.parquet").exists():
        raise FileNotFoundError(f"{dataset.id}: run a full pull before refreshing")
    watermark = read_watermark(out)
    since = watermark - timedelta(days=overlap_days)
    pulled_at = datetime.now(UTC)
    where = f"systemmodstamp >= '{since:%Y-%m-%dT%H:%M:%S}'"
    dest = out / f"delta_{pulled_at:%Y%m%dT%H%M%SZ}.parquet"
    with tempfile.TemporaryDirectory() as tmp:
        paths: list[Path] = []
        while True:
            soql = {
                "$select": ":*, *",
                "$where": where,
                "$order": ":id",
                "$limit": str(page_size),
                "$offset": str(len(paths) * page_size),
            }
            path = Path(tmp) / f"page_{len(paths):05d}.csv"
            path.write_text(client.query_csv(dataset.id, soql))
            paths.append(path)
            page_rows = duckdb.sql(
                f"SELECT count(*) FROM read_csv({sql_str(str(path))}, header = true, "
                "all_varchar = true)"
            ).fetchall()[0][0]
            if page_rows < page_size:
                break
        rows = soda_csvs_to_parquet(
            paths,
            dest,
            dataset.id,
            {c["field"] for c in live_pin["columns"]},
            {
                "_pull_method": f"'{DELTA}'",
                "_pulled_at": f"TIMESTAMPTZ {sql_str(pulled_at.isoformat())}",
            },
        )
    manifest = json.loads((out / "manifest.json").read_text())
    manifest["files"][dest.name] = rows
    manifest["deltas"].append(
        {
            "file": dest.name,
            "pulled_at": pulled_at.isoformat(timespec="seconds"),
            "watermark": watermark.isoformat(),
            "since": since.isoformat(),
            "rows": rows,
        }
    )
    write_manifest(out, manifest)
    return manifest
