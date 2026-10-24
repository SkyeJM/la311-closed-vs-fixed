"""dbt builds green on synthetic fixtures, and the models handle each planted edge case.

Runs the real dbt project against tests/fixtures/synthetic_raw.py output in a temp directory,
never the real data (about 10 s; skip it with `pytest -m "not dbt"`).
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from api import serving
from tests.fixtures.synthetic_raw import build

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.dbt


@pytest.fixture(scope="module")
def dbt_build(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dbt")
    build(tmp / "raw")
    env = os.environ | {
        "LA311_RAW_ROOT": str(tmp / "raw"),
        "LA311_WAREHOUSE": str(tmp / "warehouse.duckdb"),
    }
    dbt = str(Path(sys.executable).parent / "dbt")
    paths = ["--target-path", str(tmp / "target"), "--log-path", str(tmp / "logs")]
    subprocess.run([dbt, "deps", "--quiet"], cwd=ROOT / "dbt", env=env, check=True)
    run = subprocess.run(
        [dbt, "build", *paths], cwd=ROOT / "dbt", env=env, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stdout[-4000:]
    con = duckdb.connect(str(tmp / "warehouse.duckdb"), read_only=True)
    yield con, run.stdout, tmp
    con.close()


@pytest.fixture(scope="module")
def con(dbt_build):
    return dbt_build[0]


def fact(con, request_id: str) -> dict:
    cursor = con.execute(
        "SELECT * FROM marts.fct_service_requests WHERE request_id = ?", [request_id]
    )
    names = [d[0] for d in cursor.description]
    return dict(zip(names, cursor.fetchone(), strict=True))


def test_build_is_green_with_only_the_expected_warnings(dbt_build):
    log = dbt_build[1]
    assert "ERROR=0" in log
    assert "WARN=3" in log  # one unmapped code, one date-only close, map rows unused by fixtures
    for test in [
        "assert_all_resolution_codes_mapped",
        "assert_closed_after_created",
        "assert_code_map_rows_are_used",
    ]:
        assert f"WARN 1 {test}" in log or f"WARN 43 {test}" in log


def test_staging_reconciles_and_keeps_the_latest_version(con):
    assert con.execute(
        "SELECT count(*) FROM staging.stg_current__cases WHERE source_dataset_id = '73a2-6ar5'"
    ).fetchone() == (9,)
    case = fact(con, "current:00000107")  # updated by the delta
    assert (case["status"], case["resolution_code"]) == ("Closed", "AR-Request Completed")


def test_outcomes_come_from_the_code_then_the_status(con):
    assert fact(con, "current:00000102")["closure_outcome"] == "not_found"  # QC-Item Not Out
    unmapped = fact(con, "current:00000105")
    assert (unmapped["closure_outcome"], unmapped["outcome_basis"]) == (None, "unmapped_code")
    no_code = fact(con, "current:00000106")
    assert (no_code["closure_outcome"], no_code["outcome_basis"]) == ("cancelled", "status")
    assert fact(con, "legacy:1-2024109")["closure_outcome"] == "referred_out_of_scope"
    still_open = fact(con, "legacy:1-2024105")  # Open, though it carries a closed date
    assert (still_open["closure_outcome"], still_open["hours_to_close"]) == (None, None)
    assert still_open["is_instant_close"] is None


def test_contacts_are_not_service_requests(con):
    contacts = dict(
        con.execute(
            "SELECT request_type, sum(n_contacts) FROM marts.mart_contacts_info_only GROUP BY 1"
        ).fetchall()
    )
    assert contacts == {"Information-Only": 1, "Program Research": 1, "Other": 1, "Feedback": 1}
    assert con.execute(
        "SELECT count(*) FROM marts.fct_service_requests "
        "WHERE request_type IN ('Information-Only', 'Program Research', 'Feedback')"
    ).fetchone() == (0,)


def test_rereports(con):
    assert fact(con, "legacy:1-2024101")["n_rereports_30d"] == 1  # 17 m away, 15 days later
    assert fact(con, "legacy:1-2025101")["n_rereports_30d"] == 1  # re-reported after the cutover
    streetlight = fact(con, "current:00000203")
    assert streetlight["n_rereports_30d"] == 1  # the duplicate filed in between doesn't count
    assert streetlight["first_rereport_at"].isoformat() == "2026-02-20T10:00:00"
    no_coordinates = fact(con, "legacy:1-2024104")
    assert (no_coordinates["is_rereport_eligible"], no_coordinates["is_rereported_30d"]) == (
        False,
        None,
    )


def test_crew_self_reports_and_instant_closes(con):
    crew = fact(con, "legacy:1-2024103")
    assert (crew["is_crew_self_report"], crew["is_instant_close"]) == (True, True)
    assert fact(con, "current:00000202")["is_crew_self_report"] is True  # "Driver Self Reported"
    date_only = fact(con, "legacy:1-2024104")
    assert date_only["hours_to_close"] == -14.5
    assert date_only["is_closed_at_midnight"] and not date_only["is_instant_close"]


def test_cutover_overlap_flags_the_same_day_match(con):
    rows = con.execute(
        "SELECT request_id, has_same_day_match, has_placebo_match "
        "FROM intermediate.int_cutover_overlap"
    ).fetchall()
    assert rows == [("legacy:1-2025102", True, False)]


def test_geography_cleanup(con):
    assert fact(con, "current:00000108")["cd"] is None  # CD 0
    junk = fact(con, "legacy:1-2024108")
    assert (junk["zip"], junk["cd"], junk["nc_code"]) == (None, None, None)
    abroad = fact(con, "current:00000107")
    assert abroad["lat"] is None and abroad["has_out_of_area_coordinates"]


def test_no_address_or_crew_fields_past_staging(con):
    address_fields = {
        "address",
        "locator_gis_returned_address",
        "housenumber",
        "streetname",
        "locator_sr_house_number_",
        "locator_sr_street_name__c",
    }
    columns = con.execute(
        "SELECT table_schema, table_name, column_name FROM information_schema.columns"
    ).fetchall()
    assert not [c for c in columns if c[2] in address_fields]
    assert not [c for c in columns if c[2] == "assigned_to" and c[0] != "staging"]


def test_serving_holds_only_allowlisted_tables_without_locating_fields(dbt_build, tmp_path):
    dest = tmp_path / "serving.duckdb"
    counts = serving.build(dbt_build[2] / "warehouse.duckdb", dest)
    assert set(counts) == {t.name for t in serving.TABLES}
    assert counts["fct_current_requests"] == 13  # 16 current-era cases minus 3 contacts
    con = duckdb.connect(str(dest), read_only=True)
    columns = {row[0] for row in con.execute("SELECT column_name FROM duckdb_columns()").fetchall()}
    assert not columns & serving.FORBIDDEN_COLUMNS
    assert (
        con.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = 'mart_cutover_comparison'"
        )
        .fetchone()[0]
        .startswith("The cutover and the long run")
    )
