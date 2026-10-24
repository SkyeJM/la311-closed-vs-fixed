-- Nothing is lost or double-counted between layers: service requests plus contacts make up every
-- unified request, and each mart sums back to the slice of the fact table it covers.

with totals as (
    select 'unified requests' as layer, count(*) as n from {{ ref('int_requests_unified') }}
    union all
    select 'service requests + contacts', (select count(*) from {{ ref('fct_service_requests') }})
        + (select sum(n_contacts) from {{ ref('mart_contacts_info_only') }})
),

slices as (
    select 'mart_outcomes_monthly' as mart,
        (select sum(n_requests) from {{ ref('mart_outcomes_monthly') }}) as in_mart,
        (select count(*) from {{ ref('fct_service_requests') }}) as in_fact
    union all
    select 'mart_gap_by_district',
        (select sum(n_requests) from {{ ref('mart_gap_by_district') }}),
        (select count(*) from {{ ref('fct_service_requests') }} where era = 'current')
    union all
    select 'mart_cutover_comparison',
        (select sum(n_requests) from {{ ref('mart_cutover_comparison') }}),
        (select count(*) from {{ ref('fct_service_requests') }}
            where is_crosswalked and not is_crew_self_report)
    union all
    select 'mart_bulky_items',
        (select sum(n_requests) from {{ ref('mart_bulky_items') }}),
        (select count(*) from {{ ref('fct_service_requests') }}
            where era = 'current' and unified_category = 'Bulky & dumped item pickups')
)

select 'totals' as check_name, cast(min(n) as varchar) || ' vs ' || cast(max(n) as varchar) as detail
from totals
having min(n) <> max(n)
union all
select mart, cast(in_mart as varchar) || ' in mart vs ' || cast(in_fact as varchar) || ' in fact'
from slices
where in_mart <> in_fact
