"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search, SlidersHorizontal, X } from "lucide-react";
import {
  api,
  ApiError,
  STATUS_LABELS,
  STATUS_ORDER,
  type JobQuery,
  type JobSummary,
  type SavedSearchOut,
} from "@/lib/api";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  Select,
  Separator,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/primitives";
import {
  JobTitleCell,
  SalaryCell,
  Score,
  StarButton,
  StatusBadge,
} from "@/components/jobs/bits";
import { cn, postedAge } from "@/lib/utils";

const SEARCH_DEBOUNCE_MS = 250;
const PAGE_SIZE = 100;

/**
 * The subset of JobPatch the table can change inline.
 *
 * Narrower than JobPatch on purpose: the full patch type allows null on every
 * field (they are all optional server-side), which would widen a JobSummary's
 * non-nullable columns when spread into it optimistically.
 */
type RowPatch = Partial<Pick<JobSummary, "starred" | "hidden" | "status">>;

const LANGUAGES = [
  ["english_only", "English only"],
  ["english_preferred", "English preferred"],
  ["german_optional", "German optional"],
  ["german_a1_a2", "German A1/A2"],
  ["german_b1", "German B1"],
  ["german_b2", "German B2"],
  ["german_c1_plus", "German C1+"],
  ["german_native", "German native"],
  ["unclear", "Not stated"],
] as const;

export function JobExplorer() {
  const params = useSearchParams();

  const [query, setQuery] = useState<JobQuery>(() => ({
    sort: (params.get("sort") as JobQuery["sort"]) ?? "newest",
    only_new: params.get("only_new") === "true" || undefined,
    min_score: params.get("min_score") ? Number(params.get("min_score")) : undefined,
    status: (params.get("status") as JobQuery["status"]) ?? undefined,
    country: (params.get("country") as JobQuery["country"]) ?? undefined,
    limit: PAGE_SIZE,
  }));

  const [text, setText] = useState("");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [searches, setSearches] = useState<SavedSearchOut[]>([]);
  const [activeSearch, setActiveSearch] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // One request per pause in typing, not one per keystroke.
  useEffect(() => {
    const id = setTimeout(
      () => setQuery((q) => ({ ...q, q: text.trim() || undefined })),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(id);
  }, [text]);

  useEffect(() => {
    api.searches().then(setSearches).catch(() => setSearches([]));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = activeSearch
        ? await api.searchResults(activeSearch, PAGE_SIZE)
        : await api.jobs(query);
      setJobs(page.items);
      setTotal(page.total);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load jobs.");
    } finally {
      setLoading(false);
    }
  }, [query, activeSearch]);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = useCallback(
    async (job: JobSummary, changes: RowPatch) => {
      // Optimistic: the round trip is short, but the click should feel instant.
      setJobs((prev) =>
        changes.hidden
          ? prev.filter((j) => j.id !== job.id)
          : prev.map((j) => (j.id === job.id ? { ...j, ...changes } : j)),
      );
      try {
        await api.updateJob(job.id, changes);
      } catch {
        setError("That change did not save.");
        void load();
      }
    },
    [load],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function update<K extends keyof JobQuery>(key: K, value: JobQuery[K]) {
    setActiveSearch(null);
    setQuery((q) => ({ ...q, [key]: value || undefined }));
  }

  const activeFilterCount = useMemo(
    () =>
      Object.entries(query).filter(
        ([k, v]) => !["sort", "limit", "q"].includes(k) && v !== undefined && v !== false,
      ).length,
    [query],
  );

  return (
    <div className="flex flex-col">
      {/* saved searches */}
      {searches.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto border-b border-border px-6 py-2 scrollbar-thin">
          {searches.map((s) => (
            <Button
              key={s.id}
              size="sm"
              variant={activeSearch === s.id ? "default" : "outline"}
              title={s.description}
              onClick={() => {
                setActiveSearch(activeSearch === s.id ? null : s.id);
                setText("");
              }}
            >
              {s.pinned && "★ "}
              {s.name}
            </Button>
          ))}
        </div>
      )}

      {/* controls */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-6 py-3">
        <div className="relative min-w-52 flex-1">
          <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={searchRef}
            value={text}
            onChange={(e) => {
              setActiveSearch(null);
              setText(e.target.value);
            }}
            placeholder="Search company, role, skill or city   (press /)"
            className="pl-8"
            aria-label="Search postings"
          />
        </div>

        <Select
          value={query.sort ?? "newest"}
          onChange={(e) => update("sort", e.target.value as JobQuery["sort"])}
          aria-label="Sort order"
        >
          <option value="newest">Newest posted</option>
          <option value="discovered">Newest discovered</option>
          <option value="score">Best match</option>
          <option value="salary">Highest salary</option>
          <option value="company">Company</option>
        </Select>

        <Button
          variant={showFilters ? "default" : "outline"}
          size="sm"
          onClick={() => setShowFilters((v) => !v)}
        >
          <SlidersHorizontal />
          Filters
          {activeFilterCount > 0 && <Badge variant="info">{activeFilterCount}</Badge>}
        </Button>

        <span className="tabular ml-auto text-xs text-muted-foreground">
          {loading ? "…" : `${total} ${total === 1 ? "posting" : "postings"}`}
        </span>
      </div>

      {showFilters && (
        <FilterBar query={query} onChange={update} onClear={() => setQuery({ sort: query.sort, limit: PAGE_SIZE })} />
      )}

      {error && (
        <p className="border-b border-danger/30 bg-danger-soft px-6 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {/* results */}
      <div className="px-6 py-4">
        {loading && jobs.length === 0 ? (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <EmptyState
            title="Nothing matches"
            hint="Clear the search or widen the filters. The worker sweeps every hour, so new postings appear on their own."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setText("");
                  setActiveSearch(null);
                  setQuery({ sort: "newest", limit: PAGE_SIZE });
                }}
              >
                Reset
              </Button>
            }
          />
        ) : (
          <JobTable jobs={jobs} onPatch={patch} />
        )}
      </div>
    </div>
  );
}

function FilterBar({
  query,
  onChange,
  onClear,
}: {
  query: JobQuery;
  onChange: <K extends keyof JobQuery>(key: K, value: JobQuery[K]) => void;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/30 px-6 py-3">
      <Select
        value={query.country ?? ""}
        onChange={(e) => onChange("country", (e.target.value || undefined) as JobQuery["country"])}
        aria-label="Country"
      >
        <option value="">Any country</option>
        <option value="de">Germany</option>
        <option value="ch">Switzerland</option>
        <option value="at">Austria</option>
        <option value="nl">Netherlands</option>
        <option value="eu">Rest of Europe</option>
      </Select>

      <Select
        value={query.tier ?? ""}
        onChange={(e) => onChange("tier", e.target.value || undefined)}
        aria-label="Employer tier"
      >
        <option value="">Any employer</option>
        <option value="dream">Shortlist only</option>
        <option value="high">High priority</option>
      </Select>

      <Select
        value={query.language ?? ""}
        onChange={(e) => onChange("language", e.target.value || undefined)}
        aria-label="Language requirement"
      >
        <option value="">Any language requirement</option>
        {LANGUAGES.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </Select>

      <Select
        value={query.remote ?? ""}
        onChange={(e) => onChange("remote", e.target.value || undefined)}
        aria-label="Work arrangement"
      >
        <option value="">Any arrangement</option>
        <option value="remote">Remote</option>
        <option value="hybrid">Hybrid</option>
        <option value="onsite">On-site</option>
      </Select>

      <Select
        value={query.status ?? ""}
        onChange={(e) => onChange("status", (e.target.value || undefined) as JobQuery["status"])}
        aria-label="Application status"
      >
        <option value="">Any status</option>
        {STATUS_ORDER.map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </Select>

      <Select
        value={query.min_score?.toString() ?? ""}
        onChange={(e) => onChange("min_score", e.target.value ? Number(e.target.value) : undefined)}
        aria-label="Minimum match"
      >
        <option value="">Any match</option>
        <option value="80">80 and above</option>
        <option value="70">70 and above</option>
        <option value="60">60 and above</option>
      </Select>

      <Select
        value={query.max_age_days?.toString() ?? ""}
        onChange={(e) =>
          onChange("max_age_days", e.target.value ? Number(e.target.value) : undefined)
        }
        aria-label="Posting age"
      >
        <option value="">Any age</option>
        <option value="1">Posted today</option>
        <option value="3">Last 3 days</option>
        <option value="7">Last 7 days</option>
      </Select>

      <label className="flex items-center gap-1.5 text-xs">
        <input
          type="checkbox"
          checked={query.only_clean ?? false}
          onChange={(e) => onChange("only_clean", e.target.checked || undefined)}
        />
        No warnings
      </label>
      <label className="flex items-center gap-1.5 text-xs">
        <input
          type="checkbox"
          checked={query.only_starred ?? false}
          onChange={(e) => onChange("only_starred", e.target.checked || undefined)}
        />
        Starred
      </label>

      <Button variant="ghost" size="sm" onClick={onClear}>
        <X />
        Clear
      </Button>
    </div>
  );
}

function JobTable({
  jobs,
  onPatch,
}: {
  jobs: JobSummary[];
  onPatch: (job: JobSummary, changes: RowPatch) => void;
}) {
  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12 text-right">Match</TableHead>
            <TableHead className="min-w-64">Position</TableHead>
            <TableHead className="min-w-36">Company</TableHead>
            <TableHead className="min-w-32">Location</TableHead>
            <TableHead className="w-28">Language</TableHead>
            <TableHead className="w-24">Salary</TableHead>
            <TableHead className="w-20">Posted</TableHead>
            <TableHead className="w-24">Status</TableHead>
            <TableHead className="w-10" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <TableRow key={job.id}>
              <TableCell className="text-right">
                <Score value={job.score} />
              </TableCell>
              <TableCell>
                <JobTitleCell job={job} />
              </TableCell>
              <TableCell className="text-sm">{job.company_name}</TableCell>
              <TableCell className="text-xs text-muted-foreground">
                <span className="block truncate">
                  {job.city || job.location_raw || "—"}
                </span>
                {job.remote_policy !== "unknown" && (
                  <span className="text-[11px]">{job.remote_label}</span>
                )}
              </TableCell>
              <TableCell>
                <span
                  className={cn(
                    "text-xs",
                    job.language_requirement.startsWith("german_b")
                      || job.language_requirement.startsWith("german_c")
                      || job.language_requirement === "german_native"
                      ? "text-warn"
                      : "text-muted-foreground",
                  )}
                >
                  {job.language_label}
                </span>
              </TableCell>
              <TableCell>
                <SalaryCell job={job} />
              </TableCell>
              <TableCell className="tabular text-xs text-muted-foreground">
                {postedAge(job.age_days, job.posted_at)}
              </TableCell>
              <TableCell>
                <StatusBadge status={job.status} />
              </TableCell>
              <TableCell>
                <StarButton
                  starred={job.starred}
                  onToggle={() => onPatch(job, { starred: !job.starred })}
                />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Separator />
      <p className="px-3 py-2 text-[11px] text-muted-foreground">
        Salary is shown only when the employer stated it. A “≈” marks a figure that was
        annualised or converted from another currency.
      </p>
    </div>
  );
}
