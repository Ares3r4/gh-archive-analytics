{{ config(materialized='view') }}

with prs as (
    select * from {{ ref('stg_gh_pull_requests') }}
    where event_type = 'PullRequestEvent'
)

select
    repo_id,
    repo_name,
    actor_id as author_id,
    actor_login as author_login,
    pr_number,
    min(created_at) as opened_at,
    max(case when pr_state = 'closed' then created_at end) as closed_at,
    extract(epoch from (max(case when pr_state = 'closed' then created_at end) - min(created_at))) / 3600.0 as hours_open
from prs
group by 1, 2, 3, 4, 5