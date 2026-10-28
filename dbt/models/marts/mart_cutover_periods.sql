-- The cutover in one table (brief Q4): crosswalked categories, crew self-reports excluded, in two
-- periods of equal length.
--   * "before" (legacy): `cutover_compare_months`, ending `cutover_followup_days` before the new
--     system launched. Requests still open at the cutover never close in the legacy data, so
--     ending early gives every request in the period the same follow-up.
--   * "after" (new system): the same span, starting when the Apr-Aug 2025 overlap ended. Leaving
--     the overlap out keeps the legacy tail and the new system's first months, both unusual, out.
-- Whole years balance the seasons. "Closed within N days" is the fair time-to-close comparison:
-- the percentiles only see requests that closed, and slow categories (streetlights) have many
-- that hadn't. Percentiles live here because they can't be re-aggregated from monthly rows.
-- Closure measures are null for volume-only categories.
{%- set months = var('cutover_compare_months') %}
{%- set followup = var('cutover_followup_days') %}
{%- set cutover = "cast('" ~ var('cutover_date') ~ "' as timestamp)" %}
{%- set before_end = dbt.dateadd('day', -followup, cutover) %}
{%- set overlap_end = "cast('" ~ var('overlap_end_date') ~ "' as timestamp)" %}

with base as (
    select
        *,
        case
            when era = 'legacy'
                and created_at >= {{ dbt.dateadd('month', -months, before_end) }}
                and created_at < {{ before_end }}
                then 'before'
            when era = 'current'
                and created_at >= {{ overlap_end }}
                and created_at < {{ dbt.dateadd('month', months, overlap_end) }}
                then 'after'
        end as period
    from {{ ref('fct_service_requests') }}
    where is_crosswalked and not is_crew_self_report
),

periods as (
    select
        unified_category,
        era,
        period,
        cross_era_comparison,
        min(created_month) as first_month,
        max(created_month) as last_month,
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
        sum(case when is_closed_at_midnight then 1 else 0 end) as n_closed_at_midnight,
        sum(case when is_rereport_eligible then 1 else 0 end) as n_rereport_eligible,
        sum(case when is_rereported_30d then 1 else 0 end) as n_rereported_30d,
        sum(case when has_prior_report_30d then 1 else 0 end) as n_prior_reported_30d
    from base
    where period is not null
    group by unified_category, era, period, cross_era_comparison
)

select
    unified_category,
    era,
    period,
    cross_era_comparison,
    first_month,
    last_month,
    n_requests,
    {%- for measure in [
        'n_terminal', 'n_closed', 'n_closed_within_7d', 'n_closed_within_30d',
        'n_status_cancelled', 'n_status_referred', 'n_instant_close', 'n_with_duration',
        'p50_hours_to_close', 'p90_hours_to_close', 'n_closed_at_midnight', 'n_rereport_eligible',
        'n_rereported_30d', 'n_prior_reported_30d',
    ] %}
    case when cross_era_comparison <> 'volume_only' then {{ measure }} end as {{ measure }}
    {%- if not loop.last %},{% endif %}
    {%- endfor %}
from periods
