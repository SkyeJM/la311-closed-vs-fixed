-- Map rows for codes that never occur are probably typos (codes are matched on the exact string).

{{ config(severity = 'warn') }}

select m.resolution_code, m.department, m.request_type
from {{ ref('resolution_code_map') }} as m
where not exists (
    select 1
    from {{ ref('int_requests_unified') }} as u
    where u.resolution_code = m.resolution_code
        and (m.department is null or u.department = m.department)
        and (m.request_type is null or u.request_type = m.request_type)
)
