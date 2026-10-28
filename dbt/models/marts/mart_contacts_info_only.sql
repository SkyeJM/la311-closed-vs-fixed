-- Contacts that are not service requests (non_service_types: Information-Only, Feedback,
-- Program Research, current-era Other), kept out of every service denominator (brief section
-- 4.1) and counted here instead.

select
    created_month,
    era,
    request_type,
    channel,
    department,
    resolution_code,
    count(*) as n_contacts,
    sum(case when hours_to_close >= 0 and hours_to_close <= 1 / 60.0 then 1 else 0 end)
        as n_closed_within_60s
from {{ ref('int_requests_unified') }}
where not is_service_request
group by created_month, era, request_type, channel, department, resolution_code
