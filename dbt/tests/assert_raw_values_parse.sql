-- Staging parses timestamps with try_ functions; this makes sure nothing non-null fails to
-- parse, so a format change shows up as a failure instead of silently becoming null.
{%- set checks = [] %}
{%- for name in var('legacy_datasets') %}
    {%- for column in ['createddate', 'updateddate', 'closeddate', 'servicedate'] %}
        {%- do checks.append((name, column, 'timestamp')) %}
    {%- endfor %}
{%- endfor %}
{%- for name in var('current_datasets') %}
    {%- for column in ['createddate', 'systemmodstamp', 'closeddate', 'service_date__c'] %}
        {%- do checks.append((name, column, 'timestamp')) %}
    {%- endfor %}
    {%- do checks.append((name, 'date_service_was_rendered', 'date')) %}
{%- endfor %}

{%- for name, column, kind in checks %}
select
    '{{ name }}' as source_table,
    '{{ column }}' as source_column,
    {{ column }} as raw_value,
    count(*) as n_rows
from {{ source('raw', name) }}
where {{ column }} is not null
    and {% if kind == 'date' %}try_cast({{ column }} as date){% else %}{{ parse_socrata_timestamp(column) }}{% endif %} is null
group by {{ column }}
{%- if not loop.last %}
union all
{%- endif %}
{%- endfor %}
