import pg8000

if __package__:
    from .config import DB_CONFIG
else:
    from config import DB_CONFIG


def fetch_repo_summary(limit: int = 10):
    print(f"Connecting to the database to fetch top {limit} repositories from marts...")

    conn = pg8000.connect(
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        database=DB_CONFIG["dbname"],
        port=int(DB_CONFIG["port"]),
    )

    query = """
        SELECT repo_name, total_events, unique_contributors, push_events, pr_events, issue_events, last_active_at
        FROM marts.mart_repo_summary
        LIMIT %s;
    """

    try:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            rows = cur.fetchall()

            print("\n" + "=" * 115)
            print(f"{'Repository Name':<45} | {'Total':<7} | {'Contributors':<12} | {'Pushes':<8} | {'PRs':<6} | {'Issues':<6}")
            print("=" * 115)

            for row in rows:
                repo_name, total, contributors, pushes, prs, issues, last_active = row
                print(f"{repo_name:<45} | {total:<7} | {contributors:<12} | {pushes:<8} | {prs:<6} | {issues:<6}")

            print("=" * 115 + "\n")

    except Exception as e:
        print(f"❌ Error querying analytics mart: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    fetch_repo_summary(10)
