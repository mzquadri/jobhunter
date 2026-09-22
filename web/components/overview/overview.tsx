"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type CompanyOut,
  type Coverage,
  type JobSummary,
  type NotificationOut,
  type Stats,
} from "@/lib/api";
import { useResource, useScanState } from "@/lib/hooks";
import { JobDrawer } from "@/components/jobs/drawer";
import { JobFeedRow } from "@/components/jobs/shared";
import {
  Button,
  Card,
  ErrorState,
  Page,
  SectionTitle,
  Skeleton,
} from "@/components/ui/primitives";
import { cn, relativeTime, untilTime } from "@/lib/utils";

const SEVERITY_DOT: Record<string, string> = {
  success: "bg-ok",
  warning: "bg-warn",
  danger: "bg-danger",
  info: "bg-info",
  muted: "bg-muted-foreground",
};

/**
 * The morning command centre.
 *
 * It answers one question before any other: *what should I apply to today?*
 * Not "how is the system doing" — that belongs on Automation — and not "how
 * many roles exist", which is a number nobody acts on.
 *
 * So the page is built around the 60 line. "Worth applying" is the largest
 * list on the screen, because a role where roughly 60% of the description is
 * met is a real application opportunity, and a product that only surfaces 90%
 * matches surfaces almost nothing. High-priority roles get their own shorter
 * list above it rather than hiding the rest.
 */
export function Overview() {
  const router = useRouter();
  const [openJob, setOpenJob] = useState<string | null>(null);

  const stats = useResource(() => api.stats(), [], { pollMs: 120_000 });
  const signals = useResource(() => api.signals(6), [], { pollMs: 120_000 });
  const coverage = useResource(() => api.coverage(), [], { pollMs: 300_000 });
  const dream = useResource(() => api.companies({ tier: "dream" }), []);

  const recommend = stats.data?.recommend_min_score ?? 60;
  const high = stats.data?.high_match_score ?? 80;

  // Two lists, one query each. The top list is what to read first; the second
  // is the larger set the whole product exists to stop you overlooking.
  const priority = useResource(
    () => api.jobs({ min_score: high, sort: "newest", limit: 8 }),
    [high],
  );
  const worth = useResource(
    () => api.jobs({ min_score: recommend, sort: "newest", limit: 14 }),
    [recommend],
  );

  const patchJob = useCallback(
    async (job: JobSummary, changes: { starred?: boolean; hidden?: boolean }) => {
      try {
        await api.updateJob(job.id, changes);
        if (changes.hidden) toast.success("Ignored", { description: job.title });
        else toast.success(changes.starred ? "Saved" : "Removed from saved");
        void priority.refresh(true);
        void worth.refresh(true);
      } catch {
        toast.error("That change did not save.");
      }
    },
    [priority, worth],
  );

  if (stats.error) {
    return (
      <Page>
        <ErrorState
          title={
            stats.error.isOffline
              ? "CareerOS cannot reach its backend"
              : "Something went wrong"
          }
          message={
            stats.error.isOffline
              ? "The API is not responding. If you just started the stack, give it a few seconds."
              : stats.error.message
          }
          retry={() => void stats.refresh()}
        />
      </Page>
    );
  }

  const data = stats.data;
  // The high-priority roles are already shown above, so the second list drops
  // them rather than repeating the same card twice on one screen.
  const shown = new Set((priority.data?.items ?? []).map((j) => j.id));
  const worthOnly = (worth.data?.items ?? []).filter((j) => !shown.has(j.id));

  return (
    <Page className="space-y-6">
      <Greeting stats={data} loading={stats.loading} />
      <Metrics stats={data} loading={stats.loading && !data} />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <JobList
            title="High priority"
            hint={`Scoring ${high} or above. Read these first.`}
            jobs={priority.data?.items ?? []}
            loading={priority.loading && !priority.data}
            href={`/jobs?min_score=${high}`}
            empty="Nothing at this level right now. The list below is where the realistic opportunities are."
            onOpen={setOpenJob}
            onPatch={patchJob}
          />

          <JobList
            title="Worth applying"
            hint={
              `Scoring ${recommend}–${high - 1}. You will not meet every line of these, ` +
              `and that is the point — a job description is a wish list.`
            }
            jobs={worthOnly}
            loading={worth.loading && !worth.data}
            href={`/jobs?min_score=${recommend}`}
            empty="Nothing in this band yet. Run a scan, or widen your locations in Settings."
            onOpen={setOpenJob}
            onPatch={patchJob}
            emphasis
          />
        </div>

        <div className="space-y-5">
          <SignalsFeed signals={signals.data} loading={signals.loading} />
          <DreamRadar companies={dream.data} loading={dream.loading} recommend={recommend} />
          <CoveragePanel coverage={coverage.data} loading={coverage.loading} />
          <Watchlist stats={data} />
        </div>
      </div>

      <JobDrawer
        jobId={openJob}
        onClose={() => setOpenJob(null)}
        onChanged={() => {
          void priority.refresh(true);
          void worth.refresh(true);
          void stats.refresh(true);
          router.refresh();
        }}
      />
    </Page>
  );
}

/* -------------------------------------------------------------------------- */
/* Header                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * A compact product header, not a marketing hero.
 *
 * One sentence of what changed, one of where it is, and the two actions that
 * follow from it. Everything in the sentence is a counted figure.
 */
function Greeting({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const { start, starting, state } = useScanState();

  const hour = new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  if (loading && !stats) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-6 w-52" />
        <Skeleton className="h-4 w-96" />
      </div>
    );
  }

  const newRoles = stats?.new_since_last_run ?? 0;
  const headline =
    newRoles > 0
      ? `CareerOS found ${newRoles} new ${newRoles === 1 ? "role" : "roles"} since your last visit.`
      : stats?.last_run
        ? "Nothing new since the last scan."
        : "No scan has run yet.";

  // Only clauses with a real number behind them. A zero is dropped rather than
  // padded out to make the line look fuller.
  const detail = [
    stats?.worth_applying_new
      ? `${stats.worth_applying_new} worth applying to`
      : null,
    stats?.dream_company_open
      ? `${stats.dream_company_open} at shortlisted employers`
      : null,
    stats?.new_in_priority_city && stats.priority_city
      ? `${stats.new_in_priority_city} in ${stats.priority_city}`
      : null,
  ].filter(Boolean);

  async function scan() {
    const result = await start();
    if (result.ok) toast.success("Scan started", { description: "Reading your sources now." });
    else toast.warning(result.message);
  }

  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[17px] font-semibold tracking-tight">{part}</h1>
        <p className="mt-1 text-[13px]">{headline}</p>
        {detail.length > 0 && (
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {detail.join(" · ")}
          </p>
        )}
        {stats?.next_run_at && !state?.running && (
          <p className="mt-0.5 text-[11.5px] text-muted-foreground/80">
            Next scan {untilTime(stats.next_run_at)}.
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href={`/jobs?min_score=${stats?.recommend_min_score ?? 60}`}>
            Review opportunities <ArrowRight />
          </Link>
        </Button>
        <Button size="sm" onClick={scan} disabled={starting || state?.running}>
          <RefreshCw className={cn(state?.running && "animate-spin")} />
          {state?.running ? "Scanning" : "Run scan"}
        </Button>
      </div>
    </div>
  );
}

/**
 * The metric strip.
 *
 * Small, aligned, and every tile links to the exact list it counts — a number
 * you cannot click through to is a number you cannot check.
 */
function Metrics({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const recommend = stats?.recommend_min_score ?? 60;
  const high = stats?.high_match_score ?? 80;

  const tiles: { label: string; value: number | string; href?: string; tone?: string }[] = [
    { label: "New", value: stats?.new_since_last_run ?? "–", href: "/jobs?only_new=true" },
    {
      label: `${recommend}%+`,
      value: stats?.worth_applying ?? "–",
      href: `/jobs?min_score=${recommend}`,
      tone: "text-foreground",
    },
    {
      label: `${high}%+`,
      value: stats?.high_match ?? "–",
      href: `/jobs?min_score=${high}`,
      tone: "text-ok",
    },
    {
      label: stats?.priority_city || "Priority city",
      value: stats?.new_in_priority_city ?? "–",
      href: stats?.priority_city ? `/jobs?city=${encodeURIComponent(stats.priority_city)}` : undefined,
    },
    { label: "Shortlisted", value: stats?.dream_company_open ?? "–", href: "/jobs?tier=dream" },
    { label: "In pipeline", value: stats?.applications_pending ?? "–", href: "/applications" },
    { label: "Open roles", value: stats?.total_open ?? "–", href: "/jobs" },
  ];

  if (loading) {
    return (
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {tiles.map((t) => (
          <Skeleton key={t.label} className="h-[58px]" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map((tile) => {
        const body = (
          <div className="rounded-lg border border-border bg-card px-3 py-2 transition-colors hover:border-ring/50">
            <p className={cn("tabular text-[19px] font-semibold leading-none", tile.tone)}>
              {tile.value}
            </p>
            <p className="mt-1.5 truncate text-[11px] text-muted-foreground">{tile.label}</p>
          </div>
        );
        return tile.href ? (
          <Link key={tile.label} href={tile.href} className="block">
            {body}
          </Link>
        ) : (
          <div key={tile.label}>{body}</div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Lists                                                                       */
/* -------------------------------------------------------------------------- */

function JobList({
  title,
  hint,
  jobs,
  loading,
  href,
  empty,
  onOpen,
  onPatch,
  emphasis = false,
}: {
  title: string;
  hint: string;
  jobs: JobSummary[];
  loading: boolean;
  href: string;
  empty: string;
  onOpen: (id: string) => void;
  onPatch: (job: JobSummary, changes: { starred?: boolean; hidden?: boolean }) => void;
  emphasis?: boolean;
}) {
  return (
    <Card className={cn(emphasis && "border-ring/30")}>
      <div className="flex items-start gap-3 border-b border-border px-3.5 py-3">
        <div className="min-w-0">
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          <p className="mt-0.5 text-[11.5px] leading-snug text-muted-foreground">{hint}</p>
        </div>
        <Button asChild variant="ghost" size="sm" className="ml-auto shrink-0">
          <Link href={href}>
            See all <ArrowRight />
          </Link>
        </Button>
      </div>

      {loading ? (
        <div className="space-y-1 p-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : jobs.length === 0 ? (
        <p className="px-4 py-10 text-center text-[12px] text-muted-foreground">{empty}</p>
      ) : (
        jobs.map((job) => (
          <JobFeedRow
            key={job.id}
            job={job}
            onOpen={() => onOpen(job.id)}
            onPatch={(changes) => onPatch(job, changes)}
          />
        ))
      )}
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Side panels                                                                 */
/* -------------------------------------------------------------------------- */

function SignalsFeed({
  signals,
  loading,
}: {
  signals: NotificationOut[] | null;
  loading: boolean;
}) {
  return (
    <Card>
      <div className="flex items-center gap-1.5 border-b border-border px-3.5 py-2.5">
        <Sparkles className="size-3.5 text-muted-foreground" />
        <h2 className="text-[13px] font-semibold tracking-tight">Career signals</h2>
      </div>

      {loading && !signals ? (
        <div className="space-y-2 p-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : !signals?.length ? (
        <p className="px-3 py-8 text-center text-[11.5px] text-muted-foreground">
          Signals appear here when a scan finds something worth your attention.
        </p>
      ) : (
        <ul>
          {signals.map((signal) => {
            const body = (
              <>
                <span
                  className={cn(
                    "mt-1.5 size-1.5 shrink-0 rounded-full",
                    SEVERITY_DOT[signal.severity] ?? "bg-muted-foreground",
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] leading-snug">{signal.title}</span>
                  {signal.body && (
                    <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                      {signal.body}
                    </span>
                  )}
                  <span className="mt-0.5 block text-[10px] text-muted-foreground/70">
                    {relativeTime(signal.created_at)}
                  </span>
                </span>
              </>
            );
            return (
              <li key={signal.id} className="border-b border-border last:border-0">
                {signal.href ? (
                  <Link href={signal.href} className="row-hover flex gap-2.5 px-3.5 py-2.5">
                    {body}
                  </Link>
                ) : (
                  <div className="flex gap-2.5 px-3.5 py-2.5">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

/**
 * The shortlist, and what it is doing.
 *
 * Deliberately shows employers with nothing open as well. "NVIDIA — no new
 * relevant roles" is information; omitting NVIDIA looks identical to never
 * having checked.
 */
function DreamRadar({
  companies,
  loading,
  recommend,
}: {
  companies: CompanyOut[] | null;
  loading: boolean;
  recommend: number;
}) {
  const sorted = useMemo(
    () =>
      [...(companies ?? [])].sort(
        (a, b) =>
          b.worth_applying - a.worth_applying ||
          b.best_score - a.best_score ||
          a.name.localeCompare(b.name),
      ),
    [companies],
  );

  return (
    <Card>
      <div className="border-b border-border px-3.5 py-2.5">
        <h2 className="text-[13px] font-semibold tracking-tight">Shortlist radar</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Your dream employers, and whether they are hiring.
        </p>
      </div>

      {loading && !companies ? (
        <div className="space-y-2 p-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : !sorted.length ? (
        <p className="px-3.5 py-8 text-center text-[11.5px] text-muted-foreground">
          Nothing shortlisted yet. Mark an employer as Shortlist in Companies and they
          appear here.
        </p>
      ) : (
        <ul className="max-h-[22rem] overflow-y-auto scrollbar-thin">
          {sorted.slice(0, 14).map((company) => (
            <li key={company.id} className="border-b border-border last:border-0">
              <Link
                href={`/jobs?company=${encodeURIComponent(company.name)}`}
                className="row-hover flex items-center gap-2 px-3.5 py-2"
              >
                <span className="min-w-0 flex-1 truncate text-[12px]">{company.name}</span>
                {company.worth_applying > 0 ? (
                  <span className="tabular shrink-0 text-[11px] text-ok">
                    {company.worth_applying} · best {company.best_score}
                  </span>
                ) : (
                  <span className="shrink-0 text-[10.5px] text-muted-foreground/70">
                    {company.is_automated ? "nothing over " + recommend : "check by hand"}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/**
 * Discovery coverage.
 *
 * "Tracked" and "reading automatically" are two different numbers and are
 * printed as two different numbers. A product that reports the first as though
 * it were the second is claiming to watch employers it never fetches from.
 */
function CoveragePanel({
  coverage,
  loading,
}: {
  coverage: Coverage | null;
  loading: boolean;
}) {
  if (loading && !coverage) return <Skeleton className="h-36 w-full" />;
  if (!coverage) return null;

  return (
    <Card className="p-3.5">
      <SectionTitle
        title="Discovery coverage"
        action={
          <Button asChild variant="ghost" size="sm">
            <Link href="/companies">
              Companies <ArrowRight />
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-3 gap-2">
        <Figure label="Tracked" value={coverage.tracked} />
        <Figure label="Read automatically" value={coverage.automated} tone="text-ok" />
        <Figure label="By hand" value={coverage.manual} />
      </div>
      <p className="mt-2.5 text-[10.5px] leading-snug text-muted-foreground">
        {coverage.manual} employers publish no feed CareerOS can read. They are listed with
        a link rather than counted as monitored.
        {coverage.discovered_by_boards > 0 && (
          <> {coverage.discovered_by_boards} were found through job boards.</>
        )}
      </p>
    </Card>
  );
}

function Figure({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-md border border-border px-2.5 py-1.5">
      <p className={cn("tabular text-[15px] font-semibold leading-none", tone)}>{value}</p>
      <p className="mt-1 text-[10.5px] leading-tight text-muted-foreground">{label}</p>
    </div>
  );
}

function Watchlist({ stats }: { stats: Stats | null }) {
  const items = (stats?.watchlist ?? []).filter(
    (company) => company.careers_url && company.tier === "dream",
  );
  if (!items.length) return null;

  return (
    <Card className="p-3.5">
      <SectionTitle
        title="Check by hand"
        hint="Shortlisted employers with no readable feed."
      />
      <ul className="grid grid-cols-2 gap-1">
        {items.slice(0, 8).map((company) => (
          <li key={company.id}>
            <a
              href={company.careers_url}
              target="_blank"
              rel="noopener noreferrer"
              className="row-hover flex items-center gap-1 rounded px-1.5 py-1 text-[11.5px]"
            >
              <span className="min-w-0 truncate">{company.name}</span>
              <ExternalLink className="ml-auto size-3 shrink-0 text-muted-foreground" />
            </a>
          </li>
        ))}
      </ul>
    </Card>
  );
}