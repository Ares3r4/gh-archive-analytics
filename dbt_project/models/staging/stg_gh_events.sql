{{ config(materialized='view') }}

with source as (
    select * from {{ source('raw', 'raw_gh_events') }}
),

renamed as (
    select
        id::varchar as event_id,
        type::varchar as event_type,
        actor_id::bigint,
        actor_login::varchar,
        repo_id::bigint,
        repo_name::varchar,
        payload::jsonb,
        created_at::timestamp
    from source
    where id is not null
)

select * from renamed