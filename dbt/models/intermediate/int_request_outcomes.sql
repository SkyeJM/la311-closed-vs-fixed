-- One closure_outcome per terminal request (brief section 4.2).
--   * A status marked status_decides sets the outcome even when the case has a code. Only
--     "Reported" does: those cases end at intake and are worked in another department's system,
--     and their codes ("C-Report has been received") acknowledge intake rather than describe an
--     outcome (decision 4, Phase 3).
--   * Otherwise a resolution code decides when the map knows it (current era only: E1
--     evidence). The most specific map row wins: code + department + type, then code +
--     department, then code + type, then the code alone.
--   * A terminal case with no code takes its status's outcome from status_map (the only option in
--     the legacy era).
--   * A code the map doesn't know yet leaves the outcome null (outcome_basis = 'unmapped_code');
--     assert_all_resolution_codes_mapped reports these.
--   * Open (non-terminal) requests have no outcome.

with requests as (
    select request_id, era, status, is_terminal, resolution_code, department, request_type
    from {{ ref('int_requests_unified') }}
),

code_matches as (
    select
        r.request_id,
        m.closure_outcome,
        m.label_source
    from requests as r
    inner join {{ ref('resolution_code_map') }} as m
        on m.resolution_code = r.resolution_code
        and (m.department is null or m.department = r.department)
        and (m.request_type is null or m.request_type = r.request_type)
    qualify row_number() over (
        partition by r.request_id
        order by
            cast(m.department is not null as integer) desc,
            cast(m.request_type is not null as integer) desc
    ) = 1
)

select
    r.request_id,
    case
        when not r.is_terminal then null
        when s.status_decides or r.resolution_code is null then s.status_outcome
        else c.closure_outcome
    end as closure_outcome,
    case
        when not r.is_terminal then 'open'
        when s.status_decides or r.resolution_code is null then 'status'
        when c.closure_outcome is not null then 'resolution_code'
        else 'unmapped_code'
    end as outcome_basis,
    case when not s.status_decides then c.label_source end as code_label_source
from requests as r
left join code_matches as c
    on c.request_id = r.request_id
left join {{ ref('status_map') }} as s
    on s.era = r.era and s.status = r.status
