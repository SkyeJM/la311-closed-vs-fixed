"""dbt builds green on synthetic fixtures, and the models handle each planted edge case.

Runs the real dbt project against tests/fixtures/synthetic_raw.py output in a temp directory,
never the real data (about 10 s; skip it with `pytest -m "not dbt"`).
"""

import re

import duckdb
import pytest

from api import serving

pytestmark = pytest.mark.dbt  # the dbt_build fixture lives in tests/conftest.py


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
        assert re.search(rf"WARN \d+ {test}", log)


def test_staging_reconciles_and_keeps_the_latest_version(con):
    assert con.execute(
        "SELECT count(*) FROM staging.stg_current__cases WHERE source_dataset_id = '73a2-6ar5'"
    ).fetchone() == (11,)
    case = fact(con, "current:00000107")  # updated by the delta
    assert (case["status"], case["resolution_code"]) == ("Closed", "AR-Request Completed")


def test_outcomes_come_from_the_code_then_the_status(con):
    assert fact(con, "current:00000102")["closure_outcome"] == "not_found"  # QC-Item Not Out
    unmapped = fact(con, "current:00000105")
    assert (unmapped["closure_outcome"], unmapped["outcome_basis"]) == (None, "unmapped_code")
    no_code = fact(con, "current:00000106")
    assert (no_code["closure_outcome"], no_code["outcome_basis"]) == ("cancelled", "status")
    assert fact(con, "legacy:1-2024109")["closure_outcome"] == "referred_out_of_scope"
    # An intake handoff: the status decides, although the case carries an intake code.
    handoff = fact(con, "current:00000104")
    assert (handoff["closure_outcome"], handoff["outcome_basis"]) == ("handed_off", "status")
    assert handoff["outcome_group"] == "handed_off" and handoff["code_label_source"] is None
    still_open = fact(con, "legacy:1-2024105")  # Open, though it carries a closed date
    assert (still_open["closure_outcome"], still_open["hours_to_close"]) == (None, None)
    assert still_open["is_instant_close"] is None


def test_closed_means_the_status_says_closed(con):
    closed = {
        request_id: fact(con, request_id)["is_closed"]
        for request_id in [
            "legacy:1-2024109",  # Referred Out
            "legacy:1-2024106",  # Cancelled
            "current:00000104",  # Reported
            "current:00000106",  # Cancelled
            "current:00000108",  # Closed
            "current:00000107",  # Closed by the delta
        ]
    }
    assert closed == {
        "legacy:1-2024109": True,
        "legacy:1-2024106": False,
        "current:00000104": False,
        "current:00000106": False,
        "current:00000108": True,
        "current:00000107": True,
    }


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


def test_placebo_window_before_filing(con):
    first, second = fact(con, "legacy:1-2024101"), fact(con, "legacy:1-2024102")
    assert (first["has_prior_report_30d"], first["is_rereported_30d"]) == (False, True)
    assert (second["has_prior_report_30d"], second["is_rereported_30d"]) == (True, False)
    assert second["n_prior_reports_30d"] == 1
    # A legacy pickup filed before the cutover is a prior report for a new-system pickup there.
    assert fact(con, "current:00000102")["has_prior_report_30d"] is True
    # A new-system-only type filed in the system's first 30 days has no full placebo window.
    early = fact(con, "current:00000110")
    assert (early["is_rereport_eligible"], early["has_prior_report_30d"]) == (False, None)


def test_crew_self_reports_and_instant_closes(con):
    crew = fact(con, "legacy:1-2024103")
    assert (crew["is_crew_self_report"], crew["is_instant_close"]) == (True, True)
    assert fact(con, "current:00000202")["is_crew_self_report"] is True  # "Driver Self Reported"
    date_only = fact(con, "legacy:1-2024104")
    assert date_only["hours_to_close"] == -14.5
    assert date_only["is_closed_at_midnight"] and not date_only["is_instant_close"]
    # Ended 20 s after filing, but a handoff at intake isn't a close.
    assert fact(con, "current:00000104")["is_instant_close"] is False
    three_minutes = fact(con, "current:00000111")
    assert (three_minutes["hours_to_close"], three_minutes["is_instant_close"]) == (0.05, False)


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
    assert counts["fct_current_requests"] == 15  # 18 current-era cases minus 3 contacts
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
