import random
from datetime import date

import duckdb
import pytest

from ingest.sample import (
    allocate,
    cluster_offsets,
    cluster_query,
    csvs_to_parquet,
    month_windows,
    system_column_name,
)

HEADER = '":id",":updated_at","casenumber","zipcode__c"\n'


def test_month_windows_cover_a_past_year():
    windows = month_windows(2024, today=date(2026, 10, 23))
    assert len(windows) == 12
    assert windows[0] == (date(2024, 1, 1), date(2024, 2, 1))
    assert windows[-1] == (date(2024, 12, 1), date(2025, 1, 1))


def test_month_windows_stop_at_the_current_month():
    windows = month_windows(2026, today=date(2026, 10, 23))
    assert windows[-1] == (date(2026, 10, 1), date(2026, 11, 1))
    assert len(windows) == 10


def test_cluster_query_uses_half_open_window_and_stable_order():
    query = cluster_query(date(2026, 3, 1), date(2026, 4, 1), offset=5000, limit=100)
    assert query["$where"] == (
        "createddate >= '2026-03-01T00:00:00' AND createddate < '2026-04-01T00:00:00'"
    )
    assert (query["$order"], query["$offset"], query["$limit"]) == (":id", "5000", "100")


def test_allocate_is_proportional_and_exact():
    counts = allocate({"2025-01": 300, "2025-02": 100, "2025-03": 0}, n=40)
    assert counts == {"2025-01": 30, "2025-02": 10, "2025-03": 0}
    assert sum(allocate({"a": 7, "b": 7, "c": 7}, n=10).values()) == 10


def test_allocate_caps_at_available_rows():
    assert allocate({"2025-11": 1, "2025-12": 0}, n=500) == {"2025-11": 1, "2025-12": 0}


def test_cluster_offsets_stay_in_their_strata():
    pairs = cluster_offsets(
        month_rows=100_000, sample_rows=1_000, cluster_size=100, rng=random.Random(1)
    )
    assert len(pairs) == 10
    assert sum(limit for _, limit in pairs) == 1_000
    for i, (offset, limit) in enumerate(pairs):
        assert i * 10_000 <= offset and offset + limit <= (i + 1) * 10_000


def test_cluster_offsets_take_everything_from_small_months():
    assert cluster_offsets(
        month_rows=13, sample_rows=13, cluster_size=100, rng=random.Random(1)
    ) == [(0, 13)]


def test_system_column_names():
    assert system_column_name(":updated_at") == "_socrata_updated_at"
    assert system_column_name(":@computed_region_x") == "_socrata_computed_region_x"
    assert system_column_name("casenumber") == "casenumber"


def test_csvs_to_parquet_keeps_strings_dedupes_and_counts_months(tmp_path):
    first = tmp_path / "2026-03_0000.csv"
    first.write_text(
        HEADER + '"row-1","2026-03-02T00:00:00Z","02858279","91303"\n'
        '"row-2","2026-03-03T00:00:00Z","00000042",""\n'
    )
    overlap = tmp_path / "2026-03_0001.csv"  # overlapping cluster repeats row-2
    overlap.write_text(HEADER + '"row-2","2026-03-03T00:00:00Z","00000042",""\n')
    empty = tmp_path / "2026-04_0000.csv"
    empty.write_text(HEADER)
    dest = tmp_path / "out.parquet"

    counts = csvs_to_parquet(
        [first, overlap, empty], dest, "aaaa-0001", {"casenumber", "zipcode__c"}
    )

    assert counts == {"2026-03": 2}
    rows = duckdb.sql(
        f"SELECT casenumber, zipcode__c, _socrata_id, _dataset_id FROM '{dest}' ORDER BY casenumber"
    ).fetchall()
    assert rows[0] == ("00000042", None, "row-2", "aaaa-0001")  # zeros kept; empty -> NULL


def test_csvs_to_parquet_rejects_unexpected_columns(tmp_path):
    march = tmp_path / "2026-03_0000.csv"
    march.write_text(HEADER + '"row-1","2026-03-02T00:00:00Z","02858279","91303"\n')
    with pytest.raises(ValueError, match="missing: \\['status'\\]"):
        csvs_to_parquet(
            [march], tmp_path / "out.parquet", "aaaa-0001", {"casenumber", "zipcode__c", "status"}
        )
