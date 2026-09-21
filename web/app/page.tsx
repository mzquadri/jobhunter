import Link from "next/link";
import { ArrowUpRight, ExternalLink } from "lucide-react";
import { api, ApiError, type Stats } from "@/lib/api";
import { PageHeader } from "@/components/shell/sidebar";
import { ChartGrid } from "@/components/overview/charts";
import {
  Badge,
  Card,
  CardContent,
  EmptyState,
  Separator,
} from "@/components/ui/primitives";
import { relativeTime, untilTime } from "@/lib/utils";

// Rendered per request: the worker writes on its own schedule, so a cached
// page would show yesterday's numbers.
export const dynamic = "force-dynamic";

export const metadata = { title: "Overview" };

export default async function OverviewPage() {
  let stats: Stats;
  try {
    stats = await api.stats();
  } catch (error) {
    return (
      <>
        <PageHeader title="Overview" />
        <div className="p-6">
          <EmptyState
            title="The dashboard cannot reach the API"
            hint={
              error instanceof ApiError
                ? `${error.message} Start the stack with "docker compose up -d".`
                : "Start the stack with \"docker compose up -d\"."
            }
          />
        </div>
      </>
    );
  }

  const cards = [
    { label: "Found today", value: stats.found_today, href: "/jobs?sort=discovered" },
    { label: "New since last run", value: stats.new_since_last_run, href: "/jobs?only_new=true" },
    { label: "High match", value: stats.high_match, href: "/jobs?min_score=70", accent: true },
    { label: "Open postings", value: stats.total_open, href: "/jobs" },
    { label: "Applications pending", value: stats.applications_pending, href: "/jobs?status=applied" },
    { label: "Submitted", value: stats.applications_submitted, href: "/jobs?status=applied" },
    { label: "Companies hiring", value: stats.companies_with_roles, href: "/companies" },
    { label: "Average match", value: stats.average_match_score, href: "/jobs?sort=score" },
  ];

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={stats.headline}
        actions={<RunStatus stats={stats} />}
      />

      <div className="space-y-6 p-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {cards.map((card) => (
            <Link key={card.label} href={card.href} className="group">
              <Card className="transition-colors hover:border-foreground/20">
                <CardContent className="p-4">
                  <p className="flex items-center gap-1 text-xs text-muted-foreground">
                    {card.label}
                    <ArrowUpRight className="size-3 opacity-0 transition-opacity group-hover:opacity-100" />
                  </p>
                  <p
                    className={`tabular mt-1 text-2xl font-semibold ${
                      card.accent && card.value > 0 ? "text-ok" : ""
                    }`}
                  >
                    {card.value}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>

        <ChartGrid charts={stats.charts} />

        <Watchlist stats={stats} />
      </div>
    </>
  );
}

function RunStatus({ stats }: { stats: Stats }) {
  const run = stats.last_run;
  if (!run) {
    return <span className="text-xs text-muted-foreground">No discovery run yet</span>;
  }
  const tone = run.status === "ok" ? "ok" : run.status === "partial" ? "warn" : "danger";
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <Badge variant={tone}>{run.status}</Badge>
      <span>swept {relativeTime(run.finished_at)}</span>
      {stats.next_run_at && <span>· next {untilTime(stats.next_run_at)}</span>}
      <Link href="/runs" className="hover:underline">
        details
      </Link>
    </div>
  );
}

/**
 * The employers that cannot be automated. Naming them, with a direct link, is
 * more useful than omitting them and implying the search is exhaustive.
 */
function Watchlist({ stats }: { stats: Stats }) {
  if (!stats.watchlist.length) return null;
  return (
    <section>
      <h2 className="text-sm font-medium">Check these by hand</h2>
      <p className="mt-0.5 max-w-2xl text-xs text-muted-foreground">
        These career sites build their listings with JavaScript and publish no open feed, so
        nothing can read them automatically. Each link goes straight to their search.
      </p>
      <Separator className="my-3" />
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {stats.watchlist.map((company) => (
          <li key={company.id}>
            <a
              href={company.careers_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-accent"
            >
              <span className="min-w-0 truncate">{company.name}</span>
              <span className="flex shrink-0 items-center gap-1.5">
                {company.tier === "dream" && <Badge variant="outline">◆</Badge>}
                <ExternalLink className="size-3 text-muted-foreground" />
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
