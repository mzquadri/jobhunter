"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ExternalLink, Sparkles } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type JobSummary,
  type NotificationOut,
  type Stats,
} from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { JobDrawer } from "@/components/jobs/drawer";
import { JobFeedRow } from "@/components/jobs/shared";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Page,
  SectionTitle,
  Skeleton,
  Stat,
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
 * The command centre.
 *
 * Answers one question above all: what changed since I last looked? The
 * greeting and counts sit above a feed of the roles that actually arrived, so
 * the first screen is work to act on rather than a summary to admire.
 */
export function Overview() {
  const router = useRouter();
  const [openJob, setOpenJob] = useState<string | null>(null);

  const stats = useResource(() => api.stats(), [], { pollMs: 120_000 });
  const signals = useResource(() => api.signals(8), [], { pollMs: 120_000 });
  const feed = useResource(
    () => api.jobs({ sort: "discovered", limit: 12, only_new: true }),
    [],
  );
  // If nothing is flagged new (every scan since has run), show the newest
  // regardless, so this panel is never pointlessly empty.
  const fallback = useResource(() => api.jobs({ sort: "newest", limit: 12 }), []);

  const patchJob = useCallback(
    async (job: JobSummary, changes: { starred?: boolean; hidden?: boolean }) => {
      try {
        await api.updateJob(job.id, changes);
        if (changes.hidden) toast.success("Ignored", { description: job.title });
        else toast.success(changes.starred ? "Saved" : "Removed from saved");
        void feed.refresh(true);
        void fallback.refresh(true);
      } catch {
        toast.error("That change did not save.");
      }
    },
    [feed, fallback],
  );

  if (stats.error) {
    return (
      <Page>
        <ErrorState
          title={stats.error.isOffline ? "CareerOS cannot reach its backend" : "Something went wrong"}
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
  const newJobs = feed.data?.items ?? [];
  const items = newJobs.length > 0 ? newJobs : (fallback.data?.items ?? []);
  const showingFallback = newJobs.length === 0 && items.length > 0;

  return (
    <Page className="space-y-5">
      <Greeting stats={data} loading={stats.loading} />

      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-6">
        <Stat label="New since last scan" value={data?.new_since_last_run ?? "–"} tone="info" href="/jobs?only_new=true" />
        <Stat label="Found today" value={data?.found_today ?? "–"} href="/jobs?sort=discovered" />
        <Stat label="High match" value={data?.high_match ?? "–"} tone="ok" href="/jobs?min_score=70" />
        <Stat label="Open roles" value={data?.total_open ?? "–"} href="/jobs" />
        <Stat label="In pipeline" value={data?.applications_pending ?? "–"} href="/applications" />
        <Stat label="Employers hiring" value={data?.companies_with_roles ?? "–"} href="/companies" />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
            <h2 className="text-[13px] font-semibold tracking-tight">
              {showingFallback ? "Most recent roles" : "New since last scan"}
            </h2>
            {showingFallback && (
              <span className="text-[11px] text-muted-foreground">
                nothing new this scan
              </span>
            )}
            <Button asChild variant="ghost" size="sm" className="ml-auto">
              <Link href="/jobs">
                All jobs <ArrowRight />
              </Link>
            </Button>
          </div>

          {feed.loading && items.length === 0 ? (
            <div className="space-y-1 p-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="p-3">
              <EmptyState
                title="No roles yet"
                hint="CareerOS scans every hour. The first scan takes about a minute — you can start one from the refresh button above."
              />
            </div>
          ) : (
            items.map((job) => (
              <JobFeedRow
                key={job.id}
                job={job}
                onOpen={() => setOpenJob(job.id)}
                onPatch={(changes) => patchJob(job, changes)}
              />
            ))
          )}
        </Card>

        <div className="space-y-4">
          <SignalsFeed signals={signals.data} loading={signals.loading} />
          <PipelineSnapshot stats={data} />
          <Watchlist stats={data} />
        </div>
      </div>

      <JobDrawer
        jobId={openJob}
        onClose={() => setOpenJob(null)}
        onChanged={() => {
          void feed.refresh(true);
          void fallback.refresh(true);
          void stats.refresh(true);
          router.refresh();
        }}
      />
    </Page>
  );
}

function Greeting({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const hour = new Date().getHours();
  const part = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  if (loading && !stats) return <Skeleton className="h-14 w-full max-w-lg" />;

  const run = stats?.last_run;
  const summary = run
    ? `Your last scan read ${run.postings_seen.toLocaleString()} postings across ` +
      `${run.providers_ok} sources and kept ${run.postings_relevant}.`
    : "No scan has run yet. Start one from the refresh button above.";

  return (
    <div>
      <h1 className="text-[17px] font-semibold tracking-tight">{part}</h1>
      <p className="mt-0.5 text-[12.5px] text-muted-foreground">
        {summary}
        {stats?.next_run_at && (
          <>
            {" "}
            Next scan {untilTime(stats.next_run_at)}.
          </>
        )}
      </p>
    </div>
  );
}

/**
 * Career Signals.
 *
 * Generated by scans from rows they actually wrote. When a scan finds
 * nothing, it says so — a feed that manufactures activity teaches you to
 * ignore it.
 */
function SignalsFeed({
  signals,
  loading,
}: {
  signals: NotificationOut[] | null;
  loading: boolean;
}) {
  return (
    <Card>
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-2.5">
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
        <p className="px-3 py-6 text-center text-[11.5px] text-muted-foreground">
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
                  <Link href={signal.href} className="row-hover flex gap-2.5 px-3 py-2.5">
                    {body}
                  </Link>
                ) : (
                  <div className="flex gap-2.5 px-3 py-2.5">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function PipelineSnapshot({ stats }: { stats: Stats | null }) {
  if (!stats) return null;
  const { applications_pending: pending, applications_submitted: submitted } = stats;

  return (
    <Card className="p-3">
      <SectionTitle
        title="Applications"
        action={
          <Button asChild variant="ghost" size="sm">
            <Link href="/applications">
              Pipeline <ArrowRight />
            </Link>
          </Button>
        }
      />
      {submitted === 0 && pending === 0 ? (
        <p className="text-[11.5px] text-muted-foreground">
          Nothing tracked yet. Open a role and press Track to add it to your pipeline.
        </p>
      ) : (
        <div className="flex gap-5">
          <div>
            <p className="tabular text-lg font-semibold leading-none">{pending}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">awaiting a reply</p>
          </div>
          <div>
            <p className="tabular text-lg font-semibold leading-none">{submitted}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">submitted</p>
          </div>
        </div>
      )}
    </Card>
  );
}

/**
 * Employers with no readable endpoint.
 *
 * Listed rather than omitted: a silently missing employer looks exactly like
 * an employer with no vacancies.
 */
function Watchlist({ stats }: { stats: Stats | null }) {
  // Only employers you can actually go and look at. One with no recorded URL
  // would be a link that reloads this page.
  const items = (stats?.watchlist ?? []).filter((company) => company.careers_url);
  if (!items.length) return null;

  return (
    <Card className="p-3">
      <SectionTitle
        title="Check by hand"
        hint="These publish no open feed, so nothing can read them automatically."
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
              {company.tier === "dream" && (
                <Badge variant="outline" className="shrink-0">
                  ◆
                </Badge>
              )}
              <ExternalLink className="ml-auto size-3 shrink-0 text-muted-foreground" />
            </a>
          </li>
        ))}
      </ul>
      {items.length > 8 && (
        <Link
          href="/companies"
          className="mt-1.5 block text-[11px] text-muted-foreground hover:text-foreground"
        >
          and {items.length - 8} more
        </Link>
      )}
    </Card>
  );
}
