-- Brief section 5.1: closed_at >= created_at, as a warning that counts violations. Nearly all are
-- legacy streetlight closes stamped at midnight (date-only), so they fall up to a day "before"
-- creation; see docs/DATA_NOTES.md.
{{ config(severity = 'warn') }}

select request_id, era, request_type, created_at, closed_at
from {{ ref('int_requests_unified') }}
where closed_at < created_at
