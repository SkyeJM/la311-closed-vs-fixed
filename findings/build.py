"""findings.json: the numbers behind every claim, each with the query that produced it.

    uv run python -m findings          # needs data/serving.duckdb and data/warehouse.duckdb

Q1-Q5 (brief section 4.6) run on the served marts through the governed metrics in metrics.yml,
so the dashboard and the Ask agent see the same numbers. The E2 parameter evidence needs
coordinates and so runs on the warehouse (findings/e2.py). Prose anywhere in the project cites
these numbers by path; nothing is typed in by hand.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import yaml

from api import metrics

ROOT = Path(__file__).resolve().parents[1]
SERVING = ROOT / "data" / "serving.duckdb"
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "findings" / "findings.json"
AGREEMENT = ROOT / "ai" / "labels" / "agreement.json"
EVALS = ROOT / "evals" / "results"
DBT_PROJECT = ROOT / "dbt" / "dbt_project.yml"

PICKUPS = "Bulky & dumped item pickups"
ITEM_NOT_OUT = "QC-Item Not Out"
# Headline numbers use requests filed at least this long before the data ends, so most have had
# time to close (the new system's 90th-percentile time to close is about two weeks).
FOLLOWUP_DAYS = 60
MIN_BASE = 500  # smallest group whose rate is reported in a ranking
MIN_NC_CLOSED = 1_000


def _clean(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


@dataclass
class Recorder:
    """Runs metric queries and plain SQL, keeping each under an id for findings.json."""

    serving: duckdb.DuckDBPyConnection
    warehouse: duckdb.DuckDBPyConnection | None = None
    queries: dict = field(default_factory=dict)

    def metric(self, query_id: str, metric: str, **request) -> list[dict]:
        query = metrics.compile_query(metric, **request)
        rows = metrics.run(self.serving, query)
        self.queries[query_id] = {
            "database": "serving",
            "metric": metric,
            "request": _clean(
                {k: list(v) if isinstance(v, tuple) else v for k, v in request.items()}
            ),
            "source": query.source,
            "coverage": query.coverage,
            "sql": query.sql,
            "params": _clean(query.params),
        }
        return _clean(rows)

    def sql(self, query_id: str, sql: str, params=(), database: str = "serving") -> list[dict]:
        con = self.serving if database == "serving" else self.warehouse
        cursor = con.execute(sql, list(params))
        names = [d[0] for d in cursor.description]
        self.queries[query_id] = {
            "database": database,
            "sql": " ".join(sql.split()),
            "params": _clean(list(params)),
        }
        return [_clean(dict(zip(names, row, strict=True))) for row in cursor.fetchall()]


def one(rows: list[dict]) -> dict:
    assert len(rows) == 1, rows
    return rows[0]


def ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator else None


# --- sections ------------------------------------------------------------------------------


def data_section(rec: Recorder) -> dict:
    coverage = one(
        rec.sql(
            "data_coverage",
            "select min(created_at) as current_start, max(created_at) as data_end, "
            "count(*) as current_service_requests from fct_current_requests",
        )
    )
    eras = rec.metric("requests_by_era", "requests_created", group_by=["era"])
    contacts = rec.metric("contacts_by_era", "contacts", group_by=["era"])
    codes = one(
        rec.sql(
            "code_map_status",
            "select count(*) as codes, count(*) filter (where is_mapped) as mapped_codes, "
            "sum(n_service_cases) filter (where not is_mapped) as unmapped_code_service_cases "
            "from dim_resolution_code",
        )
    )
    sources = rec.sql(
        "code_label_sources",
        "select coalesce(label_source, 'unmapped') as label_source, count(*) as codes "
        "from dim_resolution_code group by 1 order by 2 desc",
    )
    return {
        "current_start": coverage["current_start"],
        "data_end": coverage["data_end"],
        "service_requests": {r["era"]: r["value"] for r in eras},
        "contacts": {r["era"]: r["value"] for r in contacts},
        "code_map": codes | {"label_sources": {r["label_source"]: r["codes"] for r in sources}},
        "query_ids": ["data_coverage", "requests_by_era", "contacts_by_era", "code_map_status"],
    }


def window_for(data_end: str) -> tuple[str, str]:
    """Months filed from the new system's start through the last month that ended at least
    FOLLOWUP_DAYS before the data does."""
    cutoff = datetime.fromisoformat(data_end).date() - timedelta(days=FOLLOWUP_DAYS)
    last = (cutoff.replace(day=1) - timedelta(days=1)).replace(day=1)
    return "2025-03-01", last.isoformat()


def rates(rec: Recorder, prefix: str, filters: dict | None = None, **request) -> dict:
    """The E1 trio on one request, plus the official closure rate for context."""
    filters = filters or {}
    gap = one(rec.metric(f"{prefix}_gap", "closed_fixed_gap_pp", filters=filters, **request))
    official = one(
        rec.metric(
            f"{prefix}_official_closure",
            "closure_rate",
            filters=filters | {"era": "current"},
            **request,
        )
    )
    return {
        "fix_rate_base": gap["a_denominator"],
        "closed": gap["a_numerator"],
        "verified_fixed": gap["b_numerator"],
        "closure_rate": ratio(gap["a_numerator"], gap["a_denominator"]),
        "verified_fix_rate": ratio(gap["b_numerator"], gap["b_denominator"]),
        "gap_pp": gap["value"],
        "official_closure_rate": official["value"],
        "official_closure_base": official["denominator"],
        "query_ids": [f"{prefix}_gap", f"{prefix}_official_closure"],
    }


def headline(rec: Recorder, window: tuple[str, str]) -> dict:
    mature = rates(rec, "headline", date_range=window)
    whole = rates(rec, "headline_all_months")
    excluded = rec.metric(
        "headline_excluded",
        "requests_created",
        group_by=["outcome_group"],
        filters={"era": "current", "outcome_group": ["neutral", "handed_off"]},
        date_range=window,
    )
    return {
        "window": {"from_month": window[0], "to_month": window[1]},
        **mature,
        "excluded_from_base": {r["outcome_group"]: r["value"] for r in excluded},
        "all_months": whole,
        "query_ids": mature["query_ids"] + ["headline_excluded"],
    }


def trend(rec: Recorder, window: tuple[str, str], data_end: str) -> dict:
    """The headline by month filed, for the Story page's chart. Months after the window are
    kept but flagged: their requests haven't had FOLLOWUP_DAYS to close, so their rates still
    move."""
    last = date.fromisoformat(data_end[:10]).replace(day=1).isoformat()
    rows = rec.metric(
        "trend_gap_by_month",
        "closed_fixed_gap_pp",
        time_grain="month",
        date_range=(window[0], last),
    )
    return {
        "months": [
            {
                "month": r["period_start"],
                "closure_rate": ratio(r["a_numerator"], r["a_denominator"]),
                "verified_fix_rate": ratio(r["b_numerator"], r["b_denominator"]),
                "gap_pp": r["value"],
                "fix_rate_base": r["a_denominator"],
                "full_followup": r["period_start"] <= window[1],
            }
            for r in rows
        ],
        "query_ids": ["trend_gap_by_month"],
    }


def q1_outcome_mix(rec: Recorder, window: tuple[str, str]) -> dict:
    mix = rec.metric("q1_mix", "outcome_mix", filters={"era": "current"}, date_range=window)
    by_category = rec.metric(
        "q1_gap_by_category",
        "closed_fixed_gap_pp",
        group_by=["unified_category"],
        date_range=window,
    )
    by_department = rec.metric(
        "q1_gap_by_department",
        "closed_fixed_gap_pp",
        group_by=["department"],
        date_range=window,
    )
    category_mix = rec.metric(
        "q1_mix_by_category",
        "outcome_mix",
        group_by=["unified_category"],
        filters={"era": "current"},
        date_range=window,
    )

    def table(rows: list[dict], key: str) -> list[dict]:
        out = [
            {
                key: r[key],
                "fix_rate_base": r["a_denominator"],
                "closure_rate": ratio(r["a_numerator"], r["a_denominator"]),
                "verified_fix_rate": ratio(r["b_numerator"], r["b_denominator"]),
                "gap_pp": r["value"],
            }
            for r in rows
            if (r["a_denominator"] or 0) >= MIN_BASE
        ]
        return sorted(out, key=lambda r: -r["fix_rate_base"])

    categories = table(by_category, "unified_category")
    top = {r["unified_category"] for r in categories[:12]}
    return {
        "mix": [
            {"closure_outcome": r["closure_outcome"], "requests": r["n"], "share": r["value"]}
            for r in sorted(mix, key=lambda r: -r["n"])
        ],
        "by_category": categories,
        "by_department": table(by_department, "department"),
        "mix_by_category": [
            {
                "unified_category": r["unified_category"],
                "closure_outcome": r["closure_outcome"],
                "share": r["value"],
            }
            for r in category_mix
            if r["unified_category"] in top
        ],
        "min_base": MIN_BASE,
        "query_ids": ["q1_mix", "q1_gap_by_category", "q1_gap_by_department", "q1_mix_by_category"],
    }


def q2_where_the_gap_is(rec: Recorder, window: tuple[str, str]) -> dict:
    combos = rec.metric(
        "q2_gap_by_category_department_cd",
        "closed_fixed_gap_pp",
        group_by=["unified_category", "department", "cd"],
        date_range=window,
        source="current_requests",
    )
    rows = [
        {
            "unified_category": r["unified_category"],
            "department": r["department"],
            "cd": r["cd"],
            "fix_rate_base": r["a_denominator"],
            "closed_unverified": r["a_numerator"] - r["b_numerator"],
            "gap_pp": r["value"],
        }
        for r in combos
        if (r["a_denominator"] or 0) >= MIN_BASE and r["cd"] is not None
    ]
    by_code = rec.metric(
        "q2_unverified_by_code",
        "closed_unverified",
        group_by=["resolution_code", "closure_outcome"],
        date_range=window,
        source="current_requests",
    )
    total = sum(r["value"] or 0 for r in by_code)
    codes = sorted(
        (
            {
                "resolution_code": r["resolution_code"] or "(no code)",
                "closure_outcome": r["closure_outcome"],
                "closed_unverified": r["value"],
                "share_of_gap": ratio(r["value"], total),
            }
            for r in by_code
            if r["value"]
        ),
        key=lambda r: -r["closed_unverified"],
    )
    return {
        "largest_gap_rate": sorted(rows, key=lambda r: -r["gap_pp"])[:15],
        "largest_gap_count": sorted(rows, key=lambda r: -r["closed_unverified"])[:15],
        "combinations_compared": len(rows),
        "closed_unverified_total": total,
        "top_codes": codes[:12],
        "top_5_codes_share": sum(r["share_of_gap"] for r in codes[:5]),
        "codes_in_gap": len(codes),
        "min_base": MIN_BASE,
        "query_ids": ["q2_gap_by_category_department_cd", "q2_unverified_by_code"],
    }


def q3_bulky_items(rec: Recorder, window: tuple[str, str]) -> dict:
    params = [ITEM_NOT_OUT, *window]
    totals = rec.sql(
        "q3_item_not_out_by_type",
        """
        select coalesce(request_type, 'All pickups') as request_type,
            sum(n_requests) filter (where is_closed) as closed,
            sum(n_requests) filter (where is_closed and resolution_code = ?) as item_not_out
        from mart_bulky_items
        where created_month between ? and ?
        group by rollup (request_type)
        order by closed desc
        """,
        params,
    )
    by_nc = rec.sql(
        "q3_item_not_out_by_nc",
        """
        select b.nc_code, g.geo_name as nc_name,
            sum(n_requests) filter (where is_closed) as closed,
            sum(n_requests) filter (where is_closed and resolution_code = ?) as item_not_out
        from mart_bulky_items as b
        left join dim_geography as g
            on g.geo_level = 'neighborhood_council' and g.geo_code = b.nc_code
        where b.created_month between ? and ? and b.nc_code is not null
        group by b.nc_code, g.geo_name
        order by b.nc_code
        """,
        params,
    )
    by_weekday = rec.sql(
        "q3_item_not_out_by_weekday",
        """
        select closed_weekday,
            sum(n_requests) filter (where is_closed) as closed,
            sum(n_requests) filter (where is_closed and resolution_code = ?) as item_not_out
        from mart_bulky_items
        where created_month between ? and ? and closed_weekday is not null
        group by closed_weekday
        order by closed_weekday
        """,
        params,
    )
    followups = {}
    for metric in ["rereport_30d_rate", "prior_report_30d_rate"]:
        rows = rec.metric(
            f"q3_{metric}_by_code",
            metric,
            group_by=["resolution_code"],
            filters={
                "era": "current",
                "unified_category": PICKUPS,
                "resolution_code": [ITEM_NOT_OUT, "AR-Request Completed"],
            },
            date_range=window,
            source="bulky_items",
        )
        for r in rows:
            followups.setdefault(r["resolution_code"], {})[metric] = r["value"]
            followups[r["resolution_code"]]["eligible"] = r["denominator"]

    def share(row: dict) -> dict:
        return row | {"item_not_out_share": ratio(row["item_not_out"], row["closed"])}

    ncs = sorted(
        (share(r) for r in by_nc if (r["closed"] or 0) >= MIN_NC_CLOSED),
        key=lambda r: r["item_not_out_share"],
    )
    shares = [r["item_not_out_share"] for r in ncs]
    names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return {
        "by_request_type": [share(r) for r in totals],
        "neighborhood_councils": {
            "compared": len(ncs),
            "min_closed": MIN_NC_CLOSED,
            "lowest": ncs[:5],
            "highest": ncs[-5:][::-1],
            "median_share": shares[len(shares) // 2] if shares else None,
        },
        "by_closed_weekday": [
            share(r) | {"weekday": names[int(r["closed_weekday"])]} for r in by_weekday
        ],
        "new_pickup_request_within_30d": followups,
        "query_ids": [
            "q3_item_not_out_by_type",
            "q3_item_not_out_by_nc",
            "q3_item_not_out_by_weekday",
            "q3_rereport_30d_rate_by_code",
            "q3_prior_report_30d_rate_by_code",
        ],
    }


Q4_METRICS = [
    "requests_created",
    "closed_within_7d_rate",
    "closed_within_30d_rate",
    "cancellation_rate",
    "instant_close_rate",
    "rereport_30d_rate",
    "prior_report_30d_rate",
    "rereport_excess_pp",
    "median_hours_to_close",
]


def q4_cutover(rec: Recorder) -> dict:
    table: dict[str, dict] = {}
    periods = {}
    for metric in Q4_METRICS:
        # The period mart holds resident-reported requests only; saying so lets every metric,
        # counts included, be answered from it.
        rows = rec.metric(
            f"q4_{metric}",
            metric,
            group_by=["unified_category", "era", "period"],
            filters={"is_crew_self_report": False},
        )
        for r in rows:
            entry = table.setdefault(r["unified_category"], {})
            entry.setdefault(metric, {})[r["period"]] = r["value"]
    bounds = rec.sql(
        "q4_period_bounds",
        "select period, min(first_month) as first_month, max(last_month) as last_month "
        "from mart_cutover_periods group by period order by min(first_month)",
    )
    periods = {
        r["period"]: {"first_month": r["first_month"], "last_month": r["last_month"]}
        for r in bounds
    }
    comparable = rec.sql(
        "q4_comparability",
        "select distinct unified_category, cross_era_comparison from mart_cutover_periods "
        "order by 1",
    )
    kinds = {r["unified_category"]: r["cross_era_comparison"] for r in comparable}
    categories = []
    for category, values in sorted(table.items()):
        row = {"unified_category": category, "cross_era_comparison": kinds[category]}
        for metric, by_period in values.items():
            before, after = by_period.get("before"), by_period.get("after")
            row[metric] = {"before": before, "after": after}
            if before is not None and after is not None and metric != "requests_created":
                row[metric]["change"] = after - before
        categories.append(row)
    monthly = rec.metric(
        "q4_closed_within_30d_monthly",
        "closed_within_30d_rate",
        group_by=["unified_category", "era"],
        time_grain="month",
    )
    gap_monthly = rec.metric("q4_gap_monthly", "closed_fixed_gap_pp", time_grain="month")
    return {
        "periods": periods,
        "categories": categories,
        "series": {
            "closed_within_30d_rate": [
                {k: r[k] for k in ("period_start", "unified_category", "era", "value")}
                for r in monthly
                if r["value"] is not None
            ],
            "closed_fixed_gap_pp": [
                {"period_start": r["period_start"], "value": r["value"]} for r in gap_monthly
            ],
        },
        "query_ids": [f"q4_{m}" for m in Q4_METRICS]
        + [
            "q4_period_bounds",
            "q4_comparability",
            "q4_closed_within_30d_monthly",
            "q4_gap_monthly",
        ],
    }


def q5_proxy_validation(rec: Recorder, window: tuple[str, str]) -> dict:
    # Proxies are judged on resident-reported requests, the population they'd be applied to in
    # the legacy era (crew self-reports are closed by construction).
    current = {"era": "current", "is_crew_self_report": False}
    instant_mix = rec.metric(
        "q5_mix_by_instant_close",
        "outcome_mix",
        group_by=["is_instant_close"],
        filters=current | {"is_closed": True},
        date_range=window,
    )
    instant_fix = rec.metric(
        "q5_fix_rate_by_instant_close",
        "verified_fix_rate",
        group_by=["is_instant_close"],
        filters={"is_closed": True, "is_crew_self_report": False},
        date_range=window,
        source="current_requests",
    )
    by_speed = rec.sql(
        "q5_outcome_by_time_to_close",
        """
        select
            case
                when hours_to_close < 1.0 / 60 then '1: under 1 minute'
                when hours_to_close < 1 then '2: 1 minute to 1 hour'
                when hours_to_close < 24 then '3: 1 hour to 1 day'
                when hours_to_close < 7 * 24 then '4: 1 to 7 days'
                when hours_to_close < 30 * 24 then '5: 7 to 30 days'
                else '6: over 30 days'
            end as time_to_close,
            count(*) as closed,
            avg(case when outcome_group = 'fixed' then 1.0 else 0 end) as fixed_share,
            avg(case when outcome_group = 'not_fixed' then 1.0 else 0 end) as not_fixed_share,
            avg(case when closure_outcome = 'closed_unspecified' then 1.0 else 0 end)
                as unspecified_share
        from fct_current_requests
        where is_closed and hours_to_close >= 0 and not is_crew_self_report
            and coalesce(outcome_group, '') not in ('neutral', 'handed_off')
            and created_month between ? and ?
        group by 1
        order by 1
        """,
        window,
    )
    rereports = {}
    for metric in ["rereport_30d_rate", "prior_report_30d_rate"]:
        rows = rec.metric(
            f"q5_{metric}_by_outcome",
            metric,
            group_by=["unified_category", "outcome_group"],
            filters=current | {"outcome_group": ["fixed", "not_fixed", "unknown"]},
            date_range=window,
            source="current_requests",
        )
        for r in rows:
            key = (r["unified_category"], r["outcome_group"])
            rereports.setdefault(key, {"eligible": r["denominator"]})[metric] = r["value"]
    by_category: dict[str, dict] = {}
    for (category, group), values in rereports.items():
        if values["eligible"] >= MIN_BASE:
            by_category.setdefault(category, {})[group] = values
    return {
        "instant_close": {
            "mix": [
                {
                    "is_instant_close": r["is_instant_close"],
                    "closure_outcome": r["closure_outcome"],
                    "requests": r["n"],
                    "share": r["value"],
                }
                for r in instant_mix
            ],
            "verified_fix_rate": {
                str(r["is_instant_close"]).lower(): r["value"] for r in instant_fix
            },
        },
        "time_to_close": by_speed,
        "rereports_by_outcome": {
            category: groups for category, groups in sorted(by_category.items()) if len(groups) > 1
        },
        "min_base": MIN_BASE,
        "query_ids": [
            "q5_mix_by_instant_close",
            "q5_fix_rate_by_instant_close",
            "q5_outcome_by_time_to_close",
            "q5_rereport_30d_rate_by_outcome",
            "q5_prior_report_30d_rate_by_outcome",
        ],
    }


def git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build(serving: Path = SERVING, warehouse: Path | None = WAREHOUSE) -> dict:
    from findings import e2

    if warehouse and serving.stat().st_mtime < warehouse.stat().st_mtime:
        raise SystemExit(f"{serving.name} is older than {warehouse.name}: run `make serving` first")
    rec = Recorder(
        duckdb.connect(str(serving), read_only=True),
        duckdb.connect(str(warehouse), read_only=True) if warehouse else None,
    )
    params = yaml.safe_load(DBT_PROJECT.read_text())["vars"]
    data = data_section(rec)
    window = window_for(data["data_end"])
    # Final only when the reviewed map is switched on and the data has no unmapped code.
    final = params["code_map_final"] and not data["code_map"]["unmapped_code_service_cases"]
    result = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": git_commit(),
        "status": "final" if final else "provisional",
        "status_note": (
            "Every resolution code in the data is mapped, and the map has been reviewed."
            if final
            else "Some resolution codes aren't mapped yet: they count as closed without "
            "evidence of a fix until they're labeled and reviewed."
        ),
        "parameters": {
            k: params[k]
            for k in (
                "cutover_date",
                "instant_close_minutes",
                "rereport_radius_m",
                "rereport_window_days",
                "overlap_end_date",
                "cutover_compare_months",
                "cutover_followup_days",
            )
        }
        | {"headline_followup_days": FOLLOWUP_DAYS},
        "data": data,
        "headline": headline(rec, window),
        "trend": trend(rec, window, data["data_end"]),
        "q1_outcome_mix": q1_outcome_mix(rec, window),
        "q2_where_the_gap_is": q2_where_the_gap_is(rec, window),
        "q3_bulky_items": q3_bulky_items(rec, window),
        "q4_cutover": q4_cutover(rec),
        "q5_proxy_validation": q5_proxy_validation(rec, window),
    }
    if rec.warehouse is not None:
        result["e2_parameters"] = e2.evidence(rec)
    if AGREEMENT.exists():
        result["ai_labeling"] = json.loads(AGREEMENT.read_text())
    if (EVALS / "summary.json").exists():
        # The Ask agent's eval results (make eval), so prose about the agent cites this file too.
        # Round 2 ran before the step-counter fix; the docs quote what that fix changed.
        evals = {"current": json.loads((EVALS / "summary.json").read_text())}
        before = sorted(EVALS.glob("*_claude-sonnet-5-5_round2.json"))
        if before:
            evals["sonnet_before_step_counter"] = json.loads(before[-1].read_text())["summary"]
        result["ask_evals"] = evals
    result = _clean(result)
    result["queries"] = rec.queries
    return result


def write(result: dict, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
