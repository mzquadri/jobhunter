"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Charts as ChartData, DayCount, NamedCount } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, EmptyState } from "@/components/ui/primitives";

const AXIS = {
  stroke: "var(--color-muted-foreground)",
  fontSize: 11,
  tickLine: false,
  axisLine: false,
} as const;

interface TooltipProps {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}

function ChartTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-sm">
      <p className="font-medium">{label}</p>
      <p className="tabular text-muted-foreground">{payload[0].value} postings</p>
    </div>
  );
}

function Panel({
  title,
  description,
  children,
  empty,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  empty: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </CardHeader>
      <CardContent className="h-56">
        {empty ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            Not enough data yet.
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

/** Postings per day. The one chart where recency is the whole story. */
export function PostingsPerDay({ data }: { data: DayCount[] }) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  return (
    <Panel
      title="Postings per day"
      description="When employers published, not when we found them"
      empty={total === 0}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
          <XAxis
            dataKey="label"
            {...AXIS}
            interval="preserveStartEnd"
            tickFormatter={(v: string) => v.slice(0, 6)}
          />
          <YAxis {...AXIS} allowDecimals={false} width={32} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--color-muted)" }} />
          <Bar dataKey="count" radius={[2, 2, 0, 0]}>
            {data.map((d) => (
              // The last 48 hours are the postings worth acting on today.
              <Cell
                key={d.day}
                fill={d.age_days <= 2 ? "var(--color-chart-1)" : "var(--color-muted-foreground)"}
                fillOpacity={d.age_days <= 2 ? 1 : 0.35}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Panel>
  );
}

/** A horizontal bar list. Right for categorical data with long labels. */
export function Breakdown({
  title,
  description,
  data,
  color = "var(--color-chart-1)",
}: {
  title: string;
  description?: string;
  data: NamedCount[];
  color?: string;
}) {
  const rows = data.slice(0, 7);
  const max = Math.max(1, ...rows.map((r) => r.count));

  return (
    <Panel title={title} description={description} empty={rows.length === 0}>
      <ul className="flex h-full flex-col justify-center gap-2">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center gap-2.5">
            <span className="w-28 shrink-0 truncate text-xs" title={row.label}>
              {row.label}
            </span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full"
                style={{ width: `${(row.count / max) * 100}%`, backgroundColor: color }}
              />
            </span>
            <span className="tabular w-8 shrink-0 text-right text-xs text-muted-foreground">
              {row.count}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function ChartGrid({ charts }: { charts: ChartData }) {
  const hasAnything =
    charts.by_day.some((d) => d.count > 0) || charts.by_country.length > 0;

  if (!hasAnything) {
    return (
      <EmptyState
        title="No postings yet"
        hint="The worker sweeps every hour. The first run takes about a minute; this page fills itself in once it finishes."
      />
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="lg:col-span-2">
        <PostingsPerDay data={charts.by_day} />
      </div>
      <Breakdown
        title="Where the roles are"
        description="Country, from the posting's own location"
        data={charts.by_country}
      />
      <Breakdown
        title="Language requirement"
        description="Extracted from each posting, or reported as not stated"
        data={charts.by_language}
        color="var(--color-chart-3)"
      />
      <Breakdown
        title="Role category"
        data={charts.by_category}
        color="var(--color-chart-2)"
      />
      <Breakdown
        title="Match score"
        description="How the open postings are distributed"
        data={charts.by_score_band}
        color="var(--color-chart-4)"
      />
      <div className="lg:col-span-2">
        <Breakdown
          title="Employers hiring most"
          data={charts.by_company}
          color="var(--color-chart-5)"
        />
      </div>
    </div>
  );
}
