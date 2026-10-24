{#- Adapter-specific SQL lives here so the models stay portable (brief section 5.1: "runs on
    DuckDB locally; adapter-swappable to Snowflake"). Each macro has a duckdb__ version and a
    default__ version written for Snowflake. Everything else in the models is plain SQL plus
    dbt's own cross-database macros (dbt.datediff, dbt.date_trunc, ...). -#}

{#- Socrata timestamps arrive as strings in two formats: the bulk export renders
    "MM/DD/YYYY hh:mm:ss AM" and the row API renders ISO 8601. Both are floating local
    (Pacific) time. tests/assert_raw_values_parse.sql checks that nothing non-null fails. -#}
{% macro parse_socrata_timestamp(column) -%}
    {{ return(adapter.dispatch('parse_socrata_timestamp')(column)) }}
{%- endmacro %}

{% macro duckdb__parse_socrata_timestamp(column) -%}
    coalesce(
        try_strptime({{ column }}, '%m/%d/%Y %I:%M:%S %p'),
        try_cast({{ column }} as timestamp)
    )
{%- endmacro %}

{% macro default__parse_socrata_timestamp(column) -%}
    coalesce(
        try_to_timestamp({{ column }}, 'MM/DD/YYYY HH12:MI:SS AM'),
        try_to_timestamp({{ column }})
    )
{%- endmacro %}

{#- Legacy flags are "Y"/"N"; current flags are "true"/"false". Plain SQL, so no dispatch. -#}
{% macro parse_flag(column) -%}
    case upper({{ column }})
        when 'Y' then true
        when 'TRUE' then true
        when 'N' then false
        when 'FALSE' then false
    end
{%- endmacro %}

{#- Great-circle (haversine) distance in meters. Plain SQL in both DuckDB and Snowflake. -#}
{% macro distance_m(lat1, lon1, lat2, lon2) -%}
    2 * 6371008.8 * asin(sqrt(
        power(sin(radians({{ lat2 }} - {{ lat1 }}) / 2), 2)
        + cos(radians({{ lat1 }})) * cos(radians({{ lat2 }}))
        * power(sin(radians({{ lon2 }} - {{ lon1 }}) / 2), 2)
    ))
{%- endmacro %}

{#- Square spatial-hash cells for "within N meters" joins: a point's neighbors within the cell
    size all lie in its own cell or the 8 around it, so a 3x3 equi-join plus an exact distance
    filter finds every pair. Coordinates are scaled at LA's latitude (34.05 N); across the city
    the east-west scale varies by under 0.5%, which the 10% margin in `spatial_cell_m` absorbs. -#}
{% macro spatial_cell_m() -%}
    {{ var('rereport_radius_m') * 1.1 }}
{%- endmacro %}

{% macro spatial_cell_x(lon) -%}
    cast(floor({{ lon }} * 111195.08 * 0.82855 / {{ spatial_cell_m() }}) as bigint)
{%- endmacro %}

{% macro spatial_cell_y(lat) -%}
    cast(floor({{ lat }} * 111195.08 / {{ spatial_cell_m() }}) as bigint)
{%- endmacro %}

{#- Whole days since 1970-01-01, for fixed-width time buckets in window joins. -#}
{% macro epoch_day(ts) -%}
    {{ dbt.datediff("cast('1970-01-01' as timestamp)", ts, 'day') }}
{%- endmacro %}

{#- Hours between two timestamps, to the second. -#}
{% macro hours_between(start_ts, end_ts) -%}
    {{ dbt.datediff(start_ts, end_ts, 'second') }} / 3600.0
{%- endmacro %}
