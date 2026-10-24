-- Brief section 5.1: row counts reconcile to the ingestion manifest. Every dataset in staging
-- holds exactly as many rows as the portal reported right after the latest pull or refresh.
-- A dataset that was pulled but never staged (or the reverse) fails too.

with staged as (
    select source_dataset_id as dataset_id, count(*) as staged_rows
    from {{ ref('stg_legacy__requests') }}
    group by source_dataset_id
    union all
    select source_dataset_id as dataset_id, count(*) as staged_rows
    from {{ ref('stg_current__cases') }}
    group by source_dataset_id
)

select
    coalesce(m.dataset_id, s.dataset_id) as dataset_id,
    m.expected_rows,
    s.staged_rows
from {{ ref('stg_ingest__manifests') }} as m
full outer join staged as s
    on s.dataset_id = m.dataset_id
where m.expected_rows is null
    or s.staged_rows is null
    or m.expected_rows <> s.staged_rows
