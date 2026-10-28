-- Bulky and dumped item pickups in the new system (brief Q3): how large "QC-Item Not Out" is,
-- whether it varies by neighborhood council or weekday, and how often a new pickup request
-- follows at the same place. The weekday is the closing day, i.e. when the crew came.

select
    created_month,
    request_type,
    nc_code,
    cd,
    extract(dayofweek from closed_at) as closed_weekday,  -- 0 = Sunday
    is_crew_self_report,
    is_terminal,
    is_closed,
    resolution_code,
    closure_outcome,
    outcome_group,
    count(*) as n_requests,
    sum(case when is_rereport_eligible then 1 else 0 end) as n_rereport_eligible,
    sum(case when is_rereported_30d then 1 else 0 end) as n_rereported_30d,
    sum(case when has_prior_report_30d then 1 else 0 end) as n_prior_reported_30d
from {{ ref('fct_service_requests') }}
where era = 'current'
    and unified_category = 'Bulky & dumped item pickups'
group by
    created_month, request_type, nc_code, cd, extract(dayofweek from closed_at),
    is_crew_self_report, is_terminal, is_closed, resolution_code, closure_outcome, outcome_group
