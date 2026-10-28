-- Both eras in one shape (brief section 3.2), with the reviewed seeds applied: unified category,
-- service vs contact, terminal status. Era is the system of record, never inferred from dates.
-- Dropped here on purpose: assigned_to (crews and yards; brief section 10 rules out claims about
-- crews), cd_member (a person's name), police_area (names in one era, numbers in the other).

with requests as (
    select
        request_id, 'legacy' as era, source_dataset_id, source_request_id,
        created_at, updated_at, closed_at, service_date,
        cast(null as date) as service_rendered_on,
        status, request_type, department, channel, created_by_org, call_action,
        cast(null as varchar) as resolution_code,
        cast(null as varchar) as reason_code,
        is_anonymous, is_approximate_address,
        lat, lon, has_out_of_area_coordinates, zip, cd, nc_code, nc_name, apc
    from {{ ref('stg_legacy__requests') }}

    union all

    select
        request_id, 'current' as era, source_dataset_id, source_request_id,
        created_at, updated_at, closed_at, service_date,
        service_rendered_on,
        status, request_type, department, channel, created_by_org, call_action,
        resolution_code,
        reason_code,
        is_anonymous, cast(null as boolean) as is_approximate_address,
        lat, lon, has_out_of_area_coordinates, zip, cd, nc_code, nc_name, apc
    from {{ ref('stg_current__cases') }}
)

select
    r.*,
    cast({{ dbt.date_trunc('month', 'r.created_at') }} as date) as created_month,
    coalesce(x.unified_category, r.request_type) as unified_category,
    x.unified_category is not null as is_crosswalked,
    coalesce(c.cross_era_comparison, 'none') as cross_era_comparison,
    ns.request_type is null as is_service_request,
    s.is_terminal,
    -- The official view: the status itself says closed (Closed, Closed Ext-Referred; legacy
    -- Closed, Referred Out). Cancelled and Reported are terminal but not closed.
    s.is_closed,
    -- "Driver Self Report(ed)": crews logging work they already did, closed by construction.
    coalesce(r.channel in ('Driver Self Report', 'Driver Self Reported'), false)
        as is_crew_self_report,
    {{ hours_between('r.created_at', 'r.closed_at') }} as hours_to_close,
    r.closed_at < r.created_at as is_closed_before_created,
    -- Date-only closes (legacy streetlights 2017-2021) land on midnight exactly.
    r.closed_at = {{ dbt.date_trunc('day', 'r.closed_at') }} as is_closed_at_midnight,
    {{ spatial_cell_x('r.lon') }} as cell_x,
    {{ spatial_cell_y('r.lat') }} as cell_y
from requests as r
left join {{ ref('request_type_crosswalk') }} as x
    on x.era = r.era and x.request_type = r.request_type
left join {{ ref('unified_categories') }} as c
    on c.unified_category = x.unified_category
left join {{ ref('non_service_types') }} as ns
    on ns.era = r.era and ns.request_type = r.request_type
left join {{ ref('status_map') }} as s
    on s.era = r.era and s.status = r.status
