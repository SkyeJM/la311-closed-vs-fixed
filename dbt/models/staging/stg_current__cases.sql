-- One row per case in the new MyLA311 system (from 2025-03-28), typed from the raw strings.
-- Each dataset is a full pull plus incremental deltas, so a case can appear several times: keep
-- its latest version (newest systemmodstamp, then newest pull). Address fields are never
-- selected (brief section 10).

with source as (
    {%- for name in var('current_datasets') %}
    select * from {{ source('raw', name) }}
    {%- if not loop.last %}
    union all by name  -- by name: delta files carry extra Socrata system columns
    {%- endif %}
    {%- endfor %}
),

typed as (
    select
        'current:' || casenumber as request_id,
        casenumber as source_request_id,
        _dataset_id as source_dataset_id,
        {{ parse_socrata_timestamp('createddate') }} as created_at,
        {{ parse_socrata_timestamp('systemmodstamp') }} as updated_at,
        {{ parse_socrata_timestamp('closeddate') }} as closed_at,
        {{ parse_socrata_timestamp('service_date__c') }} as service_date,
        try_cast(date_service_was_rendered as date) as service_rendered_on,
        status,
        type as request_type,
        department_name__c as department,
        assigned_to__c as assigned_to,
        origin as channel,
        created_by_user_organization as created_by_org,
        action_taken__c as call_action,
        resolution_code__c as resolution_code,
        reason_code__c as reason_code,
        {{ parse_flag('reported_anonymously__c') }} as is_anonymous,
        try_cast(geolocation__latitude__s as double) as raw_lat,
        try_cast(geolocation__longitude__s as double) as raw_lon,
        -- ZIP+4 without a dash appears a few times; keep the 5-digit ZIP.
        case
            when length(zipcode__c) in (5, 9) and try_cast(zipcode__c as bigint) is not null
                then left(zipcode__c, 5)
        end as zip,
        nullif(try_cast(locator_council_district as integer), 0) as cd,
        locator_sr_council_district as cd_member,  -- sic: the "district" field holds the name
        nullif(try_cast(locator_sr_neigborhood_council as integer), 0) as nc_code,  -- sic
        case
            when try_cast(locator_sr_neigborhood_council as integer) <> 0
                then locator_sr_neigborhood_council_1
        end as nc_name,
        locator_sr_area_planning as apc,
        locator_sr_community_police as police_area,
        _pull_method as pull_method,
        _pulled_at as pulled_at
    from source
),

latest as (
    select *
    from typed
    qualify row_number() over (
        partition by source_dataset_id, source_request_id
        order by updated_at desc nulls last, pulled_at desc
    ) = 1
)

select
    * exclude (raw_lat, raw_lon),
    -- About 2,200 cases geocode outside the city (some to other continents): keep them out of
    -- spatial joins.
    case when raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0 then raw_lat end
        as lat,
    case when raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0 then raw_lon end
        as lon,
    raw_lat is not null and not (raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0)
        as has_out_of_area_coordinates
from latest
