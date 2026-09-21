"use client";

import { ExternalLink, Star, X } from "lucide-react";
import {
  MATCH_LABELS,
  matchBand,
  STATUS_LABELS,
  type Flag,
  type JobSummary,
  type SubScores,
} from "@/lib/api";
import { Badge, Button } from "@/components/ui/primitives";
import { cn, isBlockingFlag, postedAge } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* Match score                                                                 */
/* -------------------------------------------------------------------------- */

const BAND_COLOR: Record<string, string> = {
  strong: "text-ok",
  very_good: "text-ok",
  good: "text-foreground",
  moderate: "text-muted-foreground",
  low: "text-muted-foreground/60",
};

/**
 * The headline number with its band.
 *
 * The band is a UI category, not a claim about the employer's opinion.
 * Nothing above 80 is called "perfect" — the highest label is "Strong match",
 * because the score measures fit against a profile, not likelihood of an offer.
 */
export function MatchScore({
  score,
  size = "sm",
  showLabel = false,
}: {
  score: number;
  size?: "sm" | "lg";
  showLabel?: boolean;
}) {
  const band = matchBand(score);
  return (
    <span className="inline-flex flex-col items-end leading-none">
      <span
        className={cn(
          "tabular font-semibold",
          BAND_COLOR[band],
          size === "lg" ? "text-[30px]" : "text-[13px]",
        )}
      >
        {score}
      </span>
      {showLabel && (
        <span className="mt-1 text-[10px] text-muted-foreground">{MATCH_LABELS[band]}</span>
      )}
    </span>
  );
}

/**
 * The sub-score breakdown.
 *
 * Always visible rather than behind a tooltip: an unexplained score is a
 * number you either trust blindly or ignore, and neither is useful.
 */
export function ScoreBreakdown({ sub }: { sub: SubScores }) {
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
    <dl className="space-y-[7px]">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center gap-2.5">
          <dt className="w-[74px] shrink-0 text-[11px] text-muted-foreground">{label}</dt>
          <dd className="flex min-w-0 flex-1 items-center gap-2">
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className={cn(
                  "block h-full rounded-full",
                  value >= 80 ? "bg-ok" : value >= 50 ? "bg-foreground/60" : "bg-muted-foreground/50",
                )}
                style={{ width: `${Math.min(value, 100)}%` }}
              />
            </span>
            <span className="tabular w-6 shrink-0 text-right text-[11px] text-muted-foreground">
              {value}
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

/* -------------------------------------------------------------------------- */
/* Badges                                                                      */
/* -------------------------------------------------------------------------- */

export function FlagBadges({ flags }: { flags: Flag[] }) {
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
  if (status === "new") return null;
  const tone =
    status === "offer" ? "ok"
      : status === "applied" || status === "interview" || status === "technical_interview"
        ? "info"
        : status === "rejected" || status === "withdrawn" || status === "expired"
          ? "outline"
          : "default";
  return <Badge variant={tone}>{STATUS_LABELS[status] ?? status}</Badge>;
}

/** Salary. The "≈" marks a figure that was annualised or converted. */
export function SalaryCell({ job }: { job: JobSummary }) {
  if (!job.salary.display) {
    return <span className="text-[11px] text-muted-foreground/60">—</span>;
  }
  return (
    <span
      className="tabular text-[12px]"
      title={
        job.salary.is_derived
          ? `Derived from what the employer stated: ${job.salary.evidence}`
          : job.salary.evidence
      }
    >
      {job.salary.display}
    </span>
  );
}

export function LanguageCell({ job }: { job: JobSummary }) {
  const demanding =
    job.language_requirement.startsWith("german_b") ||
    job.language_requirement.startsWith("german_c") ||
    job.language_requirement === "german_native";
  return (
    <span
      className={cn("text-[11px]", demanding ? "text-warn" : "text-muted-foreground")}
      title={job.language_label}
    >
      {job.language_label}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Quick actions                                                               */
/* -------------------------------------------------------------------------- */

/** The patch a list row can apply. Narrower than JobPatch, whose fields are
 *  all nullable — spreading those into a JobSummary would widen columns the
 *  row type declares as non-null. */
export type RowPatch = Partial<Pick<JobSummary, "starred" | "hidden" | "status">>;

export function QuickActions({
  job,
  onPatch,
  compact = false,
}: {
  job: JobSummary;
  onPatch: (patch: RowPatch) => void;
  compact?: boolean;
}) {
  return (
    <span className="flex items-center gap-0.5">
      <Button
        variant="ghost"
        size="icon"
        aria-label={job.starred ? "Remove from saved" : "Save this job"}
        aria-pressed={job.starred}
        title={job.starred ? "Saved" : "Save"}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onPatch({ starred: !job.starred });
        }}
      >
        <Star className={cn("size-3.5", job.starred && "fill-warn text-warn")} />
      </Button>

      {!compact && (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Ignore this job"
          title="Ignore — hides it from every view"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onPatch({ hidden: true });
          }}
        >
          <X className="size-3.5" />
        </Button>
      )}

      <Button variant="ghost" size="icon" asChild title="Open the original posting">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          aria-label="Open the original posting"
        >
          <ExternalLink className="size-3.5" />
        </a>
      </Button>
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Compact job row, used by the overview feed and company pages                */
/* -------------------------------------------------------------------------- */

export function JobFeedRow({
  job,
  onOpen,
  onPatch,
}: {
  job: JobSummary;
  onOpen: () => void;
  onPatch: (patch: { starred?: boolean; hidden?: boolean }) => void;
}) {
  return (
    <div
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
      className="row-hover flex cursor-pointer items-center gap-3 border-b border-border px-3 py-2.5 last:border-0"
    >
      <MatchScore score={job.score} />

      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="truncate text-[13px] font-medium">{job.title}</span>
          {job.is_new && <Badge variant="info">New</Badge>}
          {job.tier === "dream" && <Badge variant="outline">Shortlist</Badge>}
          <FlagBadges flags={job.flags} />
        </span>
        <span className="mt-0.5 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[11px] text-muted-foreground">
          <span>{job.company_name}</span>
          <span>{job.city || job.location_raw || "location not stated"}</span>
          {job.remote_label !== "Not stated" && <span>{job.remote_label}</span>}
          <span>{postedAge(job.age_days, job.posted_at)}</span>
          {job.salary.display && <span className="tabular">{job.salary.display}</span>}
        </span>
      </span>

      <QuickActions job={job} onPatch={onPatch} compact />
    </div>
  );
}
