{{ config(materialized='view') }}

with pushes as (
    select
        actor_id,
        actor_login,
        repo_id,
        repo_name,
        created_at::date as commit_date
    from {{ ref('stg_gh_events') }}
    where event_type = 'PushEvent'
)

select
    actor_id,
    actor_login,
    commit_date,
    count(*) as total_pushes,
    count(distinct repo_id) as distinct_repos_pushed
from pushes
group by 1, 2, 3