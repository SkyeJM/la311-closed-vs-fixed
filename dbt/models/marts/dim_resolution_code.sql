-- One row per resolution code seen in the data (current era only; the legacy era has none), with
-- its code-level mapping and how it is used. Context overrides (department or type) are counted,
-- not shown: see resolution_code_map for them.

with usage as (
    select
        resolution_code,
        count(*) as n_cases,
        sum(case when is_service_request then 1 else 0 end) as n_service_cases,
        count(distinct department) as n_departments,
        count(distinct request_type) as n_request_types,
        mode(department) as main_department,
        mode(request_type) as main_request_type,
        mode(status) as main_status,
        min(created_at) as first_seen_at,
        max(created_at) as last_seen_at
    from {{ ref('int_requests_unified') }}
    where resolution_code is not null
    group by resolution_code
),

code_level as (
    select resolution_code, closure_outcome, label_source, rationale
    from {{ ref('resolution_code_map') }}
    where department is null and request_type is null
),

overrides as (
    select resolution_code, count(*) as n_context_overrides
    from {{ ref('resolution_code_map') }}
    where department is not null or request_type is not null
    group by resolution_code
)

select
    u.resolution_code,
    {{ dbt.split_part('u.resolution_code', "'-'", 1) }} as code_prefix,
    m.closure_outcome,
    co.counts_as_fixed,
    co.outcome_group,
    m.label_source,
    m.rationale,
    coalesce(o.n_context_overrides, 0) as n_context_overrides,
    m.resolution_code is not null as is_mapped,
    u.n_cases,
    u.n_service_cases,
    u.n_departments,
    u.n_request_types,
    u.main_department,
    u.main_request_type,
    u.main_status,
    u.first_seen_at,
    u.last_seen_at
from usage as u
left join code_level as m
    on m.resolution_code = u.resolution_code
left join {{ ref('closure_outcomes') }} as co
    on co.closure_outcome = m.closure_outcome
left join overrides as o
    on o.resolution_code = u.resolution_code
