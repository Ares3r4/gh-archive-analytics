{{ config(materialized='view') }}

with source as (
    select * from {{ ref('stg_gh_events') }}
    where event_type in ('PullRequestEvent', 'PullRequestReviewEvent')
)

select
    event_id,
    event_type,
    actor_id,
    actor_login,
    repo_id,
    repo_name,
    created_at,
    (payload->'pull_request'->>'number')::integer as pr_number,
    payload->'pull_request'->>'state' as pr_state,
    payload->'pull_request'->>'title' as pr_title
from source