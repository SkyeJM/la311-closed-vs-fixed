-- E2 re-report signal (brief section 4.3): a closed request R (its status says closed) is
-- re-reported when a new request in
-- the same unified category is filed within `rereport_radius_m` of R within
-- `rereport_window_days` after R's closed_at. The same search over the window *before R was
-- filed* is the placebo baseline: how often that place sees a new request anyway. Re-reports in
-- excess of it are the part a closure could plausibly explain. One row per closed request with at
-- least one report in either window.
--
-- Never counted: R itself, crew self-reports (crews logging their own work, not a new report),
-- and requests closed as duplicates (their outcome lives on another request). Requests from either
-- era count, so a legacy request closed just before the cutover can be re-reported in the new
-- system. Window completeness (censoring) is decided in fct_service_requests.
--
-- Method: square spatial-hash cells (macros/portability.sql) and fixed time buckets turn the
-- search into equi-joins, then an exact great-circle distance filter keeps true neighbors.
{%- set radius = var('rereport_radius_m') %}
{%- set days = var('rereport_window_days') %}

with requests as (
    select
        u.request_id, u.unified_category, u.created_at, u.closed_at, u.lat, u.lon,
        u.cell_x, u.cell_y, u.is_closed, u.is_crew_self_report, o.closure_outcome
    from {{ ref('int_requests_unified') }} as u
    inner join {{ ref('int_request_outcomes') }} as o
        on o.request_id = u.request_id
    where u.is_service_request and u.lat is not null
),

closed_requests as (
    select
        request_id, unified_category, created_at, closed_at, lat, lon, cell_x, cell_y,
        floor({{ epoch_day('closed_at') }} / {{ days }}) as close_bucket,
        floor({{ epoch_day('created_at') }} / {{ days }}) as create_bucket
    from requests
    where is_closed and closed_at is not null
),

reports as (
    select
        request_id, unified_category, created_at, lat, lon, cell_x, cell_y,
        floor({{ epoch_day('created_at') }} / {{ days }}) as time_bucket
    from requests
    where not is_crew_self_report
        and coalesce(closure_outcome, '') <> 'duplicate'
),

-- Each closed request searches its own cell and the 8 around it: after closing, in its closing
-- bucket and the next; before filing, in its filing bucket and the previous. A window of `days`
-- never reaches further.
search_keys as (
    select
        c.request_id, w.direction, c.unified_category, c.lat, c.lon,
        case when w.direction = 'after_close' then c.closed_at else c.created_at end
            as anchor_at,
        c.cell_x + offsets_x.dx as search_x,
        c.cell_y + offsets_y.dy as search_y,
        case when w.direction = 'after_close' then c.close_bucket else c.create_bucket end
            + w.dt as search_bucket
    from closed_requests as c
    cross join (values (-1), (0), (1)) as offsets_x (dx)
    cross join (values (-1), (0), (1)) as offsets_y (dy)
    cross join (
        values ('after_close', 0), ('after_close', 1), ('before_filing', -1), ('before_filing', 0)
    ) as w (direction, dt)
),

pairs as (
    select
        k.request_id,
        k.direction,
        r.created_at
    from search_keys as k
    inner join reports as r
        on r.cell_x = k.search_x
        and r.cell_y = k.search_y
        and r.time_bucket = k.search_bucket
        and r.unified_category = k.unified_category
    where r.request_id <> k.request_id
        and (
            (
                k.direction = 'after_close'
                and r.created_at > k.anchor_at
                and r.created_at <= {{ dbt.dateadd('day', days, 'k.anchor_at') }}
            )
            or (
                k.direction = 'before_filing'
                and r.created_at < k.anchor_at
                and r.created_at >= {{ dbt.dateadd('day', -days, 'k.anchor_at') }}
            )
        )
        and {{ distance_m('k.lat', 'k.lon', 'r.lat', 'r.lon') }} <= {{ radius }}
)

select
    request_id,
    sum(case when direction = 'after_close' then 1 else 0 end) as n_rereports,
    min(case when direction = 'after_close' then created_at end) as first_rereport_at,
    sum(case when direction = 'before_filing' then 1 else 0 end) as n_prior_reports
from pairs
group by request_id
