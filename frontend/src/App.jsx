import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowDownUp,
  ArrowUp,
  ArrowUpRight,
  GitFork,
  GitPullRequest,
  Github,
  Radio,
  Search,
  Users,
  X,
} from "lucide-react";
import { supabase, supabaseConfigError } from "./supabaseClient.js";

const PAGE_SIZE = 1000;
const numberFormat = new Intl.NumberFormat("en-US");
const dateFormat = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});
const sortableColumns = [
  { key: "repo_name", label: "Repository", type: "text" },
  { key: "total_events", label: "Events", type: "number" },
  { key: "unique_contributors", label: "Contributors", type: "number" },
  { key: "push_events", label: "Pushes", type: "number" },
  { key: "pr_events", label: "Pull requests", type: "number" },
  { key: "issue_events", label: "Issues", type: "number" },
  { key: "last_active_at", label: "Last active", type: "date" },
];

function asNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function displayDate(value) {
  if (!value) return "No activity";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "No activity" : dateFormat.format(date);
}

function displayDay(value) {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "long",
        timeZone: "UTC",
      }).format(date);
}

function getErrorMessage(error) {
  if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof error.message === "string"
  ) {
    return error.message;
  }
  return "The repository data could not be loaded.";
}

function SortButton({ column, sort, onSort }) {
  const active = sort.key === column.key;
  const Icon = active ? (sort.direction === "asc" ? ArrowUp : ArrowDown) : ArrowDownUp;

  return (
    <button
      className={`sort-button${active ? " sort-button-active" : ""}`}
      onClick={() => onSort(column)}
      aria-label={`Sort by ${column.label}${active ? `, ${sort.direction === "asc" ? "ascending" : "descending"}` : ""}`}
    >
      {column.label}
      <Icon size={13} aria-hidden="true" />
    </button>
  );
}

function MetricCard({ icon: Icon, label, value, detail, accent }) {
  return (
    <article className={`metric-card metric-card-${accent}`}>
      <div className="metric-card-top">
        <span className="metric-label">{label}</span>
        <span className="metric-icon">
          <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
        </span>
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  );
}

function LoadingRows() {
  return Array.from({ length: 5 }, (_, index) => (
    <tr className="skeleton-row" key={index} aria-hidden="true">
      {sortableColumns.map((column) => (
        <td key={column.key}>
          <span className="skeleton" />
        </td>
      ))}
    </tr>
  ));
}

function App() {
  const [repositories, setRepositories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(supabaseConfigError);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key: "total_events", direction: "desc" });
  const [lastUpdated, setLastUpdated] = useState(null);
  const [activeDay, setActiveDay] = useState(null);
  const [availableDays, setAvailableDays] = useState([]);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return undefined;
    }

    let cancelled = false;

    async function loadAvailableDays() {
      setLoading(true);
      setError(null);

      try {
        const { data: latest, error: latestError } = await supabase
          .from("mart_repo_summary")
          .select("event_date")
          .order("event_date", { ascending: false })
          .limit(1);

        if (latestError) throw latestError;

        const latestDay = latest?.[0]?.event_date ?? null;
        if (!latestDay) {
          if (!cancelled) {
            setRepositories([]);
            setActiveDay(null);
            setAvailableDays([]);
            setLastUpdated(new Date());
            setLoading(false);
          }
          return;
        }

        const days = [];
        const seenDays = new Set();
        for (let from = 0; days.length < 7; from += PAGE_SIZE) {
          const { data, error: daysError } = await supabase
            .from("mart_repo_summary")
            .select("event_date")
            .order("event_date", { ascending: false })
            .range(from, from + PAGE_SIZE - 1);

          if (daysError) throw daysError;

          for (const row of data ?? []) {
            if (row.event_date && !seenDays.has(row.event_date)) {
              seenDays.add(row.event_date);
              days.push(row.event_date);
              if (days.length === 7) break;
            }
          }

          if (!data || data.length < PAGE_SIZE) break;
        }

        if (!cancelled) {
          setAvailableDays(days);
          setActiveDay(latestDay);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(getErrorMessage(loadError));
          setLoading(false);
        }
      }
    }

    loadAvailableDays();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!supabase || !activeDay) return undefined;

    let cancelled = false;

    async function loadDay() {
      setLoading(true);
      setError(null);

      try {
        const allRows = [];
        for (let from = 0; ; from += PAGE_SIZE) {
          const { data, error: queryError } = await supabase
            .from("mart_repo_summary")
            .select(
              "repo_name,total_events,unique_contributors,push_events,pr_events,issue_events,last_active_at",
            )
            .eq("event_date", activeDay)
            .order("total_events", { ascending: false })
            .range(from, from + PAGE_SIZE - 1);

          if (queryError) throw queryError;
          allRows.push(...(data ?? []));
          if (!data || data.length < PAGE_SIZE) break;
        }

        if (!cancelled) {
          setRepositories(allRows);
          setLastUpdated(new Date());
        }
      } catch (loadError) {
        if (!cancelled) setError(getErrorMessage(loadError));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadDay();
    return () => {
      cancelled = true;
    };
  }, [activeDay]);

  const metrics = useMemo(
    () =>
      repositories.reduce(
        (totals, repository) => ({
          events: totals.events + asNumber(repository.total_events),
          contributors:
            totals.contributors + asNumber(repository.unique_contributors),
        }),
        { events: 0, contributors: 0 },
      ),
    [repositories],
  );

  const visibleRepositories = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const filtered = repositories.filter((repository) =>
      String(repository.repo_name ?? "").toLocaleLowerCase().includes(query),
    );
    const column = sortableColumns.find(({ key }) => key === sort.key);
    const direction = sort.direction === "asc" ? 1 : -1;

    return [...filtered].sort((left, right) => {
      const leftValue = left[sort.key];
      const rightValue = right[sort.key];
      let comparison = 0;

      if (column?.type === "number") {
        comparison = asNumber(leftValue) - asNumber(rightValue);
      } else if (column?.type === "date") {
        comparison =
          new Date(leftValue ?? 0).getTime() - new Date(rightValue ?? 0).getTime();
      } else {
        comparison = String(leftValue ?? "").localeCompare(String(rightValue ?? ""));
      }
      return comparison * direction;
    });
  }, [repositories, search, sort]);

  function handleSort(column) {
    setSort((current) => ({
      key: column.key,
      direction:
        current.key === column.key && current.direction === "desc" ? "asc" : "desc",
    }));
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="GitHub Archive Analytics home">
          <span className="brand-mark">
            <Github size={21} aria-hidden="true" />
          </span>
          <span className="brand-name">gh<span>archive</span></span>
          <span className="brand-divider" />
          <span className="brand-product">Analytics</span>
        </a>
        <div className="topbar-right">
          <span className="live-indicator"><i /> Activity dashboard</span>
          <span className="avatar">GH</span>
        </div>
      </header>

      <section className="dashboard">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span /> OPEN SOURCE PULSE</div>
            <h1>Activity overview</h1>
            <p className="page-subtitle">
              A snapshot of the projects moving open source forward
              {activeDay ? ` on ${displayDay(activeDay)}` : ""}.
            </p>
          </div>
          <div className="updated-chip">
            <Radio size={14} aria-hidden="true" />
            {loading
              ? "Syncing data"
              : lastUpdated
                ? `Updated ${lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : "Waiting for data"}
          </div>
        </div>

        {availableDays.length > 1 && (
          <div className="day-picker" role="group" aria-label="Select activity day">
            {availableDays.slice(0, 7).map((day) => (
              <button
                key={day}
                type="button"
                className={`day-chip${day === activeDay ? " day-chip-active" : ""}`}
                onClick={() => setActiveDay(day)}
                disabled={loading}
                aria-pressed={day === activeDay}
              >
                {displayDay(day)}
              </button>
            ))}
          </div>
        )}

        <section className="metrics-grid" aria-label="Activity summary">
          <MetricCard
            icon={Activity}
            label="Total events tracked"
            value={loading || error ? "—" : numberFormat.format(metrics.events)}
            detail="Across repositories on the selected day"
            accent="violet"
          />
          <MetricCard
            icon={GitFork}
            label="Active repositories"
            value={loading || error ? "—" : numberFormat.format(repositories.length)}
            detail="Repositories in the activity mart"
            accent="blue"
          />
          <MetricCard
            icon={Users}
            label="Unique contributors"
            value={loading || error ? "—" : numberFormat.format(metrics.contributors)}
            detail="Hourly counts are summed; contributors may overlap"
            accent="green"
          />
        </section>

        <section className="repositories-panel" aria-labelledby="repositories-title">
          <div className="panel-heading">
            <div className="panel-title-group">
              <span className="panel-icon"><GitPullRequest size={17} aria-hidden="true" /></span>
              <div>
                <h2 id="repositories-title">Repository leaderboard</h2>
                <p>Explore activity across your GitHub ecosystem</p>
              </div>
            </div>
            <label className="search-box">
              <Search size={16} aria-hidden="true" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search repositories..."
                aria-label="Search repositories"
              />
              {search && (
                <button
                  className="clear-search"
                  onClick={() => setSearch("")}
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </label>
          </div>

          {error ? (
            <div className="state-message error-state" role="alert">
              <span className="state-icon"><Activity size={20} /></span>
              <h3>Couldn’t load repository activity</h3>
              <p>{error}</p>
              {!supabaseConfigError && (
                <p className="error-hint">
                  Confirm <code>marts</code> is an exposed schema in Supabase and that
                  the anon role has SELECT access to <code>mart_repo_summary</code>.
                </p>
              )}
            </div>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {sortableColumns.map((column) => (
                      <th key={column.key} scope="col">
                        <SortButton column={column} sort={sort} onSort={handleSort} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <LoadingRows />
                  ) : visibleRepositories.length ? (
                    visibleRepositories.map((repository, index) => (
                      <tr key={`${repository.repo_name ?? "unknown"}-${index}`}>
                        <td>
                          <div className="repo-cell">
                            <span className={`repo-rank${index < 3 && !search ? " repo-rank-top" : ""}`}>
                              {String(index + 1).padStart(2, "0")}
                            </span>
                            <span className="repo-symbol"><Github size={16} /></span>
                            <span className="repo-name" title={repository.repo_name}>
                              {repository.repo_name || "Unknown repository"}
                            </span>
                            <ArrowUpRight className="repo-link-icon" size={14} aria-hidden="true" />
                          </div>
                        </td>
                        <td className="number-cell event-value">
                          {numberFormat.format(asNumber(repository.total_events))}
                        </td>
                        <td className="number-cell">
                          {numberFormat.format(asNumber(repository.unique_contributors))}
                        </td>
                        <td className="number-cell"><span className="event-dot push-dot" />{numberFormat.format(asNumber(repository.push_events))}</td>
                        <td className="number-cell"><span className="event-dot pr-dot" />{numberFormat.format(asNumber(repository.pr_events))}</td>
                        <td className="number-cell"><span className="event-dot issue-dot" />{numberFormat.format(asNumber(repository.issue_events))}</td>
                        <td className="date-cell">{displayDate(repository.last_active_at)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="empty-cell" colSpan={sortableColumns.length}>
                        <div className="empty-state">
                          <Search size={22} />
                          <strong>{search ? "No matching repositories" : "No repository data yet"}</strong>
                          <span>
                            {search
                              ? "Try another name or clear your search."
                              : "Your mart is reachable, but it returned no rows."}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {!error && !loading && (
            <div className="panel-footer">
              <span>
                Showing <strong>{numberFormat.format(visibleRepositories.length)}</strong>
                {search ? " matching" : ""} of{" "}
                <strong>{numberFormat.format(repositories.length)}</strong> repositories
              </span>
              <span className="footer-status"><i /> All systems operational</span>
            </div>
          )}
        </section>

        <footer className="dashboard-footer">
          <span>Built for the open-source community</span>
          <span>Powered by Supabase <span className="footer-separator">·</span> GitHub Archive</span>
        </footer>
      </section>
    </main>
  );
}

export default App;