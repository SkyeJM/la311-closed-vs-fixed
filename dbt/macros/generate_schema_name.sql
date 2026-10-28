{#- Use custom schema names as-is (staging, intermediate, marts, seeds) instead of dbt's default
    "<target schema>_<custom schema>", so the serving export and the AI's table allowlist can name
    `marts` directly. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
