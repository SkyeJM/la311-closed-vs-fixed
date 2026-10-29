"""metrics.yml compiles to SQL that agrees with the fact table, from whichever source answers.

Runs on the serving file built from the synthetic dbt fixtures (tests/conftest.py).
"""

import pytest

from api import metrics

pytestmark = pytest.mark.dbt


def value(serving_db, metric, **request):
    rows = metrics.run(serving_db, metrics.compile_query(metric, **request))
    assert len(rows) == 1, rows
    return rows[0]["value"]


def fact(dbt_build, sql):
    """The same number straight from the warehouse fact table, as an independent check."""
    return dbt_build[0].execute(sql).fetchone()[0]


FIX_BASE = "coalesce(outcome_group, '') not in ('neutral', 'handed_off')"


def test_every_metric_compiles_and_runs(serving_db):
    for name, spec in metrics.catalog().metrics.items():
        request = {"filters": {"era": "current"}} if "percentile" in spec else {}
        rows = metrics.run(serving_db, metrics.compile_query(name, **request))
        assert rows, name


def test_rates_match_the_fact_table(serving_db, dbt_build):
    closure = fact(dbt_build, "select avg(is_closed::int) from marts.fct_service_requests")
    assert value(serving_db, "closure_rate") == pytest.approx(closure)
    fixed = fact(
        dbt_build,
        "select avg(coalesce(outcome_group = 'fixed', false)::int) "
        f"from marts.fct_service_requests where era = 'current' and {FIX_BASE}",
    )
    assert value(serving_db, "verified_fix_rate") == pytest.approx(fixed)
    closed_on_base = fact(
        dbt_build,
        f"select avg(is_closed::int) from marts.fct_service_requests "
        f"where era = 'current' and {FIX_BASE}",
    )
    assert value(serving_db, "closed_fixed_gap_pp") == pytest.approx(
        (closed_on_base - fixed) * 100, abs=1e-3
    )


def test_every_source_gives_the_same_answer(serving_db):
    """The fix rate from the monthly mart, the district mart and the slim fact must agree."""
    answers = {
        round(value(serving_db, "verified_fix_rate", source=source), 12)
        for source in ["outcomes_monthly", "gap_by_district", "current_requests"]
    }
    assert len(answers) == 1


def test_outcome_mix_sums_to_one_per_group(serving_db):
    rows = metrics.run(
        serving_db, metrics.compile_query("outcome_mix", group_by=["unified_category"])
    )
    totals = {}
    for row in rows:
        totals[row["unified_category"]] = totals.get(row["unified_category"], 0) + row["value"]
    assert all(total == pytest.approx(1) for total in totals.values())
    assert any(row["closure_outcome"] == "handed_off" for row in rows)


def test_source_choice_follows_the_dimensions(serving_db):
    by_district = metrics.compile_query("verified_fix_rate", group_by=["cd"])
    assert by_district.source == "gap_by_district"
    by_nc = metrics.compile_query("verified_fix_rate", group_by=["nc_code"])
    assert by_nc.source == "current_requests"
    pickups_by_weekday = metrics.compile_query(
        "rereport_30d_rate",
        group_by=["closed_weekday"],
        filters={"unified_category": "Bulky & dumped item pickups", "era": "current"},
    )
    assert pickups_by_weekday.source == "bulky_items"
    # The weekday is only in the pickups mart, so a request must say it's about new-system pickups.
    with pytest.raises(metrics.MetricError, match="covers only unified_category"):
        metrics.compile_query(
            "rereport_30d_rate", group_by=["closed_weekday"], filters={"era": "current"}
        )


def test_percentiles_come_from_rows_or_from_their_precomputed_grain(serving_db, dbt_build):
    median = fact(
        dbt_build,
        "select quantile_cont(hours_to_close, 0.5) from marts.fct_service_requests "
        "where era = 'current' and is_closed and hours_to_close >= 0 "
        "and not is_crew_self_report",
    )
    assert value(serving_db, "median_hours_to_close", filters={"era": "current"}) == (
        pytest.approx(median)
    )
    by_period = metrics.compile_query(
        "median_hours_to_close", group_by=["unified_category", "era", "period"]
    )
    assert by_period.source == "cutover_periods"
    with pytest.raises(metrics.MetricError, match="precomputed per"):
        metrics.compile_query("median_hours_to_close", group_by=["era"])


def test_requests_that_cant_be_answered_say_why(serving_db):
    with pytest.raises(metrics.MetricError, match="exists only for current"):
        metrics.compile_query("verified_fix_rate", filters={"era": "legacy"})
    with pytest.raises(metrics.MetricError, match="no dimension address"):
        metrics.compile_query("closure_rate", group_by=["address"])
    with pytest.raises(metrics.MetricError, match="unknown metric"):
        metrics.compile_query("fix_rate")


def test_filter_values_are_bound_not_spliced(serving_db):
    hostile = "LASAN' or 1=1 --"
    query = metrics.compile_query("closure_rate", filters={"department": hostile})
    assert hostile not in query.sql and query.params == [hostile]
    assert metrics.run(serving_db, query)[0]["denominator"] is None  # no row matched


def test_catalog_lists_definitions_and_dimensions():
    catalog = {m["name"]: m for m in metrics.describe()}
    assert catalog["verified_fix_rate"]["evidence"] == "E1"
    assert "cd" in catalog["verified_fix_rate"]["dimensions"]
    assert "period" in catalog["median_hours_to_close"]["dimensions"]


def test_every_source_column_exists_in_the_served_table(serving_db):
    """metrics.yml can't drift from the marts: each dimension and measure must resolve."""
    for source in metrics.catalog().sources.values():
        columns = [f'"{d}"' for d in source.dimensions]
        columns += [f'"{c}"' for c in (source.time_column, source.percentile_column) if c]
        columns += [f'"{c}"' for c in source.precomputed_columns.values()]
        measures = [f"sum({metrics._measure_sql(source, name)})" for name in source.measures]
        serving_db.execute(f"select {', '.join(columns)} from {source.table} limit 0")
        serving_db.execute(f"select {', '.join(measures)} from {source.table}")


def test_a_date_range_never_shifts_on_a_quarterly_source(serving_db, dbt_build):
    """Mar 2025 to Jul 2026 isn't whole quarters, so the district mart can't answer it exactly:
    the compiler must fall through to a monthly source rather than round to quarters."""
    window = ("2025-03-01", "2026-07-01")
    query = metrics.compile_query("verified_fix_rate", group_by=["cd"], date_range=window)
    assert query.source == "current_requests"
    quarters = metrics.compile_query(
        "verified_fix_rate", group_by=["cd"], date_range=("2025-04-01", "2026-06-01")
    )
    assert quarters.source == "gap_by_district"
    assert quarters.params[-2:] == ["2025-04-01", "2026-04-01"]  # Q2 2026 holds June
    direct = fact(
        dbt_build,
        "select avg(coalesce(outcome_group = 'fixed', false)::int) "
        f"from marts.fct_service_requests where era = 'current' and {FIX_BASE} "
        "and created_month between '2025-03-01' and '2026-07-01'",
    )
    assert value(serving_db, "verified_fix_rate", date_range=window) == pytest.approx(direct)


def test_date_ranges_are_whole_months(serving_db):
    for bad in [("2025-03-28", "2026-07-01"), ("2026-07-01", "2025-03-01"), ("March", "May")]:
        with pytest.raises(metrics.MetricError, match="first and last month"):
            metrics.compile_query("verified_fix_rate", date_range=bad)


def test_rankings_order_cut_and_skip_small_groups(serving_db):
    everything = metrics.run(
        serving_db, metrics.compile_query("closure_rate", group_by=["unified_category"])
    )
    ranked = metrics.run(
        serving_db,
        metrics.compile_query(
            "closure_rate", group_by=["unified_category"], order="value_desc", limit=2
        ),
    )
    best = sorted(everything, key=lambda r: (-(r["value"] or -1), r["unified_category"]))[:2]
    assert [r["unified_category"] for r in ranked] == [r["unified_category"] for r in best]
    big = metrics.run(
        serving_db,
        metrics.compile_query("closure_rate", group_by=["unified_category"], min_count=3),
    )
    assert big and all(r["denominator"] >= 3 for r in big)
    assert len(big) < len(everything)
    with pytest.raises(metrics.MetricError, match="order"):
        metrics.compile_query("closure_rate", order="random")
