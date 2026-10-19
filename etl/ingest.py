"""GH Archive -> marts.mart_repo_summary ETL.

Usage:
    python -m etl.ingest                 # yesterday UTC, full day
    python -m etl.ingest --date 2024-01-15
    python -m etl.ingest --date 2024-01-15 --limit 5000
    python -m etl.ingest --date 2024-01-15 --force   # ignore skip-guard
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


# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------

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
            log.error("404 NOT FOUND: %s — this hour may not exist in the archive", url)
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


def event_date(event: dict) -> date:
    ts = event["created_at"]                     # "2024-01-15T03:00:00Z"
    return datetime.fromisoformat(ts.replace("Z", "+00:00")) \
                   .astimezone(timezone.utc).date()


# ---------------------------------------------------------------------------
# Aggregate a batch of events into per-repo rows for a given day
# ---------------------------------------------------------------------------

def aggregate(events: list[dict], day: date) -> list[dict]:
    """Bucket events by repo, computing the mart columns. Drops rows whose
    own created_at isn't on `day` (late arrivals across midnight boundaries)."""
    buckets: dict[str, dict] = {}

    for ev in events:
        if event_date(ev) != day:
            continue
        repo = ev.get("repo", {}).get("name")
        if not repo:
            continue

        b = buckets.setdefault(repo, {
            "repo_name": repo,
            "total_events": 0,
            "actors": set(),
            "push_events": 0,
            "pr_events": 0,
            "issue_events": 0,
            "last_active_at": None,
        })

        b["total_events"] += 1
        actor = ev.get("actor", {}).get("login")
        if actor:
            b["actors"].add(actor)

        etype = ev.get("type", "")
        if etype == "PushEvent":
            b["push_events"] += 1
        elif etype in ("PullRequestEvent", "PullRequestReviewEvent"):
            b["pr_events"] += 1
        elif etype in ("IssuesEvent", "IssueCommentEvent"):
            b["issue_events"] += 1

        ts = ev.get("created_at")
        if ts and (b["last_active_at"] is None or ts > b["last_active_at"]):
            b["last_active_at"] = ts

    rows = []
    for b in buckets.values():
        b["unique_contributors"] = len(b.pop("actors"))
        rows.append(b)
    return rows


# ---------------------------------------------------------------------------
# Day orchestration
# ---------------------------------------------------------------------------

def download_and_ingest_day(year: int, month: int, day: int,
                            limit: int | None = None,
                            force: bool = False) -> None:
    d = date(year, month, day)
    conn = db.connect()
    try:
        all_rows: list[dict] = []

        for hour in range(24):
            if not force and db.already_done(conn, d, hour):
                log.info("skip %s hour %02d: already success", d, hour)
                continue

            db.mark_started(conn, d, hour)
            try:
                events = fetch_hour(d, hour, limit)
                hour_rows = aggregate(events, d)
                all_rows.extend(hour_rows)
                db.mark_finished(conn, d, hour, "success", rows=len(events))
                log.info("%s %02d: %d events, %d repos",
                         d, hour, len(events), len(hour_rows))
            except Exception as e:
                db.mark_finished(conn, d, hour, "failed", error=str(e))
                log.exception("hour %02d failed", hour)
                # Do not refresh the mart on a partial day.
                return

        if not db.day_is_complete(conn, d):
            log.warning("%s not complete; mart left untouched", d)
            return

        # Merge per-hour repo rows into one per-repo row for the day.
        merged = _merge_hourly_rows(all_rows)
        db.refresh_day(conn, d, merged)
        log.info("refreshed mart for %s (%d repos)", d, len(merged))
    finally:
        conn.close()


def _merge_hourly_rows(rows: list[dict]) -> list[dict]:
    """Sum counters and take max last_active_at across hourly buckets."""
    by_repo: dict[str, dict] = {}
    for r in rows:
        m = by_repo.get(r["repo_name"])
        if m is None:
            by_repo[r["repo_name"]] = dict(r)
            continue
        m["total_events"] += r["total_events"]
        # NOTE: unique_contributors across hours is NOT a true distinct count.
        # It's the sum of per-hour distinct counts (an upper bound). Acceptable
        # for a dashboard; a true count needs a separate actor table.
        m["unique_contributors"] += r["unique_contributors"]
        m["push_events"] += r["push_events"]
        m["pr_events"] += r["pr_events"]
        m["issue_events"] += r["issue_events"]
        if (r["last_active_at"] or "") > (m["last_active_at"] or ""):
            m["last_active_at"] = r["last_active_at"]
    return list(by_repo.values())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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