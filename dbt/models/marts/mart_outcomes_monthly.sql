-- Outcome mix by month (brief Q1): counts of service requests by creation month, era, category,
-- type, department, closed status and closure outcome. Only additive counts and sums are stored, so any rate
-- (metrics.yml, Phase 3) can be computed at any roll-up of these dimensions. A terminal row with
-- a null closure_outcome is a code the map doesn't know yet.

select
    created_month,
    era,
    unified_category,
    request_type,
    department,
    is_crew_self_report,
    is_terminal,
    is_closed,
    closure_outcome,
    outcome_group,
    count(*) as n_requests,
    sum(case when is_instant_close then 1 else 0 end) as n_instant_close,
    sum(case when hours_to_close >= 0 then 1 else 0 end) as n_with_duration,
    sum(case when hours_to_close >= 0 then hours_to_close end) as sum_hours_to_close,
    sum(case when is_closed_before_created then 1 else 0 end) as n_closed_before_created,
    sum(case when is_rereport_eligible then 1 else 0 end) as n_rereport_eligible,
    sum(case when is_rereported_30d then 1 else 0 end) as n_rereported_30d,
    sum(case when has_prior_report_30d then 1 else 0 end) as n_prior_reported_30d
from {{ ref('fct_service_requests') }}
group by
    created_month, era, unified_category, request_type, department, is_crew_self_report,
    is_terminal, is_closed, closure_outcome, outcome_group
