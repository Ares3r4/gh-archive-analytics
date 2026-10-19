"""GH Archive -> raw.raw_gh_events ELT.

Usage:
    python -m etl.ingest                 # yesterday UTC, full day
    python -m etl.ingest --date 2024-01-15
    python -m etl.ingest --date 2024-01-15 --limit 5000
    python -m etl.ingest --date 2024-01-15 --force
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from . import db

log = logging.getLogger("etl.ingest")

GH_ARCHIVE_URL = "https://data.gharchive.org/{y}-{m:02d}-{d:02d}-{h}.json.gz"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://www.gharchive.org/",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
}


def fetch_hour(d: date, hour: int, limit: int | None) -> list[dict]:
    """Download one hourly GH Archive file and return up to `limit` events."""
    url = GH_ARCHIVE_URL.format(y=d.year, m=d.month, d=d.day, h=hour)
    log.info("fetch %s", url)

    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.error("404 NOT FOUND: %s — this hour may not exist", url)
        else:
            log.warning("skip %s: HTTP %s", url, e.code)
        return []
    except Exception as e:
        log.warning("skip %s: %s", url, e)
        return []

    events = []
    with gzip.GzipFile(fileobj=BytesIO(raw)) as gz:
        for line in gz:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
            if limit is not None and len(events) >= limit:
                break
    return events


def insert_raw_events(conn, events: list[dict]) -> int:
    """Insert events directly into the raw layer in one fast bulk query."""
    if not events:
        return 0
        
    # 1. Prepare the rows
    rows = []
    for ev in events:
        actor = ev.get("actor", {})
        repo = ev.get("repo", {})
        
        ts_str = ev.get("created_at")
        created_at = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if ts_str else None
        
        rows.append((
            ev.get("id"),
            ev.get("type"),
            actor.get("id"),
            actor.get("login"),
            repo.get("id"),
            repo.get("name"),
            json.dumps(ev.get("payload", {})),
            created_at
        ))
        
    try:
        # 2. Build the query dynamically
        # We create a string like: (%s, %s, %s, ...), (%s, %s, %s, ...)
        placeholders = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s)"] * len(rows))
        
        insert_sql = f"""
            INSERT INTO raw.raw_gh_events 
            (id, type, actor_id, actor_login, repo_id, repo_name, payload, created_at)
            VALUES {placeholders}
            ON CONFLICT (id) DO NOTHING;
        """
        
        # 3. Flatten the list of tuples into a single tuple of values
        flat_values = [item for row in rows for item in row]
        
        # 4. Execute
        conn.run(insert_sql, *flat_values)
        conn.run("COMMIT")
        return len(rows)
        
    except Exception as e:
        log.error("Bulk insert failed: %s", e)
        conn.run("ROLLBACK")
        return 0
    
def download_and_ingest_day(year: int, month: int, day: int,
                            limit: int | None = None,
                            force: bool = False) -> None:
    d = date(year, month, day)
    conn = db.connect()
    
    try:
        total_events = 0
        for hour in range(24):
            if not force and db.already_done(conn, d, hour):
                log.info("skip %s hour %02d: already success", d, hour)
                continue

            db.mark_started(conn, d, hour)
            conn.run("COMMIT") # commit the 'started' status
            
            try:
                events = fetch_hour(d, hour, limit)
                if not events:
                    db.mark_finished(conn, d, hour, "success", rows=0)
                    conn.run("COMMIT")
                    continue
                    
                log.info("%s %02d: downloaded %d events. Inserting to raw...", d, hour, len(events))
                inserted = insert_raw_events(conn, events)
                total_events += inserted
                
                db.mark_finished(conn, d, hour, "success", rows=inserted)
                conn.run("COMMIT")
                log.info("%s %02d: inserted %d new events.", d, hour, inserted)
                
            except Exception as e:
                db.mark_finished(conn, d, hour, "failed", error=str(e))
                conn.run("COMMIT")
                log.exception("hour %02d failed", hour)
                return

        log.info("Finished ingestion for %s. Total new events: %d", d, total_events)
    finally:
        conn.close()


def _parse_args(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD (default: yesterday UTC)")
    p.add_argument("--limit", type=int, default=None,
                   help="max events per hourly file (default: no limit)")
    p.add_argument("--force", action="store_true",
                   help="re-process hours even if already marked success")
    return p.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)

    if args.date:
        d = date.fromisoformat(args.date)
    else:
        d = (datetime.now(timezone.utc).date() - timedelta(days=1))

    download_and_ingest_day(d.year, d.month, d.day, limit=args.limit, force=args.force)


if __name__ == "__main__":
    main(sys.argv[1:])