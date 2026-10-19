{{ config(materialized='table') }}

with daily_stats as (
    select * from {{ ref('int_developer_daily_commits') }}
),

aggregated as (
    select
        actor_id,
        actor_login,
        sum(total_pushes) as lifetime_pushes,
        count(distinct commit_date) as days_active,
        max(commit_date) as last_push_date
    from daily_stats
    group by 1, 2
)

select
    actor_id,
    actor_login,
    lifetime_pushes,
    days_active,
    last_push_date,
    dense_rank() over (order by lifetime_pushes desc) as activity_rank
from aggregated