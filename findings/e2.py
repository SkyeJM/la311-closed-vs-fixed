"""Evidence for the E2 proxy parameters (brief section 4.3), from the warehouse.

Instant close: where the closed-at-intake spike ends, and how much the threshold matters.
Re-reports: how the after-closing rate and its before-filing placebo move with the radius and
the window, on a fixed sample of eligible closed requests (1 in 50 by DuckDB's hash of the
request ID, so reruns pick the same requests).
"""

from __future__ import annotations

RADII_M = [25, 50, 100]
WINDOWS_DAYS = [7, 14, 30, 60]
SAMPLE_ONE_IN = 50


def instant_close(rec) -> dict:
    spike = rec.sql(
        "e2_seconds_to_close_current",
        """
        select
            case
                when hours_to_close * 3600 < 10 then '1: under 10 seconds'
                when hours_to_close * 3600 < 60 then '2: 10 to 59 seconds'
                when hours_to_close * 60 < 2 then '3: 1 to 2 minutes'
                when hours_to_close * 60 < 5 then '4: 2 to 5 minutes'
                when hours_to_close * 60 < 10 then '5: 5 to 10 minutes'
                when hours_to_close < 1 then '6: 10 to 60 minutes'
                else '7: an hour or more'
            end as time_to_close,
            count(*) as closed,
            avg(case when outcome_group = 'fixed' then 1.0 else 0 end) as fixed_share,
            avg(case when outcome_group = 'neutral' then 1.0 else 0 end) as neutral_share,
            avg(case when closure_outcome = 'closed_unspecified' then 1.0 else 0 end)
                as unspecified_share
        from marts.fct_service_requests
        where era = 'current' and is_closed and hours_to_close >= 0 and not is_crew_self_report
        group by 1
        order by 1
        """,
        database="warehouse",
    )
    precision = rec.sql(
        "e2_legacy_precision",
        """
        select
            case when year(created_at) <= 2019 then '2015-2019' else '2020-2025' end as years,
            count(*) filter (where hours_to_close = 0) as closed_at_0_seconds,
            count(*) filter (where hours_to_close > 0 and hours_to_close * 60 < 1)
                as closed_1_to_59_seconds,
            count(*) as closed
        from marts.fct_service_requests
        where era = 'legacy' and is_closed and hours_to_close >= 0 and not is_crew_self_report
        group by 1
        order by 1
        """,
        database="warehouse",
    )
    thresholds = rec.sql(
        "e2_instant_close_thresholds",
        """
        select era,
            count(*) as closed,
            avg(case when hours_to_close * 60 <= 1 then 1.0 else 0 end) as within_1_min,
            avg(case when hours_to_close * 60 <= 2 then 1.0 else 0 end) as within_2_min,
            avg(case when hours_to_close * 60 <= 5 then 1.0 else 0 end) as within_5_min,
            avg(case when hours_to_close * 60 <= 10 then 1.0 else 0 end) as within_10_min
        from marts.fct_service_requests
        where is_crosswalked and cross_era_comparison <> 'volume_only'
            and not is_crew_self_report and is_closed and hours_to_close >= 0
        group by era
        order by era
        """,
        database="warehouse",
    )
    return {
        "current_seconds_to_close": spike,
        "legacy_timestamp_precision": precision,
        "crosswalked_share_closed_within": thresholds,
        "query_ids": [
            "e2_seconds_to_close_current",
            "e2_legacy_precision",
            "e2_instant_close_thresholds",
        ],
    }


def _flag(direction: str, radius: int, window: int) -> str:
    return (
        f"max(case when p.direction = '{direction}' and p.meters <= {radius} and p.days > 0 "
        f"and p.days <= {window} then 1 else 0 end) as {direction}_{radius}_{window}"
    )


def rereport_sensitivity(rec) -> dict:
    max_r, max_w = max(RADII_M), max(WINDOWS_DAYS)
    cell = max_r * 1.1  # as in macros/portability.sql: neighbors lie in the 3x3 block
    flags = ",\n            ".join(
        _flag(d, r, w) for d in ("after", "before") for r in RADII_M for w in WINDOWS_DAYS
    )
    rates = ",\n        ".join(
        f"avg({d}_{r}_{w}) as {d}_{r}_{w}"
        for d in ("after", "before")
        for r in RADII_M
        for w in WINDOWS_DAYS
    )
    rows = rec.sql(
        "e2_rereport_sensitivity",
        f"""
        with bounds as (
            select min(created_at) as data_start, max(created_at) as data_end
            from marts.fct_service_requests
        ),
        located as (
            select request_id, era, unified_category, created_at, closed_at, lat, lon,
                is_closed, is_crew_self_report, closure_outcome,
                cast(floor(lon * 111195.08 * 0.82855 / {cell}) as bigint) as cx,
                cast(floor(lat * 111195.08 / {cell}) as bigint) as cy
            from marts.fct_service_requests
            where is_crosswalked and lat is not null
        ),
        anchors as (
            select l.*,
                floor(epoch(l.closed_at) / 86400 / {max_w}) as close_bucket,
                floor(epoch(l.created_at) / 86400 / {max_w}) as file_bucket
            from located as l
            cross join bounds as b
            where l.is_closed and not l.is_crew_self_report and l.closed_at is not null
                and l.closed_at + interval {max_w} day <= b.data_end
                and l.created_at - interval {max_w} day >= b.data_start
                and hash(l.request_id) % {SAMPLE_ONE_IN} = 0
        ),
        reports as (
            select request_id, unified_category, created_at, lat, lon, cx, cy,
                floor(epoch(created_at) / 86400 / {max_w}) as bucket
            from located
            where not is_crew_self_report and coalesce(closure_outcome, '') <> 'duplicate'
        ),
        search_keys as (
            select a.request_id, a.unified_category, a.lat, a.lon, a.created_at, a.closed_at,
                w.direction,
                a.cx + x.dx as sx,
                a.cy + y.dy as sy,
                case when w.direction = 'after' then a.close_bucket else a.file_bucket end
                    + w.dt as sb
            from anchors as a
            cross join (values (-1), (0), (1)) as x (dx)
            cross join (values (-1), (0), (1)) as y (dy)
            cross join (values ('after', 0), ('after', 1), ('before', -1), ('before', 0))
                as w (direction, dt)
        ),
        pairs as (
            select k.request_id, k.direction,
                2 * 6371008.8 * asin(sqrt(
                    power(sin(radians(r.lat - k.lat) / 2), 2)
                    + cos(radians(k.lat)) * cos(radians(r.lat))
                    * power(sin(radians(r.lon - k.lon) / 2), 2)
                )) as meters,
                case
                    when k.direction = 'after' then epoch(r.created_at - k.closed_at)
                    else epoch(k.created_at - r.created_at)
                end / 86400.0 as days
            from search_keys as k
            inner join reports as r
                on r.cx = k.sx and r.cy = k.sy and r.bucket = k.sb
                and r.unified_category = k.unified_category
            where r.request_id <> k.request_id
        ),
        flags as (
            select a.request_id, a.era, a.unified_category,
            {flags}
            from anchors as a
            left join pairs as p on p.request_id = a.request_id
            group by a.request_id, a.era, a.unified_category
        )
        select era, unified_category, count(*) as sampled_requests,
        {rates}
        from flags
        group by era, unified_category
        order by unified_category, era
        """,
        database="warehouse",
    )
    grid = []
    for row in rows:
        for radius in RADII_M:
            for window in WINDOWS_DAYS:
                after = row[f"after_{radius}_{window}"]
                before = row[f"before_{radius}_{window}"]
                grid.append(
                    {
                        "era": row["era"],
                        "unified_category": row["unified_category"],
                        "sampled_requests": row["sampled_requests"],
                        "radius_m": radius,
                        "window_days": window,
                        "after_close": after,
                        "before_filing": before,
                        "excess_pp": round((after - before) * 100, 2),
                    }
                )
    signs = {}
    for g in grid:
        key = f"{g['unified_category']} | {g['era']}"
        entry = signs.setdefault(key, {"settings": 0, "after_above_before": 0})
        entry["settings"] += 1
        entry["after_above_before"] += g["excess_pp"] > 0
    return {
        "sample": f"1 in {SAMPLE_ONE_IN} eligible closed requests (resident-reported, located, "
        f"both {max_w}-day windows observable), crosswalked categories",
        "grid": grid,
        "after_above_before_by_category": signs,
        "query_ids": ["e2_rereport_sensitivity"],
    }


def evidence(rec) -> dict:
    return {"instant_close": instant_close(rec), "rereport": rereport_sensitivity(rec)}
