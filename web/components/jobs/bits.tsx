"use client";

import Link from "next/link";
import { Star } from "lucide-react";
import type { Flag, JobSummary, SubScores } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/api";
import { Badge, Button } from "@/components/ui/primitives";
import { cn, isBlockingFlag, postedAge, scoreColor } from "@/lib/utils";

/** The headline match number. Colour follows the same bands as the charts. */
export function Score({ value, size = "sm" }: { value: number; size?: "sm" | "lg" }) {
  return (
    <span
      className={cn(
        "tabular font-semibold",
        scoreColor(value),
        size === "lg" ? "text-3xl" : "text-sm",
      )}
    >
      {value}
    </span>
  );
}

/**
 * The sub-score breakdown. §10 requires the score to be explainable, and this
 * is where that promise is kept: the seven components are always visible, not
 * hidden behind a tooltip.
 */
export function ScoreBreakdown({ sub, className }: { sub: SubScores; className?: string }) {
  const rows: [string, number][] = [
    ["Technical", sub.technical],
    ["Location", sub.location],
    ["Freshness", sub.freshness],
    ["Experience", sub.experience],
    ["Language", sub.language],
    ["Domain", sub.domain],
    ["Education", sub.education],
  ];
  return (
    <dl className={cn("space-y-1.5", className)}>
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center gap-2.5">
          <dt className="w-20 shrink-0 text-xs text-muted-foreground">{label}</dt>
          <dd className="flex min-w-0 flex-1 items-center gap-2">
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-foreground/70"
                style={{ width: `${Math.min(value, 100)}%` }}
              />
            </span>
            <span className="tabular w-7 shrink-0 text-right text-xs text-muted-foreground">
              {value}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function FlagBadges({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  return (
    <>
      {flags.map((flag) => (
        <Badge
          key={flag.code}
          variant={isBlockingFlag(flag.code) ? "danger" : "warn"}
          title={flag.why}
        >
          {flag.code}
        </Badge>
      ))}
    </>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "applied" || status === "offer"
      ? "ok"
      : status === "rejected" || status === "withdrawn" || status === "expired"
        ? "outline"
        : status === "new"
          ? "info"
          : "default";
  return <Badge variant={tone}>{STATUS_LABELS[status] ?? status}</Badge>;
}

/**
 * Salary. The "≈" is load-bearing: it marks a figure that was annualised or
 * converted, so a derived number is never mistaken for the employer's own.
 */
export function SalaryCell({ job }: { job: JobSummary }) {
  if (!job.salary.display) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  return (
    <span
      className="tabular text-xs"
      title={job.salary.is_derived ? `Derived from: ${job.salary.evidence}` : job.salary.evidence}
    >
      {job.salary.display}
    </span>
  );
}

export function StarButton({
  starred,
  onToggle,
}: {
  starred: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={starred ? "Remove star" : "Star this job"}
      aria-pressed={starred}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
    >
      <Star className={cn("size-4", starred ? "fill-warn text-warn" : "text-muted-foreground")} />
    </Button>
  );
}

export function JobTitleCell({ job }: { job: JobSummary }) {
  return (
    <div className="min-w-0">
      <Link
        href={`/jobs/${encodeURIComponent(job.id)}`}
        className="block truncate text-sm font-medium hover:underline"
      >
        {job.title}
      </Link>
      <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
        {job.is_new && <Badge variant="info">NEW</Badge>}
        {job.tier === "dream" && <Badge variant="outline">◆ shortlist</Badge>}
        <FlagBadges flags={job.flags} />
      </div>
    </div>
  );
}

export function MetaLine({ job }: { job: JobSummary }) {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
      <span>{job.city || job.location_raw || "location not stated"}</span>
      <span>{postedAge(job.age_days, job.posted_at)}</span>
      <span>{job.source}</span>
    </div>
  );
}
