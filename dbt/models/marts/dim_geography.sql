-- The areas the UI and the AI may aggregate to (brief section 10): council districts and
-- neighborhood councils. NC names vary by year and system ("Sylmar" vs "SYLMAR NC"), so each
-- code takes its most common current-era name, falling back to the legacy one. NC boundaries
-- have changed over time (subdivisions), so cross-era NC comparisons are approximate.

with requests as (
    select era, cd, nc_code, nc_name
    from {{ ref('int_requests_unified') }}
),

nc_name_counts as (
    select nc_code, era, nc_name, count(*) as n
    from requests
    where nc_code is not null and nc_name is not null
    group by nc_code, era, nc_name
),

nc_names as (
    select
        nc_code,
        max_by(case when era = 'current' then nc_name end, case when era = 'current' then n end)
            as current_name,
        max_by(case when era = 'legacy' then nc_name end, case when era = 'legacy' then n end)
            as legacy_name
    from nc_name_counts
    group by nc_code
),

nc_primary_cd as (
    select nc_code, max_by(cd, n) as primary_cd
    from (
        select nc_code, cd, count(*) as n
        from requests
        where nc_code is not null and cd is not null
        group by nc_code, cd
    ) as nc_cd
    group by nc_code
),

nc_counts as (
    select
        nc_code,
        sum(case when era = 'legacy' then 1 else 0 end) as n_requests_legacy,
        sum(case when era = 'current' then 1 else 0 end) as n_requests_current
    from requests
    where nc_code is not null
    group by nc_code
),

cd_counts as (
    select
        cd,
        sum(case when era = 'legacy' then 1 else 0 end) as n_requests_legacy,
        sum(case when era = 'current' then 1 else 0 end) as n_requests_current
    from requests
    where cd is not null
    group by cd
)

select
    'council_district' as geo_level,
    cd as geo_code,
    'Council District ' || cast(cd as varchar) as geo_name,
    cast(null as integer) as primary_cd,
    n_requests_legacy,
    n_requests_current
from cd_counts

union all

select
    'neighborhood_council' as geo_level,
    c.nc_code as geo_code,
    coalesce(n.current_name, upper(n.legacy_name)) as geo_name,
    p.primary_cd,
    c.n_requests_legacy,
    c.n_requests_current
from nc_counts as c
left join nc_names as n
    on n.nc_code = c.nc_code
left join nc_primary_cd as p
    on p.nc_code = c.nc_code
