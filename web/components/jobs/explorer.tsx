"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { toast } from "sonner";
import {
  ALL_STATUSES,
  api,
  HIGH_PRIORITY,
  STATUS_LABELS,
  WORTH_APPLYING,
  type JobQuery,
  type JobSummary,
} from "@/lib/api";
import { useDebounced, useHotkey, useResource } from "@/lib/hooks";
import { JobDrawer } from "@/components/jobs/drawer";
import {
  FlagBadges,
  LanguageCell,
  MatchScore,
  QuickActions,
  SalaryCell,
  StatusBadge,
  type RowPatch,
} from "@/components/jobs/shared";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Drawer,
  ErrorState,
  Input,
  Page,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableSkeleton,
  Tabs,
} from "@/components/ui/primitives";
import { cn, postedAge } from "@/lib/utils";

const PAGE_SIZE = 150;

/**
 * One-click views, grouped so they compose instead of fighting.
 *
 * Each group owns exactly one query key. Picking "Germany" replaces
 * "Switzerland" because a role is in one country; picking "Munich" alongside
 * "80%+" keeps both because they are different questions. The old flat list
 * made every chip toggle independently, so clicking two of them silently
 * produced a filter nobody asked for.
 */
type QuickView = { id: string; label: string; key: keyof JobQuery; value: unknown };

/**
 * The one view that is several answers at once.
 *
 * Everything else in the bar owns a single query key, which is what stops two
 * chips fighting. "For You" is deliberately the exception: it is the whole
 * default stance in one click — worth applying to, recently posted, and in a
 * language you actually have — so it sets a bundle and is only lit when every
 * part of that bundle is in effect.
 */
const FOR_YOU: Partial<JobQuery> = {
  min_score: WORTH_APPLYING,
  max_age_days: 14,
  sort: "recommended",
};

const QUICK_GROUPS: { group: string; views: QuickView[] }[] = [
  {
    group: "match",
    views: [
      { id: "worth", label: "60%+ Worth applying", key: "min_score", value: WORTH_APPLYING },
      { id: "high", label: "80%+", key: "min_score", value: HIGH_PRIORITY },
    ],
  },
  {
    group: "freshness",
    views: [
      { id: "new", label: "New", key: "only_new", value: true },
      { id: "today", label: "Today", key: "max_age_days", value: 0 },
      { id: "24h", label: "Since yesterday", key: "max_age_days", value: 1 },
      { id: "3d", label: "3 days", key: "max_age_days", value: 3 },
      { id: "7d", label: "7 days", key: "max_age_days", value: 7 },
    ],
  },
  {
    group: "place",
    views: [
      { id: "munich", label: "Munich", key: "city", value: "munich" },
      { id: "de", label: "Germany", key: "country", value: "de" },
      { id: "ch", label: "Switzerland", key: "country", value: "ch" },
      { id: "at", label: "Austria", key: "country", value: "at" },
      { id: "nl", label: "Netherlands", key: "country", value: "nl" },
    ],
  },
  {
    group: "language",
    views: [{ id: "english", label: "English compatible", key: "english_compatible", value: true }],
  },
  {
    group: "field",
    views: [
      { id: "ai", label: "AI / LLM", key: "category", value: "Generative AI" },
      { id: "cv", label: "Computer Vision", key: "category", value: "Computer Vision" },
      { id: "robotics", label: "Robotics", key: "domain", value: "robotics" },
      { id: "automotive", label: "Automotive", key: "domain", value: "automotive" },
      { id: "aerospace", label: "Aerospace", key: "domain", value: "aerospace" },
    ],
  },
  {
    group: "mine",
    views: [
      { id: "dream", label: "Dream companies", key: "tier", value: "dream" },
      { id: "saved", label: "Saved", key: "only_starred", value: true },
      { id: "unseen", label: "Unseen", key: "only_unseen", value: true },
      { id: "official", label: "Official only", key: "official_only", value: true },
    ],
  },
];

const QUICK: QuickView[] = QUICK_GROUPS.flatMap((g) => g.views);

const LANGUAGES: [string, string][] = [
  ["english_only", "English only"],
  ["english_preferred", "English preferred"],
  ["german_optional", "German optional"],
  ["german_a1_a2", "German A1/A2"],
  ["german_b1", "German B1"],
  ["german_b2", "German B2"],
  ["german_c1_plus", "German C1+"],
  ["german_native", "German native"],
  ["unclear", "Not stated"],
];

export function JobExplorer() {
  const params = useSearchParams();
  const router = useRouter();

  // Arriving with no filters at all opens on the roles worth applying to
  // rather than on everything ever stored. Storage keeps a 43 in case a later
  // setting change makes it a 67; the opening view is for deciding what to do
  // today. Any link that names its own filters is honoured untouched, and the
  // threshold chip is visibly on, so this is a default rather than a trap.
  const untouched = Array.from(params.keys()).every((k) => k === "open");

  const [query, setQuery] = useState<JobQuery>(() => ({
    // Recommended, not newest: the opening list should be ordered by what to
    // read first, which is match plus recency plus employer priority plus
    // whether the language is one you have. Newest is one click away.
    sort: (params.get("sort") as JobQuery["sort"]) ?? "recommended",
    only_new: params.get("only_new") === "true" || undefined,
    only_unseen: params.get("only_unseen") === "true" || undefined,
    official_only: params.get("official_only") === "true" || undefined,
    english_compatible: params.get("english_compatible") === "true" || undefined,
    only_starred: params.get("only_starred") === "true" || undefined,
    min_score: params.get("min_score")
      ? Number(params.get("min_score"))
      : untouched
        ? WORTH_APPLYING
        : undefined,
    max_age_days: params.get("max_age_days") !== null ? Number(params.get("max_age_days")) : untouched ? 14 : undefined,
    country: (params.get("country") as JobQuery["country"]) ?? undefined,
    tier: params.get("tier") ?? undefined,
    language: params.get("language") ?? undefined,
    status: (params.get("status") as JobQuery["status"]) ?? undefined,
    company: params.get("company") ?? undefined,
    city: params.get("city") ?? undefined,
    category: params.get("category") ?? undefined,
    domain: params.get("domain") ?? undefined,
    limit: PAGE_SIZE,
  }));

  const [text, setText] = useState(params.get("q") ?? "");
  const debounced = useDebounced(text, 250);
  const [view, setView] = useState<"table" | "cards">("table");
  const [showFilters, setShowFilters] = useState(false);
  const [openJob, setOpenJob] = useState<string | null>(params.get("open"));
  const [reviewMode, setReviewMode] = useState(false);
  const [viewName, setViewName] = useState("");
  const savedViews = useResource(() => api.searches(), []);
  const searchRef = useRef<HTMLInputElement>(null);

  useHotkey("/", () => searchRef.current?.focus());

  const effective = useMemo(
    () => ({ ...query, q: debounced.trim() || undefined }),
    [query, debounced],
  );

  const { data, error, loading, refresh, setData } = useResource(
    () => api.jobs(effective),
    [JSON.stringify(effective)],
  );

  const jobs = data?.items ?? [];

  const patch = useCallback(
    async (job: JobSummary, changes: RowPatch) => {
      // Optimistic: the round trip is short, the click should feel instant.
      setData((prev) =>
        prev
          ? {
              ...prev,
              items: changes.hidden
                ? prev.items.filter((j) => j.id !== job.id)
                : prev.items.map((j) => (j.id === job.id ? { ...j, ...changes } : j)),
              total: changes.hidden ? prev.total - 1 : prev.total,
            }
          : prev,
      );
      try {
        await api.updateJob(job.id, changes);
        if (changes.hidden) toast.success("Ignored", { description: job.title });
        else if (changes.starred !== undefined)
          toast.success(changes.starred ? "Saved" : "Removed from saved");
      } catch {
        toast.error("That change did not save.");
        void refresh(true);
      }
    },
    [refresh, setData],
  );

  function set<K extends keyof JobQuery>(key: K, value: JobQuery[K]) {
    setQuery((q) => ({ ...q, [key]: value === "" ? undefined : value, offset: 0 }));
  }

  const forYouActive = (Object.keys(FOR_YOU) as (keyof JobQuery)[]).every(
    (key) => query[key] === FOR_YOU[key],
  );

  function toggleForYou() {
    setQuery((q) =>
      forYouActive
        ? { ...q, min_score: undefined, max_age_days: undefined }
        : { ...q, ...FOR_YOU },
    );
  }

  function toggleQuick(id: string) {
    const item = QUICK.find((q) => q.id === id);
    if (!item) return;
    setQuery((q) => ({
      ...q,
      // Clicking an active chip clears it; clicking a different chip in the
      // same group replaces it, because one key holds one answer.
      [item.key]: q[item.key] === item.value ? undefined : item.value,
      offset: 0,
    }));
  }

  function isQuickActive(item: QuickView) {
    return query[item.key] === item.value;
  }

  const activeFilters = Object.entries(query).filter(
    ([k, v]) => !["sort", "limit", "offset"].includes(k) && v !== undefined && v !== false,
  ).length;

  function clearAll() {
    setQuery({ sort: query.sort, limit: PAGE_SIZE });
    setText("");
  }

  return (
    <>
      {/* Quick views, separated by group so the bar reads as several small
          decisions rather than one long undifferentiated row of chips. */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-border px-5 py-2 scrollbar-thin">
        <button
          onClick={toggleForYou}
          aria-pressed={forYouActive}
          title="Worth applying to, posted in the last two weeks, ordered by what to read first"
          className={cn(
            "shrink-0 rounded-md border px-2.5 py-1 text-[12px] font-medium transition-colors",
            forYouActive
              ? "border-foreground bg-foreground text-background"
              : "border-ring/50 text-foreground hover:bg-accent",
          )}
        >
          For you
        </button>
        <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden />

        {QUICK_GROUPS.map((group, index) => (
          <div key={group.group} className="flex shrink-0 items-center gap-1">
            {index > 0 && <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden />}
            {group.views.map((item) => (
              <button
                key={item.id}
                onClick={() => toggleQuick(item.id)}
                aria-pressed={isQuickActive(item)}
                className={cn(
                  "shrink-0 rounded-md border px-2.5 py-1 text-[12px] transition-colors",
                  isQuickActive(item)
                    ? "border-foreground bg-foreground font-medium text-background"
                    : "border-border text-muted-foreground hover:border-ring/50 hover:text-foreground",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* controls */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-2.5">
        <div className="relative min-w-52 flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={searchRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search role, company, skill or city   (press /)"
            className="h-8 pl-8 text-[13px]"
            aria-label="Search jobs"
          />
        </div>

        <Select
          value={query.sort ?? "newest"}
          onChange={(e) => set("sort", e.target.value as JobQuery["sort"])}
          className="h-8 text-[12px]"
          aria-label="Sort"
        >
          <option value="recommended">Recommended</option>
          <option value="newest">Newest posted</option>
          <option value="discovered">Newest found</option>
          <option value="score">Best match</option>
          <option value="salary">Highest salary</option>
          <option value="company">Company</option>
          <option value="field_relevance">Field relevance</option>
          <option value="experience">Experience fit</option>
          <option value="language">Language fit</option>
          <option value="location">Location priority</option>
          <option value="company_priority">Company priority</option>
        </Select>

        <Button
          variant={showFilters ? "secondary" : "outline"}
          size="sm"
          onClick={() => setShowFilters((v) => !v)}
        >
          <SlidersHorizontal />
          Filters
          {activeFilters > 0 && <Badge variant="info">{activeFilters}</Badge>}
        </Button>

        {activeFilters > 0 && (
          <Button variant="ghost" size="sm" onClick={clearAll}>
            <X /> Clear
          </Button>
        )}

        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={!jobs.length} onClick={() => {
            setReviewMode(true); setOpenJob(jobs.find((j) => !j.reviewed_at)?.id ?? jobs[0].id);
          }}>Start review</Button>
          <span className="tabular text-[11px] text-muted-foreground">
            {loading ? "…" : `${data?.total ?? 0} roles`}
          </span>
          <Tabs
            value={view}
            onChange={(v) => setView(v as "table" | "cards")}
            options={[
              { value: "table", label: "Table" },
              { value: "cards", label: "Cards" },
            ]}
          />
        </div>
      </div>

      <Drawer open={showFilters} onClose={() => setShowFilters(false)} label="Advanced filters">
        <div className="flex items-center justify-between p-4"><h2 className="text-sm font-medium">Advanced filters</h2><Button variant="ghost" size="sm" onClick={() => setShowFilters(false)}>Done</Button></div>
        <FilterPanel query={query} onChange={set} />
      </Drawer>

      <Page>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Select aria-label="Saved views" value="" onChange={(e) => {
            const saved = savedViews.data?.find((v) => v.id === Number(e.target.value));
            if (saved) { setQuery({ ...saved.query, limit: PAGE_SIZE }); setText(String(saved.query.q ?? "")); }
          }}><option value="">Saved views</option>{savedViews.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</Select>
          <Input className="h-8 max-w-52 text-xs" aria-label="Name this view" placeholder="Name this view" value={viewName} onChange={(e) => setViewName(e.target.value)} />
          <Button size="sm" variant="outline" disabled={!viewName.trim()} onClick={async () => {
            const filters = Object.fromEntries(Object.entries(effective).filter(([key, value]) => !["limit", "offset"].includes(key) && value !== undefined));
            try { await api.saveSearch(viewName.trim(), filters); setViewName(""); void savedViews.refresh(); toast.success("View pinned"); }
            catch { toast.error("Could not save this view"); }
          }}>Pin view</Button>
        </div>
        {error ? (
          <ErrorState
            title={error.isOffline ? "Cannot reach the backend" : "Could not load jobs"}
            message={error.message}
            retry={() => void refresh()}
          />
        ) : loading && jobs.length === 0 ? (
          <TableSkeleton rows={10} />
        ) : jobs.length === 0 ? (
          <EmptyState
            title="Nothing matches"
            hint="Clear a filter or widen the search. CareerOS scans every hour, so new roles appear on their own."
            action={
              <Button variant="outline" size="sm" onClick={clearAll}>
                Reset filters
              </Button>
            }
          />
        ) : view === "table" ? (
          <JobTable jobs={jobs} onOpen={setOpenJob} onPatch={patch} />
        ) : (
          <JobCards jobs={jobs} onOpen={setOpenJob} onPatch={patch} />
        )}
        {!!data && data.total > PAGE_SIZE && <div className="mt-4 flex items-center justify-end gap-3 text-xs">
          <Button size="sm" variant="outline" disabled={!query.offset} onClick={() => setQuery((q) => ({ ...q, offset: Math.max(0, (q.offset ?? 0) - PAGE_SIZE) }))}>Previous page</Button>
          <span>{(query.offset ?? 0) + 1}–{Math.min((query.offset ?? 0) + PAGE_SIZE, data.total)} of {data.total}</span>
          <Button size="sm" variant="outline" disabled={(query.offset ?? 0) + PAGE_SIZE >= data.total} onClick={() => setQuery((q) => ({ ...q, offset: (q.offset ?? 0) + PAGE_SIZE }))}>Next page</Button>
        </div>}
      </Page>

      <JobDrawer
        jobId={openJob}
        reviewMode={reviewMode}
        // The panel walks the list you are actually looking at, in the order
        // it is shown, so j/k move through your filtered results rather than
        // some global ordering the drawer invented.
        siblings={jobs.map((j) => j.id)}
        onNavigate={setOpenJob}
        onClose={() => { setOpenJob(null); setReviewMode(false); }}
        onChanged={(updated) => {
          setData((prev) =>
            prev
              ? { ...prev, items: prev.items.map((j) => (j.id === updated.id ? { ...j, ...updated } : j)) }
              : prev,
          );
          router.refresh();
        }}
      />
    </>
  );
}

function FilterPanel({
  query,
  onChange,
}: {
  query: JobQuery;
  onChange: <K extends keyof JobQuery>(key: K, value: JobQuery[K]) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/30 px-5 py-2.5">
      <Select
        value={query.country ?? ""}
        onChange={(e) => onChange("country", (e.target.value || undefined) as JobQuery["country"])}
        className="h-8 text-[12px]"
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
        className="h-8 text-[12px]"
        aria-label="Employer priority"
      >
        <option value="">Any employer</option>
        <option value="dream">Shortlist</option>
        <option value="high">High priority</option>
        <option value="normal">Normal</option>
      </Select>

      <Select
        value={query.language ?? ""}
        onChange={(e) => onChange("language", e.target.value || undefined)}
        className="h-8 text-[12px]"
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
        className="h-8 text-[12px]"
        aria-label="Work mode"
      >
        <option value="">Any work mode</option>
        <option value="remote">Remote</option>
        <option value="hybrid">Hybrid</option>
        <option value="onsite">On-site</option>
      </Select>

      <Select
        value={query.seniority ?? ""}
        onChange={(e) => onChange("seniority", e.target.value || undefined)}
        className="h-8 text-[12px]"
        aria-label="Level"
      >
        <option value="">Any level</option>
        <option value="graduate">Graduate</option>
        <option value="junior">Junior</option>
        <option value="mid">Mid</option>
        <option value="senior">Senior</option>
      </Select>

      <Select
        value={query.status ?? ""}
        onChange={(e) => onChange("status", (e.target.value || undefined) as JobQuery["status"])}
        className="h-8 text-[12px]"
        aria-label="Application status"
      >
        <option value="">Any status</option>
        {ALL_STATUSES.map((s) => (
          <option key={s} value={s}>
            {STATUS_LABELS[s]}
          </option>
        ))}
      </Select>

      <Select
        value={query.min_score?.toString() ?? ""}
        onChange={(e) => onChange("min_score", e.target.value ? Number(e.target.value) : undefined)}
        className="h-8 text-[12px]"
        aria-label="Minimum match"
      >
        <option value="">Any match</option>
        <option value="90">90+</option>
        <option value="80">80+</option>
        <option value="70">70+</option>
        <option value="60">60+</option>
      </Select>

      <Select
        value={query.salary_min?.toString() ?? ""}
        onChange={(e) => onChange("salary_min", e.target.value ? Number(e.target.value) : undefined)}
        className="h-8 text-[12px]"
        aria-label="Minimum stated salary"
        title="Only roles where the employer actually printed a figure can be compared"
      >
        <option value="">Any salary</option>
        <option value="60000">€60k+ stated</option>
        <option value="70000">€70k+ stated</option>
        <option value="80000">€80k+ stated</option>
      </Select>

      <Select aria-label="Minimum field relevance" value={query.min_relevance ?? ""}
        onChange={(e) => onChange("min_relevance", e.target.value ? Number(e.target.value) : undefined)}>
        <option value="">Any field relevance</option><option value="60">60+ field relevance</option>
        <option value="80">80+ field relevance</option><option value="100">Direct field title</option>
      </Select>

      <label className="flex items-center gap-1.5 text-[12px]">
        <input
          type="checkbox"
          checked={query.only_clean ?? false}
          onChange={(e) => onChange("only_clean", e.target.checked || undefined)}
        />
        No warnings
      </label>
    </div>
  );
}

function JobTable({
  jobs,
  onOpen,
  onPatch,
}: {
  jobs: JobSummary[];
  onOpen: (id: string) => void;
  onPatch: (job: JobSummary, changes: RowPatch) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-12 text-right">Match</TableHead>
            <TableHead className="min-w-[19rem]">Role</TableHead>
            <TableHead className="w-40">Company</TableHead>
            <TableHead className="w-36">Location</TableHead>
            <TableHead className="w-20">Mode</TableHead>
            <TableHead className="w-24">Salary</TableHead>
            <TableHead className="w-28">Language</TableHead>
            <TableHead className="w-20">Level</TableHead>
            <TableHead className="w-20">Posted</TableHead>
            <TableHead className="w-24">Source</TableHead>
            <TableHead className="w-24">Status</TableHead>
            <TableHead className="w-24" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <TableRow
              key={job.id}
              onClick={() => onOpen(job.id)}
              className="cursor-pointer"
            >
              <TableCell className="text-right">
                <MatchScore score={job.score} />
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="truncate text-[13px] font-medium">{job.title}</span>
                  {job.is_new && <Badge variant="info">New</Badge>}
                  {job.tier === "dream" && <Badge variant="outline">◆</Badge>}
                  <FlagBadges flags={job.flags} />
                </div>
              </TableCell>
              <TableCell className="truncate text-[12.5px]">{job.company_name}</TableCell>
              <TableCell className="truncate text-[11.5px] text-muted-foreground">
                {job.city || job.location_raw || "—"}
              </TableCell>
              <TableCell className="text-[11px] text-muted-foreground">
                {job.remote_label === "Not stated" ? "—" : job.remote_label}
              </TableCell>
              <TableCell>
                <SalaryCell job={job} />
              </TableCell>
              <TableCell>
                <LanguageCell job={job} />
              </TableCell>
              <TableCell className="text-[11px] text-muted-foreground">
                {job.seniority_label === "Not stated" ? "—" : job.seniority_label}
              </TableCell>
              <TableCell className="tabular text-[11.5px] text-muted-foreground">
                {postedAge(job.age_days, job.posted_at)}
              </TableCell>
              <TableCell className="truncate text-[11px] text-muted-foreground">
                {job.source}
              </TableCell>
              <TableCell>
                <StatusBadge status={job.status} />
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <QuickActions job={job} onPatch={(c) => onPatch(job, c)} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="border-t border-border px-3 py-2 text-[10.5px] text-muted-foreground">
        Salary is shown only where the employer stated it. “≈” marks a figure that was
        annualised or converted from another currency.
      </p>
    </Card>
  );
}

function JobCards({
  jobs,
  onOpen,
  onPatch,
}: {
  jobs: JobSummary[];
  onOpen: (id: string) => void;
  onPatch: (job: JobSummary, changes: RowPatch) => void;
}) {
  return (
    <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
      {jobs.map((job) => (
        <Card
          key={job.id}
          onClick={() => onOpen(job.id)}
          className="cursor-pointer p-3 transition-colors hover:border-ring/40"
        >
          <div className="flex items-start gap-2.5">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                {job.is_new && <Badge variant="info">New</Badge>}
                {job.tier === "dream" && <Badge variant="outline">Shortlist</Badge>}
                <FlagBadges flags={job.flags} />
              </div>
              <h3 className="mt-1 truncate text-[13px] font-medium">{job.title}</h3>
              <p className="text-[11.5px] text-muted-foreground">{job.company_name}</p>
            </div>
            <MatchScore score={job.score} />
          </div>

          <div className="mt-2 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>{job.city || job.location_raw || "—"}</span>
            {job.remote_label !== "Not stated" && <span>{job.remote_label}</span>}
            <span>{postedAge(job.age_days, job.posted_at)}</span>
            {job.salary.display && <span className="tabular">{job.salary.display}</span>}
          </div>

          <div className="mt-2 flex items-center gap-1.5">
            <LanguageCell job={job} />
            <span className="ml-auto" onClick={(e) => e.stopPropagation()}>
              <QuickActions job={job} onPatch={(c) => onPatch(job, c)} />
            </span>
          </div>
        </Card>
      ))}
    </div>
  );
}
