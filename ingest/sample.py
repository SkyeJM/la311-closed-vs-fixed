"""Random-cluster samples through the SODA row API, for field checks, early profiling and fixtures.

Rows are allocated to months in proportion to each month's volume. Within a month, rows in
Socrata row-id order (which follows creation order) are split into equal strata, and one run of
consecutive rows is taken at a random offset inside each stratum. This spreads the sample across
every month without relying on ID patterns: legacy SR numbers have non-uniform trailing digits,
so "ID ends in 37" sampling would be biased there. Ordering by row id alone (the first version)
returned only the first day of each month.
"""

from __future__ import annotations

import json
import math
import random
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from ingest.config import Dataset
from ingest.socrata import SocrataClient

METHOD = "soda_csv_stratified_random_clusters"


def month_windows(year: int, today: date) -> list[tuple[date, date]]:
    """[start, end) for each month of `year` that has begun by `today`."""
    windows = []
    for month in range(1, 13):
        start = date(year, month, 1)
        if start > today:
            break
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        windows.append((start, end))
    return windows


def month_where(start: date, end: date) -> str:
    return (
        f"createddate >= '{start.isoformat()}T00:00:00' "
        f"AND createddate < '{end.isoformat()}T00:00:00'"
    )


def cluster_query(start: date, end: date, offset: int, limit: int) -> dict[str, str]:
    return {
        "$select": ":*, *",
        "$where": month_where(start, end),
        "$order": ":id",
        "$offset": str(offset),
        "$limit": str(limit),
    }


def allocate(month_rows: dict[str, int], n: int) -> dict[str, int]:
    """Sample rows per month, proportional to volume (largest-remainder rounding)."""
    total = sum(month_rows.values())
    target = min(n, total)
    if target == 0:
        return dict.fromkeys(month_rows, 0)
    exact = {m: target * rows / total for m, rows in month_rows.items()}
    counts = {m: math.floor(v) for m, v in exact.items()}
    by_remainder = sorted(exact, key=lambda m: exact[m] - counts[m], reverse=True)
    for m in by_remainder[: target - sum(counts.values())]:
        counts[m] += 1
    return counts


def cluster_offsets(
    month_rows: int, sample_rows: int, cluster_size: int, rng: random.Random
) -> list[tuple[int, int]]:
    """(offset, limit) pairs: one run of consecutive rows at a random offset per equal stratum."""
    if sample_rows <= 0 or month_rows <= 0:
        return []
    if sample_rows >= month_rows:
        return [(0, month_rows)]
    k = math.ceil(sample_rows / cluster_size)
    stratum = month_rows / k
    pairs, remaining = [], sample_rows
    for i in range(k):
        limit = min(cluster_size, remaining)
        low = int(i * stratum)
        high = max(low, int((i + 1) * stratum) - limit)
        pairs.append((rng.randint(low, high), limit))
        remaining -= limit
    return pairs


def system_column_name(name: str) -> str:
    """Socrata system fields such as ":updated_at" become "_socrata_updated_at"."""
    if not name.startswith(":"):
        return name
    return "_socrata_" + re.sub(r"[^0-9a-z_]+", "_", name[1:].lower()).strip("_")


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def csvs_to_parquet(
    csv_paths: list[Path], dest: Path, dataset_id: str, expected_fields: set[str]
) -> dict[str, int]:
    """Combine CSVs named YYYY-MM[_suffix].csv into one all-VARCHAR Parquet file.

    Drops rows repeated across overlapping clusters and fails if the CSV columns don't match the
    pinned fields. Returns row counts per month.
    """
    con = duckdb.connect()
    files = "[" + ", ".join(_sql_str(str(p)) for p in csv_paths) + "]"
    source = f"read_csv({files}, header = true, all_varchar = true, filename = true)"
    columns = [row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()]
    data_columns = {c for c in columns if not c.startswith(":") and c != "filename"}
    if data_columns != expected_fields:
        raise ValueError(
            f"{dataset_id}: CSV columns differ from the pinned schema. "
            f"Unexpected: {sorted(data_columns - expected_fields)}; "
            f"missing: {sorted(expected_fields - data_columns)}"
        )
    select = ", ".join(f'"{c}" AS "{system_column_name(c)}"' for c in columns if c != "filename")
    month = r"regexp_extract(filename, '(\d{4}-\d{2})[^/]*\.csv$', 1)"
    dedupe = (
        'QUALIFY row_number() OVER (PARTITION BY ":id" ORDER BY filename) = 1'
        if ":id" in columns
        else ""
    )
    con.execute(
        f"COPY (SELECT {select}, {_sql_str(dataset_id)} AS _dataset_id, {month} AS _sample_month "
        f"FROM {source} {dedupe}) TO {_sql_str(str(dest))} (FORMAT parquet, COMPRESSION zstd)"
    )
    counts = con.execute(
        f"SELECT _sample_month, count(*) FROM read_parquet({_sql_str(str(dest))}) "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    return dict(counts)


def pull_sample(
    client: SocrataClient,
    dataset: Dataset,
    n: int,
    out_dir: Path,
    live_pin: dict,
    cluster_size: int = 100,
    seed: int = 311,
    today: date | None = None,
    workers: int = 4,
) -> dict:
    """Pull ~n rows in random clusters across the dataset's months; write Parquet + manifest."""
    pulled_at = datetime.now(UTC)
    windows = {
        f"{s:%Y-%m}": (s, e) for s, e in month_windows(dataset.year, today or pulled_at.date())
    }

    def month_count(month: str) -> int:
        start, end = windows[month]
        rows = client.get(
            f"/resource/{dataset.id}.json",
            params={"$select": "count(*) AS n", "$where": month_where(start, end)},
        ).json()
        return int(rows[0]["n"])

    with ThreadPoolExecutor(workers) as pool:
        month_rows = dict(zip(windows, pool.map(month_count, windows), strict=True))
    rng = random.Random(seed)
    jobs = [
        (month, i, offset, limit)
        for month, rows in allocate(month_rows, n).items()
        for i, (offset, limit) in enumerate(
            cluster_offsets(month_rows[month], rows, cluster_size, rng)
        )
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{dataset.id}.parquet"
    with tempfile.TemporaryDirectory() as tmp:

        def fetch(job: tuple[str, int, int, int]) -> Path:
            month, i, offset, limit = job
            start, end = windows[month]
            path = Path(tmp) / f"{month}_{i:04d}.csv"
            path.write_text(client.query_csv(dataset.id, cluster_query(start, end, offset, limit)))
            return path

        with ThreadPoolExecutor(workers) as pool:
            paths = list(pool.map(fetch, jobs))
        expected = {c["field"] for c in live_pin["columns"]}
        rows_by_month = csvs_to_parquet(paths, dest, dataset.id, expected) if paths else {}
    manifest = {
        "dataset_id": dataset.id,
        "name": dataset.name,
        "era": dataset.era,
        "method": METHOD,
        "pulled_at": pulled_at.isoformat(timespec="seconds"),
        "n_requested": n,
        "cluster_size": cluster_size,
        "seed": seed,
        "rows": sum(rows_by_month.values()),
        "rows_by_month": rows_by_month,
        "month_rows_at_pull": month_rows,
        "schema_hash": live_pin["schema_hash"],
        "filter_hash": live_pin["filter_hash"],
        "file": dest.name,
    }
    (out_dir / f"{dataset.id}.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
