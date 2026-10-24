-- Where the closed-vs-fixed gap is (brief Q2 and Q7): current-era service requests by quarter,
-- category, department, council district and resolution code. Explicit outcomes (E1) exist only
-- in the new system, so the legacy era is not here. Crew self-reports are a dimension rather
-- than a filter: within the current era they are part of the record, but they are logged as
-- done by construction.

select
    cast({{ dbt.date_trunc('quarter', 'created_at') }} as date) as created_quarter,
    unified_category,
    request_type,
    department,
    cd,
    is_crew_self_report,
    is_terminal,
    resolution_code,
    closure_outcome,
    count(*) as n_requests
from {{ ref('fct_service_requests') }}
where era = 'current'
group by
    cast({{ dbt.date_trunc('quarter', 'created_at') }} as date), unified_category, request_type,
    department, cd, is_crew_self_report, is_terminal, resolution_code, closure_outcome
