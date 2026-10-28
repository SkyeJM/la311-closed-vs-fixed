-- One row per raw request type in each era, with its unified category, whether it can be
-- compared across eras, and whether it is a service request at all.

select
    r.era,
    r.request_type,
    r.unified_category,
    r.is_crosswalked,
    r.cross_era_comparison,
    c.comparability_note,
    r.is_service_request,
    ns.reason as non_service_reason,
    count(*) as n_requests,
    min(r.created_at) as first_created_at,
    max(r.created_at) as last_created_at,
    mode(r.department) as main_department
from {{ ref('int_requests_unified') }} as r
left join {{ ref('unified_categories') }} as c
    on c.unified_category = r.unified_category and r.is_crosswalked
left join {{ ref('non_service_types') }} as ns
    on ns.era = r.era and ns.request_type = r.request_type
group by
    r.era, r.request_type, r.unified_category, r.is_crosswalked, r.cross_era_comparison,
    c.comparability_note, r.is_service_request, ns.reason
