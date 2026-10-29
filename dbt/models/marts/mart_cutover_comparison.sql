-- The cutover and the long run (brief Q4 and Q6): one row per month, crosswalked category and
-- era, with behavioral (E2) measures that exist in both systems. Crew self-reports are excluded
-- (Phase 1 sign-off). Cancellation and referral come from the status in both eras, so the two
-- systems are measured the same way. Closure measures are null for volume-only categories. Both
-- eras have rows for Mar-Aug 2025 (is_overlap_month): era is the system of record.
-- "Closed within N days" counts are null for months whose requests couldn't all be followed for
-- `cutover_followup_days` in their own system: the latest months, and legacy months near the
-- cutover (requests still open then never close in the legacy data).
{%- set followup = var('cutover_followup_days') %}

with base as (
    select *
    from {{ ref('fct_service_requests') }}
    where is_crosswalked and not is_crew_self_report
),

coverage as (
    select max(created_at) as data_end
    from {{ ref('fct_service_requests') }}
),

monthly as (
    select
        created_month,
        unified_category,
        era,
        cross_era_comparison,
        count(*) as n_requests,
        sum(case when is_terminal then 1 else 0 end) as n_terminal,
        sum(case when is_closed then 1 else 0 end) as n_closed,
        sum(case when is_closed and hours_to_close <= 7 * 24 then 1 else 0 end)
            as n_closed_within_7d,
        sum(case when is_closed and hours_to_close <= {{ followup }} * 24 then 1 else 0 end)
            as n_closed_within_30d,
        sum(case when status_outcome = 'cancelled' then 1 else 0 end) as n_status_cancelled,
        sum(case when status_outcome = 'referred_out_of_scope' then 1 else 0 end)
            as n_status_referred,
        sum(case when is_instant_close then 1 else 0 end) as n_instant_close,
        -- Time to close covers requests that closed; cancellations end a different way.
        sum(case when is_closed and hours_to_close >= 0 then 1 else 0 end) as n_with_duration,
        percentile_cont(0.5) within group (
            order by case when is_closed and hours_to_close >= 0 then hours_to_close end
        ) as p50_hours_to_close,
        percentile_cont(0.9) within group (
            order by case when is_closed and hours_to_close >= 0 then hours_to_close end
        ) as p90_hours_to_close,
        sum(case when is_closed_before_created then 1 else 0 end) as n_closed_before_created,
        sum(case when is_closed_at_midnight then 1 else 0 end) as n_closed_at_midnight,
        sum(case when is_rereport_eligible then 1 else 0 end) as n_rereport_eligible,
        sum(case when is_rereported_30d then 1 else 0 end) as n_rereported_30d,
        sum(case when has_prior_report_30d then 1 else 0 end) as n_prior_reported_30d
    from base
    group by created_month, unified_category, era, cross_era_comparison
),

flagged as (
    select
        m.*,
        -- Every request in the month could be followed for `cutover_followup_days`.
        {{ dbt.dateadd('day', followup, dbt.dateadd('month', 1, 'm.created_month')) }} <= case
            when m.era = 'legacy' then cast('{{ var("cutover_date") }}' as timestamp)
            else c.data_end
        end as has_full_followup
    from monthly as m
    cross join coverage as c
)

select
    created_month,
    unified_category,
    era,
    cross_era_comparison,
    created_month >= cast('2025-03-01' as date) and created_month < cast('2025-09-01' as date)
        as is_overlap_month,
    has_full_followup,
    n_requests,
    {%- for measure in [
        'n_terminal', 'n_closed', 'n_status_cancelled', 'n_status_referred', 'n_instant_close',
        'n_with_duration', 'p50_hours_to_close', 'p90_hours_to_close', 'n_closed_before_created',
        'n_closed_at_midnight', 'n_rereport_eligible', 'n_rereported_30d', 'n_prior_reported_30d',
    ] %}
    case when cross_era_comparison <> 'volume_only' then {{ measure }} end as {{ measure }},
    {%- endfor %}
    {%- for measure in ['n_closed_within_7d', 'n_closed_within_30d'] %}
    case
        when cross_era_comparison <> 'volume_only' and has_full_followup then {{ measure }}
    end as {{ measure }}
    {%- if not loop.last %},{% endif %}
    {%- endfor %}
from flagged
