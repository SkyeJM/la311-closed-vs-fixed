-- One row per dataset from its ingest manifest. `expected_rows` is the live row count the portal
-- reported right after the latest full pull or refresh: what staging must hold.

select
    dataset_id,
    name as dataset_name,
    era,
    pulled_at as full_pull_at,
    method as full_pull_method,
    "rows" as full_pull_rows,
    live_count_after_pull,
    len(deltas) as n_deltas,
    case when len(deltas) > 0 then deltas[len(deltas)].pulled_at end as last_refresh_at,
    case
        when len(deltas) > 0 then deltas[len(deltas)].live_count_after_refresh
        else live_count_after_pull
    end as expected_rows
from {{ source('raw', 'manifests') }}
