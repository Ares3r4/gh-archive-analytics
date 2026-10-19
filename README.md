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

- **ETL:** Downloads GH Archive JSON files, aggregates events by repository,
  and upserts counts into `marts.mart_repo_summary`.
- **Dashboard:** The Vite/React frontend queries that table directly through
  Supabase's REST API. It does not require a local Python API/backend server.
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
| `repo_name` | Repository name; unique key for upserts |
| `total_events` | Total events seen |
| `unique_contributors` | Distinct actors counted for an ingested hour |
| `push_events` | Push events |
| `pr_events` | Pull request events |
| `issue_events` | Issue events |
| `last_active_at` | Latest event timestamp seen for the repository |

If the table or permissions are missing, the dashboard will show a load error.

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

By default, this targets **yesterday in UTC** and processes at most 5,000
events from each hourly GH Archive file. To ingest a different date or change
the per-hour limit, call `download_and_ingest_day(year, month, day, limit=...)`
from `etl.ingest`; use `limit=None` to process each available hour in full.

The database table must exist before running the script. The ETL expects
`marts.mart_repo_summary` to have the columns listed above and a unique
constraint or primary key on `repo_name`.

### Important: repeated runs add counts

The ETL uses an upsert. For an existing repository, it **adds** the newly
processed event counts to the stored totals and keeps the later
`last_active_at`. It does not delete old rows or replace a day's previous
counts. Re-ingesting a date that was already loaded will therefore count those
events again. The contributor value is updated using the larger of the stored
count and the count from the current hourly batch; it is not a globally
deduplicated contributor total.

## Repository layout

```text
.
├── etl/
│   ├── config.py                # Loads PostgreSQL settings from .env
│   ├── ingest.py                # Downloads, aggregates, and upserts GH Archive data
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
  permissions on `mart_repo_summary`.
- **Dashboard loads but shows older activity:** The page reads what is already
  stored in the table. Run the ETL for the needed date and check its output for
  unavailable GH Archive hours or database errors.
- **ETL cannot connect:** Check the root `.env` database host, port, username,
  password, database name, and network access.
- **A rerun inflated totals:** The current upsert is additive. It is not
  idempotent for dates already processed.