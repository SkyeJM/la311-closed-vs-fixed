-- A status that status_map doesn't list (such as a new one the City adds) fails the build:
-- whether it is terminal is a decision, not a default.

select era, status, count(*) as n_requests
from {{ ref('int_requests_unified') }}
where is_terminal is null
group by era, status
