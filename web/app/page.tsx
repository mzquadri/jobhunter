"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Job, SortKey, Stats } from "@/lib/types";
import { FILTERS, Filters, type FilterKey } from "@/components/Filters";
import { JobStrip } from "@/components/JobStrip";
import { Telemetry } from "@/components/Telemetry";
import { EmptyState, SweepPanel, Watchlist } from "@/components/Panels";

const POLL_MS = 60_000;
const SEARCH_DEBOUNCE_MS = 250;

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);

  const [filter, setFilter] = useState<FilterKey>("all");
  const [sort, setSort] = useState<SortKey>("newest");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [cursor, setCursor] = useState(-1);

  const searchRef = useRef<HTMLInputElement>(null);

  // Typing should not fire a request per keystroke.
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [search]);

  const query = useMemo(() => {
    const preset = FILTERS.find((f) => f.key === filter)?.query ?? {};
    return { ...preset, sort, q: debouncedSearch.trim() || undefined, limit: 400 };
  }, [filter, sort, debouncedSearch]);

  const load = useCallback(async () => {
    try {
      const [page, freshStats] = await Promise.all([api.jobs(query), api.stats()]);
      setJobs(page.items);
      setStats(freshStats);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong loading the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  // The collector sweeps on its own schedule, so the page checks back rather
  // than waiting for someone to reload it.
  useEffect(() => {
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const patch = useCallback(async (job: Job, changes: Partial<Job>) => {
    // Optimistic: the round trip is short but the click should feel immediate.
    setJobs((prev) =>
      changes.hidden
        ? prev.filter((j) => j.id !== job.id)
        : prev.map((j) => (j.id === job.id ? { ...j, ...changes } : j)),
    );
    try {
      await api.updateJob(job.id, changes);
    } catch {
      setError("That change did not save. The API may be down.");
      void load();
    }
  }, [load]);

  const sweep = useCallback(async () => {
    setSweeping(true);
    try {
      await api.runSweep();
      // A sweep takes roughly twenty seconds; look again once it should be done.
      setTimeout(() => void load(), 25_000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start a sweep.");
    } finally {
      setTimeout(() => setSweeping(false), 25_000);
    }
  }, [load]);

  // ---- keyboard ----------------------------------------------------------
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const typing = e.target instanceof HTMLElement &&
        ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
      if (typing) {
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const current = jobs[cursor];
      switch (e.key) {
        case "/":
          e.preventDefault();
          searchRef.current?.focus();
          return;
        case "j":
        case "ArrowDown":
          e.preventDefault();
          setCursor((c) => Math.min(c + 1, jobs.length - 1));
          return;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          setCursor((c) => Math.max(c - 1, 0));
          return;
        case "Enter":
          if (current) setExpanded((x) => (x === current.id ? null : current.id));
          return;
        case "o":
          if (current) window.open(current.url, "_blank", "noopener");
          return;
        case "s":
          if (current) void patch(current, { starred: !current.starred });
          return;
        case "x":
          if (current) void patch(current, { hidden: true });
          return;
        case "Escape":
          setExpanded(null);
          setCursor(-1);
          return;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jobs, cursor, patch]);

  useEffect(() => {
    document.querySelector("[data-cursor]")?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  // ---- render ------------------------------------------------------------
  const counts: Partial<Record<FilterKey, number>> = stats
    ? {
        all: stats.total_open,
        fresh: stats.fresh_48h,
        new: stats.new_since_last_sweep,
        dream: stats.dream,
        clean: stats.no_warnings,
        starred: stats.starred,
        applied: stats.applied,
      }
    : {};

  if (error && !stats) {
    return (
      <main className="pt-20">
        <EmptyState
          title="The dashboard cannot reach the API"
          hint={`${error} Start the stack with "docker compose up", then this page will fill itself in.`}
        />
      </main>
    );
  }

  const justPosted = jobs.filter((j) => j.age_days !== null && j.age_days <= 2);
  const earlier = jobs.filter((j) => !(j.age_days !== null && j.age_days <= 2));
  const banded = sort === "newest" && justPosted.length > 0;

  return (
    <main>
      {stats && <Telemetry stats={stats} onSweep={sweep} sweeping={sweeping} />}

      <Filters
        active={filter}
        onFilter={(k) => {
          setFilter(k);
          setCursor(-1);
        }}
        search={search}
        onSearch={setSearch}
        sort={sort}
        onSort={setSort}
        counts={counts}
        searchRef={searchRef}
      />

      {error && stats && (
        <p className="mt-3 border border-warn bg-warn-bg px-3 py-2 text-[13px] text-warn">{error}</p>
      )}

      {loading && jobs.length === 0 ? (
        <p className="py-14 text-center text-ink-2">Loading…</p>
      ) : jobs.length === 0 ? (
        <div className="mt-5">
          <EmptyState
            title="Nothing here yet"
            hint={
              filter === "starred"
                ? "Star a posting with the ☆ button and it will collect here."
                : filter === "fresh"
                  ? "Nothing posted in the last 48 hours. The next sweep runs within the hour."
                  : "Clear the search, or choose All."
            }
          />
        </div>
      ) : banded ? (
        <>
          <Band label="Posted in the last 48 hours" live />
          <Stack jobs={justPosted} offset={0} {...{ expanded, cursor, setExpanded, patch }} />
          {earlier.length > 0 && (
            <>
              <Band label="Earlier, still open" />
              <Stack
                jobs={earlier}
                offset={justPosted.length}
                {...{ expanded, cursor, setExpanded, patch }}
              />
            </>
          )}
        </>
      ) : (
        <div className="mt-5">
          <Stack jobs={jobs} offset={0} {...{ expanded, cursor, setExpanded, patch }} />
        </div>
      )}

      {stats && <Watchlist items={stats.watchlist} />}
      {stats && <SweepPanel sweep={stats.last_sweep} />}

      <footer className="mt-11 max-w-[74ch] border-t border-rule pt-4 text-[12.5px] text-ink-2">
        <Keys /> Strong matches also get a folder under <code>data/drafts/</code> holding a draft
        cover letter, the saved job description and a checklist. Starred, hidden and status live in
        the database, so a sweep never overwrites them. Nothing is ever submitted on your behalf.
      </footer>
    </main>
  );
}

function Band({ label, live }: { label: string; live?: boolean }) {
  return (
    <div
      className={`mt-6 mb-1.5 flex items-center gap-3 text-[12px] ${
        live ? "text-live" : "text-ink-2"
      } after:h-px after:flex-1 after:bg-hair after:content-['']`}
    >
      {label}
    </div>
  );
}

function Stack({
  jobs,
  offset,
  expanded,
  cursor,
  setExpanded,
  patch,
}: {
  jobs: Job[];
  offset: number;
  expanded: string | null;
  cursor: number;
  setExpanded: (id: string | null) => void;
  patch: (job: Job, changes: Partial<Job>) => void;
}) {
  return (
    <div>
      {jobs.map((job, i) => (
        <JobStrip
          key={job.id}
          job={job}
          expanded={expanded === job.id}
          cursored={cursor === offset + i}
          onToggle={() => setExpanded(expanded === job.id ? null : job.id)}
          onPatch={(changes) => patch(job, changes)}
        />
      ))}
    </div>
  );
}

function Keys() {
  const keys = [
    ["/", "search"],
    ["j k", "move"],
    ["Enter", "expand"],
    ["o", "open posting"],
    ["s", "star"],
    ["x", "hide"],
  ];
  return (
    <span className="mb-3 block">
      {keys.map(([key, what], i) => (
        <span key={key}>
          {i > 0 && " · "}
          <kbd className="border border-rule bg-sunk px-1.5 py-px font-mono text-[11.5px]">
            {key}
          </kbd>{" "}
          {what}
        </span>
      ))}
    </span>
  );
}
