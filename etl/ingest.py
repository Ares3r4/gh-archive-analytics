from collections import defaultdict
import datetime
import gzip
import io
import json
import time
from datetime import timedelta
import pg8000
import requests

if __package__:
    from .config import DB_CONFIG
else:
    from config import DB_CONFIG


def get_db_connection():
    """Creates a fresh, independent connection to prevent stale socket/idle timeouts."""
    return pg8000.connect(
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        database=DB_CONFIG["dbname"],
        port=int(DB_CONFIG["port"]),
    )


def download_and_aggregate_hour(year: int, month: int, day: int, hour: int, limit: int | None = None):
    """Downloads an hour, aggregates metrics in memory, and upserts directly to marts."""
    url = f"https://data.gharchive.org/{year}-{month:02d}-{day:02d}-{hour}.json.gz"
    print(f"\n📥 Downloading & aggregating hour {hour:02d}: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    buffer = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=60)
            if response.status_code == 404:
                print(f"⚠️ Hour {hour:02d} not available yet on GH Archive. Skipping.")
                return
            response.raise_for_status()

            buffer = io.BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    buffer.write(chunk)
            buffer.seek(0)
            break 
        except Exception as e:
            print(f"⚠️ Download/Stream attempt {attempt + 1} failed for hour {hour:02d}: {e}")
            if attempt == 2:
                print(f"❌ Skipping hour {hour:02d} after 3 failed attempts.")
                return
            time.sleep(3)

    if not buffer:
        return

    print(f"🔄 Processing and aggregating hour {hour:02d} in memory...")
    
    # In-memory aggregation dictionary
    # Key: repo_name -> Value: stats dict
    repo_stats = defaultdict(lambda: {
        "total_events": 0,
        "unique_actors": set(),
        "push_events": 0,
        "pr_events": 0,
        "issue_events": 0,
        "last_active_at": None
    })

    try:
        with gzip.GzipFile(fileobj=buffer) as f:
            for i, line in enumerate(f):
                if limit is not None and i >= limit:
                    break
                try:
                    # Sanitize null bytes out of the line string before parsing JSON
                    raw_str = line.decode("utf-8").replace("\x00", "")
                    event = json.loads(raw_str)
                    
                    repo_name = event.get("repo", {}).get("name")
                    if not repo_name:
                        continue
                    
                    stats = repo_stats[repo_name]
                    stats["total_events"] += 1
                    
                    actor_login = event.get("actor", {}).get("login")
                    if actor_login:
                        stats["unique_actors"].add(actor_login)
                    
                    ev_type = event.get("type")
                    if ev_type == "PushEvent":
                        stats["push_events"] += 1
                    elif ev_type == "PullRequestEvent":
                        stats["pr_events"] += 1
                    elif ev_type == "IssuesEvent":
                        stats["issue_events"] += 1
                        
                    created_at = event.get("created_at")
                    if created_at and (not stats["last_active_at"] or created_at > stats["last_active_at"]):
                        stats["last_active_at"] = created_at
                        
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"❌ Failed to parse hour {hour:02d}: {e}")
        return

    if not repo_stats:
        print(f"⚠️ Hour {hour:02d} had no valid repository events.")
        return

    # Persist the aggregated hourly stats straight into the database
    conn = get_db_connection()
    try:
        batch_size = 1000
        items = list(repo_stats.items())
        
        with conn.cursor() as cur:
            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]
                
                placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(batch))
                query = f"""
                    INSERT INTO marts.mart_repo_summary 
                    (repo_name, total_events, unique_contributors, push_events, pr_events, issue_events, last_active_at)
                    VALUES {placeholders}
                    ON CONFLICT (repo_name) DO UPDATE SET
                        total_events = marts.mart_repo_summary.total_events + EXCLUDED.total_events,
                        unique_contributors = GREATEST(marts.mart_repo_summary.unique_contributors, EXCLUDED.unique_contributors),
                        push_events = marts.mart_repo_summary.push_events + EXCLUDED.push_events,
                        pr_events = marts.mart_repo_summary.pr_events + EXCLUDED.pr_events,
                        issue_events = marts.mart_repo_summary.issue_events + EXCLUDED.issue_events,
                        last_active_at = GREATEST(marts.mart_repo_summary.last_active_at, EXCLUDED.last_active_at);
                """
                
                flat_params = []
                for repo_name, stats in batch:
                    flat_params.extend([
                        repo_name,
                        stats["total_events"],
                        len(stats["unique_actors"]),
                        stats["push_events"],
                        stats["pr_events"],
                        stats["issue_events"],
                        stats["last_active_at"]
                    ])
                    
                cur.execute(query, flat_params)
            conn.commit()
            
        print(f"✅ Hour {hour:02d} aggregated & upserted successfully ({len(repo_stats):,} unique repos).")
    except Exception as e:
        conn.rollback()
        print(f"❌ Error inserting aggregated stats for hour {hour:02d}: {e}")
    finally:
        conn.close()


def download_and_ingest_day(year: int, month: int, day: int, limit: int | None = None):
    print(f"🚀 Starting in-memory streaming pipeline for {year}-{month:02d}-{day:02d} (Limit per hour: {limit})...")
    
    for hour in range(24):
        download_and_aggregate_hour(year, month, day, hour, limit=limit)
        
    print(f"🎉 Full-day in-memory pipeline complete for {year}-{month:02d}-{day:02d}!")


if __name__ == "__main__":
    target_date = datetime.datetime.utcnow() - timedelta(days=1)
    download_and_ingest_day(target_date.year, target_date.month, target_date.day, limit=5000)