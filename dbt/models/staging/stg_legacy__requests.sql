-- One row per legacy MyLA311 service request (Aug 2015 - Nov 2025), typed from the raw strings.
-- Address fields are never selected (brief section 10): coordinates cover every spatial need.
-- The 11 yearly views don't share a request (Profile section 3), so rows are not deduplicated
-- here; the unique test on request_id fails loudly if a year boundary ever overlaps.

with source as (
    {%- for name in var('legacy_datasets') %}
    select * from {{ source('raw', name) }}
    {%- if not loop.last %}
    union all by name  -- by name: five views lack createdbyuserorganization
    {%- endif %}
    {%- endfor %}
),

typed as (
    select
        'legacy:' || srnumber as request_id,
        srnumber as source_request_id,
        _dataset_id as source_dataset_id,
        {{ parse_socrata_timestamp('createddate') }} as created_at,
        {{ parse_socrata_timestamp('updateddate') }} as updated_at,
        {{ parse_socrata_timestamp('closeddate') }} as closed_at,
        {{ parse_socrata_timestamp('servicedate') }} as service_date,
        status,
        requesttype as request_type,
        owner as department,
        assignto as assigned_to,
        requestsource as channel,
        createdbyuserorganization as created_by_org,
        actiontaken as call_action,
        {{ parse_flag('anonymous') }} as is_anonymous,
        try_cast(latitude as double) as raw_lat,
        try_cast(longitude as double) as raw_lon,
        case when length(zipcode) = 5 and try_cast(zipcode as integer) is not null then zipcode end
            as zip,
        nullif(try_cast(cd as integer), 0) as cd,
        cdmember as cd_member,
        nullif(try_cast(nc as integer), 0) as nc_code,
        case when try_cast(nc as integer) <> 0 then ncname end as nc_name,
        apc,
        policeprecinct as police_area,
        addressverified as address_verified,
        {{ parse_flag('approximateaddress') }} as is_approximate_address,
        mobileos as mobile_os,
        _pull_method as pull_method,
        _pulled_at as pulled_at
    from source
)

select
    * exclude (raw_lat, raw_lon),
    -- Coordinates outside a box around the city are geocoding errors: keep them out of spatial
    -- joins (none in the legacy era today; the same rule applies to the current era).
    case when raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0 then raw_lat end
        as lat,
    case when raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0 then raw_lon end
        as lon,
    raw_lat is not null and not (raw_lat between 33.6 and 34.4 and raw_lon between -118.8 and -118.0)
        as has_out_of_area_coordinates
from typed
