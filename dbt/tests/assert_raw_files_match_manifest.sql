-- Every raw file holds the row count ingest recorded for it, and no file is missing or extra.

with recorded as (
    select dataset_id, 'full.parquet' as file_name, "rows" as n_rows
    from {{ source('raw', 'manifests') }}
    union all
    select m.dataset_id, d.delta.file as file_name, d.delta."rows" as n_rows
    from {{ source('raw', 'manifests') }} as m
    cross join unnest(m.deltas) as d (delta)
)

select
    coalesce(r.dataset_id, f.dataset_id) as dataset_id,
    coalesce(r.file_name, f.file_name) as file_name,
    r.n_rows as recorded_rows,
    f.n_rows as rows_on_disk
from recorded as r
full outer join {{ ref('stg_ingest__files') }} as f
    on f.dataset_id = r.dataset_id and f.file_name = r.file_name
where r.n_rows is null
    or f.n_rows is null
    or r.n_rows <> f.n_rows
