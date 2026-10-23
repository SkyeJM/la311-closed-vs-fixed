"""Hosting spike: how big is a slim serving DuckDB file at full scale, and how fast is it to query
on a small instance? Uses synthetic data shaped like the planned slim fact table (no real rows).

    uv run python spikes/hosting/bench_duckdb.py [--rows 18000000]

Variant "timestamps" keeps created_at/closed_at; variant "compact" keeps created_date plus
hours_to_close, which is all the metrics need. Each query runs in a fresh read-only process with
1 thread and a 1 GB memory limit, roughly a Vercel Hobby function (2 GB, 1 vCPU).
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
LEGACY_SHARE = 0.78  # legacy is ~78% of rows (~14M of ~18M); refined in Phase 1

COMMON = """
    request_key,
    CASE WHEN request_key < {n_legacy} THEN 'legacy' ELSE 'current' END AS era,
    least(63, floor(-ln((h1 % 1000000 + 1) / 1000001.0) * 6))::SMALLINT AS category_id,
    (h1 % 15)::UTINYINT AS department_id,
    CASE WHEN h2 % 100 < 50 THEN 0 WHEN h2 % 100 < 80 THEN 1 ELSE h2 % 9 END::UTINYINT
        AS channel_id,
    CASE WHEN h3 % 100 < 90 THEN 0 ELSE h3 % 9 END::UTINYINT AS status_id,
    least(10, floor(-ln((h2 % 100000 + 1) / 100001.0) * 2))::UTINYINT AS outcome_id,
    CASE WHEN request_key >= {n_legacy}
         THEN least(120, floor(-ln((h3 % 100000 + 1) / 100001.0) * 12))::USMALLINT END
         AS resolution_code_id,
    (1 + h3 % 15)::UTINYINT AS cd,
    (1 + h1 % 99)::UTINYINT AS nc_code,
    (617700000000000000 + (h2 % 1800))::UBIGINT AS h3_r8,
    (h1 % 100 < 80) AS is_service,
    (h2 % 100 < 12) AS instant_close,
    (h3 % 100 < 7) AS rereport_30d,
    exp(((h2 % 10000) / 10000.0) * 8 - 2)::FLOAT AS hours_to_close
"""

VARIANTS = {
    "timestamps": """
        TIMESTAMP '2015-08-01' + to_seconds((request_key * {span_s} // {n})::BIGINT) AS created_at,
        TIMESTAMP '2015-08-01' + to_seconds((request_key * {span_s} // {n})::BIGINT)
            + to_seconds((exp(((h2 % 10000) / 10000.0) * 8 - 2) * 3600)::BIGINT) AS closed_at,
    """,
    "compact": """
        (DATE '2015-08-01' + (request_key * {span_d} // {n})::INTEGER) AS created_date,
    """,
}

QUERIES = {
    "monthly_outcome_mix": """
        SELECT date_trunc('month', {date_col}) AS m, outcome_id, count(*) FROM fct
        WHERE era = 'current' AND category_id = 3 GROUP BY ALL""",
    "gap_by_district": """
        SELECT cd, category_id, avg((outcome_id IN (1, 2))::INT) AS fixed_share FROM fct
        WHERE era = 'current' AND is_service GROUP BY ALL""",
    "top_codes_2026": """
        SELECT resolution_code_id, count(*) AS n FROM fct WHERE {date_col} >= DATE '2026-01-01'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 20""",
    "yearly_median_full_scan": """
        SELECT year({date_col}) AS y, count(*), median(hours_to_close) FROM fct GROUP BY 1""",
}


def build(path: Path, variant: str, n: int) -> None:
    n_legacy = int(n * LEGACY_SHARE)
    span_s, span_d = 11 * 365 * 86400 + 90 * 86400, 11 * 365 + 90  # 2015-08 .. 2026-10
    select = (VARIANTS[variant] + COMMON).format(
        n=n, n_legacy=n_legacy, span_s=span_s, span_d=span_d
    )
    path.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute(
        f"""CREATE TABLE fct AS SELECT {select} FROM (
            SELECT i AS request_key, hash(i) AS h1, hash(i * 7919 + 13) AS h2,
                   hash(i * 104729 + 7) AS h3 FROM range(0, {n}) t(i))"""
    )
    con.execute("CHECKPOINT")
    con.close()


def run_query(path: str, sql: str) -> dict:
    """Runs in a child process: open read-only, run the query twice, report timings and peak RSS."""
    start = time.perf_counter()
    con = duckdb.connect(path, read_only=True, config={"threads": 1, "memory_limit": "1GB"})
    opened = time.perf_counter()
    con.execute(sql).fetchall()
    first = time.perf_counter()
    con.execute(sql).fetchall()
    second = time.perf_counter()
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024  # bytes on macOS
    return {
        "open_ms": round((opened - start) * 1000, 1),
        "first_ms": round((first - opened) * 1000, 1),
        "warm_ms": round((second - first) * 1000, 1),
        "peak_rss_mb": round(rss_mb, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=18_000_000)
    parser.add_argument("--child", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(run_query(*args.child)))
        return
    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    results = {"rows": args.rows, "duckdb": duckdb.__version__, "variants": {}}
    for variant in VARIANTS:
        path = out_dir / f"serving_synthetic_{variant}.duckdb"
        t0 = time.perf_counter()
        build(path, variant, args.rows)
        entry = {
            "build_s": round(time.perf_counter() - t0, 1),
            "file_mb": round(path.stat().st_size / 1024 / 1024, 1),
            "queries": {},
        }
        date_col = "created_at" if variant == "timestamps" else "created_date"
        for name, sql in QUERIES.items():
            child = subprocess.run(
                [sys.executable, __file__, "--child", str(path), sql.format(date_col=date_col)],
                capture_output=True,
                text=True,
                check=True,
            )
            entry["queries"][name] = json.loads(child.stdout)
        results["variants"][variant] = entry
    print(json.dumps(results, indent=2))
    (out_dir / "bench_results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
