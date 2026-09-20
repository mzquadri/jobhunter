"use client";

import type { Job, JobStatus } from "@/lib/types";
import { isWarning, postedAge, scoreBand } from "@/lib/format";

const RULE_BY_TIER: Record<Job["tier"], string> = {
  // Priority is weight, never hue: that keeps colour free to mean only status.
  DREAM: "bg-ink",
  PRIORITY: "bg-ink-2",
  NORMAL: "bg-hair",
};

const STATUSES: JobStatus[] = ["new", "shortlisted", "applied", "rejected"];

export function JobStrip({
  job,
  expanded,
  cursored,
  onToggle,
  onPatch,
}: {
  job: Job;
  expanded: boolean;
  cursored: boolean;
  onToggle: () => void;
  onPatch: (patch: Partial<Job>) => void;
}) {
  const band = scoreBand(job.score);
  const justPosted = job.age_days !== null && job.age_days <= 2;

  return (
    <article
      data-cursor={cursored || undefined}
      className={`grid grid-cols-[5px_1fr_auto] border border-t-0 border-hair bg-panel first:border-t
        ${expanded ? "border-ink-2" : "hover:border-rule"}
        ${cursored ? "shadow-[inset_3px_0_0_var(--color-live)]" : ""}`}
    >
      <div className={RULE_BY_TIER[job.tier]} />

      <div className="min-w-0 cursor-pointer px-4 py-3" onClick={onToggle}>
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="font-semibold">
            {job.company}
            {job.tier === "DREAM" && (
              <span className="ml-1.5 align-super text-[9px] text-ink-2">◆</span>
            )}
          </span>
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="border-b border-rule hover:border-ink"
          >
            {job.title}
          </a>
          {justPosted && <Badge tone="go">JUST POSTED</Badge>}
          {job.is_new && <Badge tone="live">NEW</Badge>}
          {job.status === "applied" && <Badge tone="go">APPLIED</Badge>}
          {job.flags.map((f) => (
            <Badge key={f.code} tone={isWarning(f.code) ? "warn" : "caution"} title={f.why}>
              {f.code}
            </Badge>
          ))}
        </div>

        <div className="mt-1 flex flex-wrap gap-4 text-[12.5px] text-ink-2">
          <span>{job.location || "location not stated"}</span>
          <span>{postedAge(job)}</span>
          <span>{job.source}</span>
          {job.salary && <span>{job.salary}</span>}
        </div>

        {job.skills.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {job.skills.slice(0, 6).map((s) => (
              <span key={s} className="border border-hair px-1.5 py-0.5 text-[11px] text-ink-2">
                {s}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex min-w-[112px] flex-col justify-center gap-1.5 border-l border-hair py-3 pr-4 pl-2 text-right">
        <span
          className={`num text-[24px] leading-none font-semibold ${
            band === "go" ? "text-go" : band === "low" ? "text-ink-3" : ""
          }`}
        >
          {job.score}
        </span>
        <span className="h-[3px] bg-sunk">
          <i
            className={`block h-full ${band === "go" ? "bg-go" : "bg-ink-2"}`}
            style={{ width: `${Math.min(job.score, 100)}%` }}
          />
        </span>
        <span className="flex justify-end gap-1">
          <button
            type="button"
            title="Star"
            aria-pressed={job.starred}
            onClick={() => onPatch({ starred: !job.starred })}
            className={`border px-1.5 text-[12px] ${
              job.starred
                ? "border-caution text-caution"
                : "border-transparent text-ink-3 hover:border-rule hover:text-ink"
            }`}
          >
            {job.starred ? "★" : "☆"}
          </button>
          <button
            type="button"
            title="Hide"
            onClick={() => onPatch({ hidden: true })}
            className="border border-transparent px-1.5 text-[12px] text-ink-3 hover:border-rule hover:text-ink"
          >
            ✕
          </button>
        </span>
      </div>

      {expanded && (
        <div className="col-start-2 col-end-[-1] border-t border-hair bg-sunk px-4 py-3 text-[13.5px] max-[620px]:col-start-1">
          {job.flags.length > 0 && (
            <div className="mb-3">
              {job.flags.map((f) => (
                <div
                  key={f.code}
                  className={`mb-1.5 px-2.5 py-1.5 text-[12.5px] ${
                    isWarning(f.code)
                      ? "bg-warn-bg text-warn"
                      : "bg-caution-bg text-caution"
                  }`}
                >
                  <b>{f.code}</b> — {f.why}
                </div>
              ))}
            </div>
          )}

          {job.excerpt && (
            <p className="mb-3 max-w-[76ch] whitespace-pre-line text-ink-2">{job.excerpt}</p>
          )}

          <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3.5 gap-y-1 text-[12.5px]">
            <dt className="text-ink-3">Location</dt>
            <dd>{job.location || "not stated"}</dd>
            <dt className="text-ink-3">Posted</dt>
            <dd>
              {job.posted_on ?? "not stated"} · {postedAge(job)}
            </dd>
            <dt className="text-ink-3">Source</dt>
            <dd>{job.source}</dd>
            {job.skills.length > 0 && (
              <>
                <dt className="text-ink-3">Your skills</dt>
                <dd>{job.skills.join(", ")}</dd>
              </>
            )}
            {job.draft_folder && (
              <>
                <dt className="text-ink-3">Draft</dt>
                <dd className="font-mono text-[11.5px] break-all text-ink-2">
                  data/drafts/{job.draft_folder}
                </dd>
              </>
            )}
          </dl>

          <div className="flex flex-wrap items-center gap-2">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-ink px-3.5 py-1.5 text-[13px] font-semibold text-paper hover:opacity-85"
            >
              Open the posting
            </a>
            <select
              value={job.status}
              onChange={(e) => onPatch({ status: e.target.value as JobStatus })}
              aria-label="Application status"
              className="border border-rule bg-transparent px-2.5 py-1.5 text-[13px] text-ink"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            {job.applied_on && (
              <span className="text-[12.5px] text-ink-2">applied {job.applied_on}</span>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function Badge({
  tone,
  children,
  title,
}: {
  tone: "go" | "live" | "caution" | "warn";
  children: React.ReactNode;
  title?: string;
}) {
  const tones = {
    go: "bg-go-bg text-go border-go",
    live: "bg-live-bg text-live border-live",
    caution: "bg-caution-bg text-caution border-caution",
    warn: "bg-warn-bg text-warn border-warn",
  } as const;
  return (
    <span
      title={title}
      className={`border px-1.5 py-0.5 text-[11px] font-semibold tracking-[0.03em] ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
