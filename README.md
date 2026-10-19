# GitHub Archive Analytics

A small analytics project for collecting public GitHub event data from
[GH Archive](https://www.gharchive.org/), aggregating it in PostgreSQL, and
viewing repository activity in a React dashboard.

## How it works

```text
GH Archive hourly files
        |
        v
Python ETL (etl/ingest.py) ---> PostgreSQL / Supabase
                                      ^
                                      |
                              React dashboard
```

- **ETL:** Downloads GH Archive JSON files, aggregates events by repository and
  event date, and refreshes that date's rows in `marts.mart_repo_summary`.
- **Dashboard:** The Vite/React frontend queries that table directly through
  Supabase's REST API. It shows the latest available day and lets you switch
  among up to seven recent available days. It does not require a local Python
  API/backend server.
- **dbt:** `dbt_project/` contains a project configuration and model-file
  placeholders. The current ETL and dashboard use `marts.mart_repo_summary`
  directly; they do not run dbt as part of loading or displaying data.

## Requirements

- Node.js and npm
- Python 3.10 or later
- A PostgreSQL database reachable by the ETL (for example, a Supabase project)
- GH Archive data is fetched from the internet when the ETL runs

## Run the dashboard

1. Open a terminal in the `frontend/` directory and install the JavaScript
   dependencies:

   ```powershell
   cd frontend
   npm install
   ```

2. Create `frontend/.env` with your Supabase project URL and **publishable/anon**
   key:

   ```dotenv
   VITE_SUPABASE_URL=https://your-project.supabase.co
   VITE_SUPABASE_ANON_KEY=your-supabase-publishable-or-anon-key
   ```

   These values are read by Vite when it starts. Restart the dev server after
   changing them. Never put a Supabase service-role key in a `VITE_` variable
   or in frontend code.

3. Start the frontend:

   ```powershell
   npm run dev
   ```

   Open the local URL printed by Vite. The dashboard fetches rows directly from
   Supabase; the data must already exist in the database.

To create a production build, run `npm run build` from `frontend/`. To serve the
build locally for a preview, run `npm run preview`.

### Supabase access required by the dashboard

The frontend uses the `marts` schema and reads the
`marts.mart_repo_summary` table. The schema must be exposed through the
Supabase Data API, and the role associated with the publishable/anon key needs
`SELECT` access. The expected columns are:

| Column | Purpose |
| --- | --- |
| `repo_name` | Repository name; unique together with `event_date` |
| `event_date` | UTC date for this repository activity row |
| `total_events` | Total events seen for this repository on this date |
| `unique_contributors` | Sum of hourly distinct-actor counts for this repository and date |
| `push_events` | Push events |
| `pr_events` | Pull request events |
| `issue_events` | Issue events |
| `last_active_at` | Latest event timestamp seen for the repository on this date |

If the table, permissions, or browser connection are unavailable, the dashboard
will show a load error. If Row Level Security (RLS) is enabled, add a `SELECT`
policy for the `anon` role (or the role used by the publishable key) as well as
granting table-level `SELECT`.

## Configure and run the ETL

The ETL writes to PostgreSQL directly; it is a batch script, not a server.
From the repository root, install its Python dependencies:

```powershell
python -m pip install requests pg8000 python-dotenv
```

Create a root-level `.env` file with database connection settings:

```dotenv
DB_HOST=your-database-host
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-database-password
DB_PORT=5432
```

`DB_NAME` and `DB_PORT` default to `postgres` and `5432`. Set `DB_HOST`,
`DB_USER`, and `DB_PASSWORD` to match your database. Keep this file private;
do not commit database credentials.

Run the default ingestion job from the repository root:

```powershell
python -m etl.ingest
```

By default, this targets **yesterday in UTC** and processes each available
hourly GH Archive file in full. To limit the number of events per hourly file,
use `--limit 5000` or pass a limit to
`download_and_ingest_day(year, month, day, limit=...)`.

The database table must exist before running the script. The ETL expects
`marts.mart_repo_summary` to have the columns listed above and a unique
constraint or primary key on `(repo_name, event_date)`.

### Refreshing an ingested date

The ETL replaces all mart rows for a date after processing its hourly files.
Use `--force` to reprocess a date whose hours are already marked successful.
Contributor counts are summed from hourly distinct-actor counts, so they are
not globally deduplicated across hours or repositories.

## Repository layout

```text
.
├── etl/
│   ├── config.py                # Loads PostgreSQL settings from .env
│   ├── ingest.py                # Downloads and refreshes daily GH Archive summaries
│   └── query_marts.py           # Small command-line query example
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Repository activity dashboard
│   │   └── supabaseClient.js    # Supabase browser client
│   └── package.json
└── dbt_project/                 # dbt project configuration and model files
```

## Troubleshooting

- **Dashboard reports a Supabase error:** Check the `frontend/.env` values,
  restart Vite, expose the `marts` schema in Supabase, and verify `SELECT`
  permissions and an applicable RLS `SELECT` policy on `mart_repo_summary`.
- **Dashboard reports `TypeError: Failed to fetch`:** Confirm that
  `VITE_SUPABASE_URL` is the project's API URL (`https://<project-ref>.supabase.co`)
  and that the publishable/anon key belongs to the same project. Restart Vite
  after changing `frontend/.env`. Also check that the Supabase project is
  available and that the browser or network is not blocking requests to it.
  SQL permission checks do not verify that the browser can reach the API.
- **Dashboard reports duplicate React keys:** Check for duplicate repository
  rows for the same date. The mart should have a unique constraint or primary
  key on `(repo_name, event_date)`; the ETL writes one summary row per
  repository per date.
- **Dashboard loads but shows older activity:** The page reads what is already
  stored in the table. Run the ETL for the needed date and check its output for
  unavailable GH Archive hours or database errors.
- **ETL cannot connect:** Check the root `.env` database host, port, username,
  password, database name, and network access.
- **A completed date has no rows after a rerun:** The ETL skips hours already
  marked successful unless `--force` is used. Re-run that date with `--force`
  so its daily summary is rebuilt from the archived files.