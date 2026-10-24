-- Brief section 5.1: every observed resolution code must be in resolution_code_map. A new code
-- is the brief's alert. It warns while the map is provisional (Phase 2) and fails the build once
-- Phase 3 sets `code_map_final: true`.
{{ config(severity = 'error' if var('code_map_final') else 'warn') }}

select
    u.resolution_code,
    count(*) as n_cases
from {{ ref('int_requests_unified') }} as u
where u.resolution_code is not null
    and not exists (
        select 1
        from {{ ref('resolution_code_map') }} as m
        where m.resolution_code = u.resolution_code
    )
group by u.resolution_code
