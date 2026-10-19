# GitHub Archive Analytics

An end-to-end data engineering project for turning public GitHub event data
into analytics-ready repository and developer insights. The intended pipeline
separates raw ingestion from SQL transformation, applies dbt data-quality
checks, and presents curated results in a React dashboard.

## Project overview

The platform is designed around an ELT workflow: extract hourly JSON archives
from GH Archive, load the source records into PostgreSQL, and transform them
inside the warehouse with dbt.

```text
                         ┌─────────────────────┐
                         │ GH Archive JSON.GZ  │
                         │ hourly public files │
                         └──────────┬──────────┘
                                    │ Extract and load
                                    ▼
                         ┌─────────────────────┐
                         │ Python ingestion    │
                         │ raw JSON → Postgres │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ raw.raw_gh_events   │
                         │ PostgreSQL/Supabase │
                         └──────────┬──────────┘
                                    │
                                    ▼
                 ┌───────────────────────────────────┐
                 │ dbt transformation layers         │
                 │                                   │
                 │  staging → intermediate → marts  │
                 └─────────────────┬─────────────────┘
                                   │
                   ┌───────────────┴────────────────┐
                   ▼                                ▼
       ┌────────────────────────┐      ┌──────────────────────────┐
       │ fct_repo_activity      │      │ dim_developer_leaderboard│
       │ incremental, repo/day  │      │ developer-level rankings │
       └────────────┬───────────┘      └─────────────┬────────────┘
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Supabase Data API   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ React + Vite UI     │
                         └─────────────────────┘

 GitHub Actions: push to main / manual dispatch → dbt deps → dbt run → dbt test
```

## Data model

The dbt project follows a three-tier structure:

| Layer | Purpose | Current models |
| --- | --- | --- |
| **Staging** | Select, type, and normalize source records; retain a close relationship to the raw data. | `stg_gh_events`, `stg_gh_pull_requests` |
| **Intermediate** | Express reusable business logic and prepare clean inputs for analytics. | `int_developer_daily_commits`, `int_pr_turnaround` |
| **Marts** | Publish stable analytical outputs for reporting and downstream applications. | `fct_repo_activity`, `dim_developer_leaderboard` |

`fct_repo_activity` is designed at repository/day grain and uses an incremental
materialization with `(repo_name, activity_date)` as its unique key. It reports
event volume, contributor counts, event categories, and last activity.
`dim_developer_leaderboard` summarizes developer activity and assigns a
rank. Together, these provide fact- and dimension-oriented analytical
outputs for repository and contributor reporting.

The dbt tests use `dbt_utils` to validate the composite uniqueness of the
repository fact grain and to check metric constraints. The models also define
not-null and uniqueness checks for key fields.

## Technology

- **Ingestion:** Python, GH Archive hourly JSON.GZ files
- **Warehouse:** PostgreSQL / Supabase
- **Transformations and tests:** dbt Core, `dbt-postgres`, `dbt_utils`
- **Orchestration/CI:** GitHub Actions
- **Dashboard:** React, Vite, Supabase JavaScript client

## Repository layout

```text
.
├── .github/
│   └── workflows/
│       └── dbt_pipeline.yml          # dbt CI workflow
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   │   ├── stg_gh_events.sql
│   │   │   ├── stg_gh_pull_requests.sql
│   │   │   └── _src_gh_archive.yml  # Raw source declaration
│   │   ├── intermediate/
│   │   │   ├── int_developer_daily_commits.sql
│   │   │   └── int_pr_turnaround.sql
│   │   ├── marts/
│   │   │   ├── fct_repo_activity.sql
│   │   │   ├── dim_developer_leaderboard.sql
│   │   │   └── schema.yml            # Model-level data tests
│   │   └── sources.yml
│   ├── dbt_project.yml
│   ├── packages.yml                  # dbt_utils dependency
│   └── profiles.yml
├── etl/
│   ├── config.py                     # Loads database settings
│   ├── db.py                         # PostgreSQL operations
│   ├── ingest.py                     # GH Archive ingestion entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── supabaseClient.js
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Prerequisites

- Python 3.10 or later
- Node.js and npm
- PostgreSQL or Supabase database access
- GitHub repository access to configure Actions secrets

## Setup

### 1. Configure database credentials

Create a private `.env` file in the repository root. The tracked
`dbt_project/.env.example` provides a template:

```dotenv
DB_HOST=your-database-host
DB_NAME=postgres
DB_USER=your-database-user
DB_PASSWORD=your-database-password
DB_PORT=5432
```

Do not commit credentials. The dbt source declaration expects a raw table named
`raw.raw_gh_events` with the event fields referenced by the staging models,
including `id`, `type`, `actor_id`, `actor_login`, `repo_id`, `repo_name`,
`payload`, and `created_at`.

### 2. Ingest GH Archive data

From the repository root, create and activate a Python environment, then
install the ingestion dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pg8000 python-dotenv
```

Run the current ingestion entry point:

```powershell
python -m etl.ingest
```

The script accepts a target date and an optional per-hour event limit:

```powershell
python -m etl.ingest --date 2024-01-15
python -m etl.ingest --date 2024-01-15 --limit 5000
python -m etl.ingest --date 2024-01-15 --force
```

The default date is yesterday in UTC. **Implementation note:** in this
checkout, `etl.ingest` still aggregates events and writes to the legacy
`marts.mart_repo_summary` table; it does not yet load raw JSON records into
`raw.raw_gh_events`. The ingestion target must be aligned with the raw table
contract above before this command can serve as the ELT load step for dbt.

### 3. Install and run dbt

Install the PostgreSQL adapter and dbt packages:

```powershell
python -m pip install dbt-core dbt-postgres
Set-Location dbt_project
dbt deps
dbt debug
```

`profiles.yml` reads `DB_HOST`, `DB_USER`, and `DB_PASSWORD` from the
environment, with `DB_NAME` defaulting to `postgres`. Configure those values
for the shell before running dbt. Build the models and run their tests:

```powershell
dbt run
dbt test
```

The normal `dbt run` uses the fact model's incremental materialization. To
rebuild it from the full source, use:

```powershell
dbt run --full-refresh
```

### 4. Configure and run the React dashboard

Create `frontend/.env` with the Supabase project API URL and publishable/anon
key:

```dotenv
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-publishable-or-anon-key
```

Never place a Supabase service-role key in a `VITE_` variable or frontend
source. The schema must be exposed through the Supabase Data API, and the
dashboard role needs `USAGE` on the schema, `SELECT` on its table, and an
applicable Row Level Security policy if RLS is enabled.

Install dependencies and start the local development server:

```powershell
Set-Location ..\frontend
npm install
npm run dev
```

Create and preview a production build with:

```powershell
npm run build
npm run preview
```

The frontend uses the Supabase Data API directly; it does not require a
separate local application server.

## Continuous integration

The GitHub Actions workflow at `.github/workflows/dbt_pipeline.yml` runs on
pushes to `main` and can also be started manually with `workflow_dispatch`.
It installs dbt, resolves packages, rebuilds the project, and executes dbt
tests.

Configure these repository Actions secrets:

| Secret | Purpose |
| --- | --- |
| `DB_HOST` | PostgreSQL host |
| `DB_USER` | Database user |
| `DB_PASSWORD` | Database password |

The workflow currently connects on port `6543` and uses the `postgres`
database. Ensure those connection details match the target database. Secrets
are provided to the runner through GitHub's encrypted Actions secret store and
must not be committed to the repository.

## Current implementation status

This README documents the intended end-state architecture. The checked-in
components are not yet fully wired to that design: `etl/ingest.py` currently
aggregates events and writes to `marts.mart_repo_summary` rather than loading
raw JSON rows into `raw.raw_gh_events`; the React dashboard currently queries
`mart_repo_summary`; and the GitHub Actions workflow uses
`dbt run --full-refresh` rather than an incremental run. The dbt models declare
the intended raw source and analytical outputs, but end-to-end deployment
requires aligning the ingestion target, database schemas, and frontend table
contract with those models.

## Data handling

GH Archive contains public GitHub event data. Keep database credentials and
Supabase service-role keys out of source control. Use only a Supabase
publishable/anon key in the browser, with database grants and Row Level
Security policies configured for the intended public read access.
