"use client";

import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Analytics as AnalyticsData, type NamedCount } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import {
  Card,
  EmptyState,
  ErrorState,
  Page,
  SectionTitle,
  Skeleton,
  Stat,
  Tabs,
} from "@/components/ui/primitives";
import { compactNumber } from "@/lib/utils";

const RANGES = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

/** Chart colours come from the theme, so both light and dark stay readable. */
const INK = "var(--color-chart-1)";
const MUTED = "var(--color-muted-foreground)";
const GRID = "var(--color-border)";

/**
 * What the market actually looks like for you.
 *
 * Every figure here is counted from postings CareerOS stored. Where coverage
 * is partial — salary, above all — the screen says how partial rather than
 * quietly charting a biased subset as if it were the whole market.
 */
export function Analytics() {
  const [range, setRange] = useState("30");
  const { data, error, loading, refresh } = useResource(
    () => api.analytics(Number(range)),
    [range],
  );

  if (error) {
    return (
      <Page>
        <ErrorState
          title={error.isOffline ? "CareerOS cannot reach its backend" : "Could not load analytics"}
          message={
            error.isOffline
              ? "The API is not responding. If you just started the stack, give it a few seconds."
              : error.message
          }
          retry={() => void refresh()}
        />
      </Page>
    );
  }

  if (loading && !data) {
    return (
      <Page className="space-y-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[68px]" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </Page>
    );
  }

  if (!data) return null;

  const empty = data.discovered_by_day.every((d) => d.count === 0) && data.by_company.length === 0;

  return (
    <Page className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[12px] text-muted-foreground">
          Counted from every role open right now. The range sets the timeline below it.
        </p>
        <Tabs value={range} onChange={setRange} options={RANGES} />
      </div>

      {empty ? (
        <EmptyState
          title="Not enough data yet"
          hint="Analytics fill in as scans collect postings. Run a scan from Automation and come back."
        />
      ) : (
        <>
          {/* Only figures the API actually returns. A tile with no number
              behind it is worse than no tile. */}
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-5">
            <Stat label="Open roles" value={data.totals.open?.toLocaleString() ?? "—"} />
            <Stat
              label="Strong matches (80+)"
              value={strongCount(data)?.toLocaleString() ?? "—"}
              tone="ok"
            />
            <Stat label="Roles you tracked" value={data.totals.applications ?? "—"} href="/applications" />
            <Stat label="Awaiting a reply" value={data.totals.pending ?? "—"} href="/applications" />
            <Stat
              label="Stated a salary"
              value={`${Math.round(data.salary_coverage * 100)}%`}
              hint={`${data.totals.with_salary ?? 0} of ${data.totals.open ?? 0} open roles`}
            />
          </div>

          <Card className="p-4">
            <SectionTitle
              title="Roles found per day"
              hint="When postings were first seen by CareerOS, not when they were published."
            />
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={data.discovered_by_day} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="found" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={INK} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={INK} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: MUTED }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: MUTED }}
                  tickLine={false}
                  axisLine={false}
                  allowDecimals={false}
                  width={44}
                />
                <Tooltip content={<ChartTooltip unit="roles" />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke={INK}
                  strokeWidth={1.5}
                  fill="url(#found)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <RankedCard
              title="Employers hiring most"
              hint="By roles that matched your profile."
              items={data.by_company}
            />
            <RankedCard
              title="Where the roles are"
              hint="Country of the posting, as the employer stated it."
              items={data.by_country}
            />
            <RankedCard
              title="Role types"
              hint="How CareerOS categorised each posting."
              items={data.by_category}
            />
            <RankedCard
              title="Language expected"
              hint="Read from the posting text, not assumed from the country."
              items={data.by_language}
            />
            <RankedCard
              title="Seniority asked for"
              hint="Inferred from the title and the stated years."
              items={data.by_seniority}
            />
            <RankedCard
              title="Where they came from"
              hint="The source each posting was read from."
              items={data.by_source}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-4">
              <SectionTitle
                title="Match scores"
                hint="How your profile scores against everything found."
              />
              <BandChart items={data.score_distribution} />
            </Card>

            <Card className="p-4">
              <SectionTitle
                title="How fresh the roles are"
                hint="Age at the time of the last scan."
              />
              <BandChart items={data.freshness_distribution} />
            </Card>
          </div>

          <Card className="p-4">
            <SectionTitle
              title="Salary, where it was stated"
              hint={
                `Only ${Math.round(data.salary_coverage * 100)}% of open roles stated a salary. ` +
                "The rest are not counted here, and nothing is estimated to fill the gap."
              }
            />
            <SalaryChart data={data} />
          </Card>

          <Card className="p-4">
            <SectionTitle
              title="Your funnel"
              hint="How far the roles you tracked have travelled."
            />
            <Funnel data={data} />
          </Card>
        </>
      )}
    </Page>
  );
}

/* -------------------------------------------------------------------------- */

/** The 80-100 bucket, as the server labelled it. Read, never recomputed. */
function strongCount(data: AnalyticsData): number | null {
  const band = data.score_distribution.find((b) => b.key === "80-100" || b.label === "80-100");
  return band ? band.count : null;
}

/**
 * A ranked list, not a pie chart.
 *
 * Twelve categories in a pie are unreadable; a sorted bar with the number
 * beside it answers "which is biggest and by how much" at a glance.
 */
function RankedCard({
  title,
  hint,
  items,
}: {
  title: string;
  hint: string;
  items: NamedCount[];
}) {
  const top = items.slice(0, 8);
  const max = Math.max(1, ...top.map((i) => i.count));

  return (
    <Card className="p-4">
      <SectionTitle title={title} hint={hint} />
      {top.length === 0 ? (
        <p className="py-6 text-center text-[11.5px] text-muted-foreground">
          Nothing recorded in this window.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {top.map((item) => (
            <li key={item.key} className="flex items-center gap-2.5">
              <span className="w-36 shrink-0 truncate text-[11.5px]" title={item.label}>
                {item.label}
              </span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                <span
                  className="block h-full rounded-full bg-[var(--color-chart-1)]"
                  style={{ width: `${(item.count / max) * 100}%` }}
                />
              </span>
              <span className="tabular w-10 shrink-0 text-right text-[11.5px] text-muted-foreground">
                {item.count}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function BandChart({ items }: { items: NamedCount[] }) {
  if (!items.length) {
    return (
      <p className="py-6 text-center text-[11.5px] text-muted-foreground">
        Nothing recorded in this window.
      </p>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={items} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: MUTED }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: MUTED }}
          tickLine={false}
          axisLine={false}
          allowDecimals={false}
          width={44}
        />
        <Tooltip cursor={{ fill: "var(--color-muted)" }} content={<ChartTooltip unit="roles" />} />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {items.map((item) => (
            <Cell key={item.key} fill={INK} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SalaryChart({ data }: { data: AnalyticsData }) {
  const bands = data.salary_bands;
  const counted = bands.reduce((n, b) => n + b.count, 0);

  if (counted === 0) {
    return (
      <p className="py-6 text-center text-[11.5px] text-muted-foreground">
        No posting in this window stated a salary. Nothing is inferred to fill the gap.
      </p>
    );
  }

  const max = Math.max(...bands.map((b) => b.count));

  return (
    <>
      <ul className="space-y-1.5">
        {bands.map((band) => (
          <li key={band.label} className="flex items-center gap-2.5">
            <span className="tabular w-28 shrink-0 text-[11.5px]">{band.label}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-[var(--color-chart-2)]"
                style={{ width: `${(band.count / max) * 100}%` }}
              />
            </span>
            <span className="tabular w-10 shrink-0 text-right text-[11.5px] text-muted-foreground">
              {band.count}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-[10.5px] text-muted-foreground">
        Based on {compactNumber(counted)} postings that stated a figure. Ranges are converted to a
        yearly EUR equivalent where the employer gave a different period or currency.
      </p>
    </>
  );
}

function Funnel({ data }: { data: AnalyticsData }) {
  const stages = data.funnel;
  const top = Math.max(1, ...stages.map((s) => s.count));
  const tracked = stages.reduce((n, s) => n + s.count, 0);

  if (tracked === 0) {
    return (
      <p className="py-6 text-center text-[11.5px] text-muted-foreground">
        Nothing tracked yet. Set a role to Interested in Jobs and it appears here.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {stages.map((stage) => (
        <li key={stage.key} className="flex items-center gap-2.5">
          <span className="w-32 shrink-0 text-[11.5px]">{stage.label}</span>
          <span className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
            <span
              className="block h-full rounded-full bg-[var(--color-chart-3)]"
              style={{ width: `${(stage.count / top) * 100}%` }}
            />
          </span>
          <span className="tabular w-10 shrink-0 text-right text-[11.5px] text-muted-foreground">
            {stage.count}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Recharts' default tooltip does not inherit the theme. This one does. */
function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: { value?: number | string }[];
  label?: string | number;
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 text-[11px] shadow-md">
      <p className="text-muted-foreground">{label}</p>
      <p className="tabular font-medium">
        {payload[0]?.value} {unit}
      </p>
    </div>
  );
}
