-- The Apr-Aug 2025 overlap (brief section 3.3): legacy requests filed on or after the cutover,
-- and whether the same problem was also filed in the new system. A legacy request "matches" when
-- a current case in the same unified category was filed within `rereport_radius_m` and +-24 hours.
-- The placebo repeats the search 7-8 days away in either direction (the same 48-hour total
-- width): it estimates how often an unrelated case is simply nearby. Excess matches over the
-- placebo would mean double-recording; Phase 1 found about 0.6% for graffiti, i.e. a split by
-- channel (docs/DATA_NOTES.md).
{%- set radius = var('rereport_radius_m') %}

with legacy_tail as (
    select
        request_id, unified_category, request_type, channel, is_crew_self_report, created_at,
        lat, lon, cell_x, cell_y
    from {{ ref('int_requests_unified') }}
    where era = 'legacy'
        and created_at >= cast('{{ var("cutover_date") }}' as timestamp)
),

current_cases as (
    select
        unified_category, created_at, lat, lon, cell_x, cell_y,
        {{ epoch_day('created_at') }} as created_day
    from {{ ref('int_requests_unified') }}
    where era = 'current' and lat is not null
),

-- 3x3 neighboring cells, and every day that can hold a case less than 8 days away.
search_keys as (
    select
        l.request_id, l.unified_category, l.created_at, l.lat, l.lon,
        l.cell_x + offsets_x.dx as search_x,
        l.cell_y + offsets_y.dy as search_y,
        {{ epoch_day('l.created_at') }} + offsets_d.dd as search_day
    from legacy_tail as l
    cross join (values (-1), (0), (1)) as offsets_x (dx)
    cross join (values (-1), (0), (1)) as offsets_y (dy)
    cross join (
        values {% for d in range(-9, 10) %}({{ d }}){% if not loop.last %}, {% endif %}{% endfor %}
    ) as offsets_d (dd)
    where l.lat is not null
),

pairs as (
    select
        k.request_id,
        abs({{ hours_between('k.created_at', 'c.created_at') }}) as hours_apart
    from search_keys as k
    inner join current_cases as c
        on c.cell_x = k.search_x
        and c.cell_y = k.search_y
        and c.created_day = k.search_day
        and c.unified_category = k.unified_category
    where {{ distance_m('k.lat', 'k.lon', 'c.lat', 'c.lon') }} <= {{ radius }}
),

matches as (
    select
        request_id,
        max(case when hours_apart <= 24 then 1 else 0 end) = 1 as has_same_day_match,
        max(case when hours_apart >= 168 and hours_apart < 192 then 1 else 0 end) = 1
            as has_placebo_match
    from pairs
    group by request_id
)

select
    l.request_id,
    l.unified_category,
    l.request_type,
    l.channel,
    l.is_crew_self_report,
    l.created_at,
    l.lat is not null as has_coordinates,
    coalesce(m.has_same_day_match, false) as has_same_day_match,
    coalesce(m.has_placebo_match, false) as has_placebo_match
from legacy_tail as l
left join matches as m
    on m.request_id = l.request_id
