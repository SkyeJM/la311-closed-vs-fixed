-- One row per service request in either era. Contacts (non_service_types) are excluded and
-- counted in mart_contacts_info_only. This is the warehouse's analysis table: it keeps
-- coordinates for spatial work, so it never ships to serving.
{%- set days = var('rereport_window_days') %}

with requests as (
    select * from {{ ref('int_requests_unified') }}
    where is_service_request
),

coverage as (
    select max(created_at) as data_end
    from {{ ref('int_requests_unified') }}
),

flagged as (
    select
        r.*,
        o.closure_outcome,
        o.outcome_basis,
        o.code_label_source,
        s.status_outcome,
        rr.n_rereports,
        rr.first_rereport_at,
        -- A re-report window counts only when it can be observed in full: it ends before the
        -- data does, and, for types only the legacy system had, before the cutover (nobody files
        -- them in the legacy system after it).
        coalesce(
            r.is_terminal
            and r.closed_at is not null
            and r.lat is not null
            and {{ dbt.dateadd('day', days, 'r.closed_at') }} <= c.data_end
            and (
                r.is_crosswalked
                or r.era = 'current'
                or {{ dbt.dateadd('day', days, 'r.closed_at') }}
                    < cast('{{ var("cutover_date") }}' as timestamp)
            ),
            false
        ) as is_rereport_eligible
    from requests as r
    cross join coverage as c
    left join {{ ref('int_request_outcomes') }} as o
        on o.request_id = r.request_id
    left join {{ ref('status_map') }} as s
        on s.era = r.era and s.status = r.status
    left join {{ ref('int_rereports') }} as rr
        on rr.request_id = r.request_id
)

select
    f.request_id,
    f.era,
    f.source_dataset_id,
    f.source_request_id,
    f.created_at,
    f.updated_at,
    f.closed_at,
    f.created_month,
    f.request_type,
    f.unified_category,
    f.is_crosswalked,
    f.cross_era_comparison,
    f.department,
    f.channel,
    f.created_by_org,
    f.is_crew_self_report,
    f.is_anonymous,
    f.status,
    f.is_terminal,
    f.status_outcome,
    f.resolution_code,
    f.reason_code,
    f.closure_outcome,
    f.outcome_basis,
    f.code_label_source,
    co.counts_as_fixed,
    co.outcome_group,
    -- Time to close is defined for terminal requests only: about 1% of legacy Open rows (and
    -- some Forward rows) carry a closed date although the request is still open.
    case when f.is_terminal then f.hours_to_close end as hours_to_close,
    f.is_closed_before_created,
    f.is_closed_at_midnight,
    case
        when f.is_terminal
            then f.hours_to_close >= 0
            and f.hours_to_close <= {{ var('instant_close_minutes') }} / 60.0
    end as is_instant_close,
    f.is_rereport_eligible,
    case when f.is_rereport_eligible then coalesce(f.n_rereports, 0) end as n_rereports_30d,
    case when f.is_rereport_eligible then f.n_rereports is not null end as is_rereported_30d,
    case when f.is_rereport_eligible then f.first_rereport_at end as first_rereport_at,
    f.cd,
    f.nc_code,
    f.nc_name,
    f.apc,
    f.zip,
    f.lat,
    f.lon,
    f.has_out_of_area_coordinates,
    f.is_approximate_address
from flagged as f
left join {{ ref('closure_outcomes') }} as co
    on co.closure_outcome = f.closure_outcome
