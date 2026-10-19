{{ config(
    materialized='incremental',
    unique_key=['repo_name', 'activity_date'],
    on_schema_change='sync_all_columns'
) }}

with events as (
    select * from {{ ref('stg_gh_events') }}
    
    {% if is_incremental() %}
    where created_at > (select coalesce(max(last_active_at), '1970-01-01'::timestamp) from {{ this }})
    {% endif %}
)

select
    repo_name,
    created_at::date as activity_date,
    count(*) as total_events,
    count(distinct actor_id) as unique_contributors,
    count(*) filter (where event_type = 'PushEvent') as push_events,
    count(*) filter (where event_type = 'PullRequestEvent') as pr_events,
    count(*) filter (where event_type = 'IssuesEvent') as issue_events,
    max(created_at) as last_active_at
from events
group by 1, 2