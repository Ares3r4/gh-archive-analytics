from contextlib import contextmanager
from datetime import date

import pg8000.native  # low-level; we use .run() for parameterized SQL

from .config import DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT


def connect():
    """Open a pg8000 connection. autocommit is OFF by default in pg8000."""
    return pg8000.native.Connection(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        timeout=30,
    )


@contextmanager
def transaction(conn):
    """Commit on success, rollback on any exception."""
    try:
        yield
        conn.run("COMMIT")
    except Exception:
        conn.run("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# ops.ingestion_runs helpers
# ---------------------------------------------------------------------------

def already_done(conn, event_date: date, hour: int) -> bool:
    rows = conn.run(
        "SELECT 1 FROM ops.ingestion_runs "
        "WHERE event_date = :d AND hour = :h AND status = 'success'",
        d=event_date, h=hour,
    )
    return len(rows) > 0


def mark_started(conn, event_date: date, hour: int):
    conn.run(
        "INSERT INTO ops.ingestion_runs (event_date, hour, status) "
        "VALUES (:d, :h, 'started') "
        "ON CONFLICT (event_date, hour) DO UPDATE "
        "SET status = 'started', started_at = now(), finished_at = NULL, "
        "    error = NULL, rows_processed = NULL",
        d=event_date, h=hour,
    )


def mark_finished(conn, event_date: date, hour: int, status: str,
                  rows: int | None = None, error: str | None = None):
    conn.run(
        "UPDATE ops.ingestion_runs "
        "SET status = :s, rows_processed = :r, error = :e, finished_at = now() "
        "WHERE event_date = :d AND hour = :h",
        s=status, r=rows, e=(error[:500] if error else None),
        d=event_date, h=hour,
    )


def day_is_complete(conn, event_date: date) -> bool:
    """True iff all 24 hours for this date are 'success'."""
    rows = conn.run(
        "SELECT count(*) FROM ops.ingestion_runs "
        "WHERE event_date = :d AND status = 'success'",
        d=event_date,
    )
    return rows[0][0] == 24


# ---------------------------------------------------------------------------
# Mart refresh
# ---------------------------------------------------------------------------

def refresh_day(conn, event_date: date, aggregated_rows: list[dict]):
    """Atomically replace all mart rows for event_date.

    aggregated_rows: list of dicts with keys
      repo_name, total_events, unique_contributors,
      push_events, pr_events, issue_events, last_active_at
    """
    with transaction(conn):
        conn.run(
            "DELETE FROM marts.mart_repo_summary WHERE event_date = :d",
            d=event_date,
        )
        if not aggregated_rows:
            return
        for r in aggregated_rows:
            conn.run(
                "INSERT INTO marts.mart_repo_summary "
                "  (repo_name, event_date, total_events, unique_contributors, "
                "   push_events, pr_events, issue_events, last_active_at) "
                "VALUES (:rn, :d, :te, :uc, :pe, :pre, :ie, :la)",
                rn=r["repo_name"], d=event_date,
                te=r["total_events"], uc=r["unique_contributors"],
                pe=r["push_events"], pre=r["pr_events"],
                ie=r["issue_events"], la=r["last_active_at"],
            )