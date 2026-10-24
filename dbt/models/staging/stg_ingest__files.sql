-- One row per raw Parquet file on disk: which dataset it belongs to and how many rows it holds.
-- assert_raw_files_match_manifest compares these with what ingest recorded.

{%- for name in var('legacy_datasets') + var('current_datasets') %}
select
    _dataset_id as dataset_id,
    parse_filename(filename) as file_name,
    count(*) as n_rows
from {{ source('raw', name) }}
group by _dataset_id, parse_filename(filename)
{%- if not loop.last %}
union all
{%- endif %}
{%- endfor %}
