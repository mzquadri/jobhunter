"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Briefcase,
  Building2,
  Check,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  Loader2,
  MapPin,
  Star,
  TriangleAlert,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  ALL_STATUSES,
  api,
  isWorthApplying,
  MATCH_LABELS,
  matchBand,
  PIPELINE_STAGES,
  STATUS_LABELS,
  type ApplicationStatus,
  type JobDetail,
} from "@/lib/api";
import {
  Badge,
  Button,
  Drawer,
  Input,
  Select,
  Separator,
  Skeleton,
  Textarea,
} from "@/components/ui/primitives";
import { FlagBadges, MatchScore, ScoreBreakdown } from "@/components/jobs/shared";
import { cn, isBlockingFlag, postedAge, relativeTime } from "@/lib/utils";

/**
 * Job detail, as a right-hand panel.
 *
 * A panel rather than a page because scanning a list is the main activity:
 * opening the twelfth result should not throw away the eleven above it. The
 * URL still carries `?open=<id>`, so a specific job remains linkable.
 */
export function JobDrawer({
  jobId,
  onClose,
  onChanged,
  siblings = [],
  onNavigate,
}: {
  jobId: string | null;
  onClose: () => void;
  onChanged?: (job: JobDetail) => void;
  /** The ids currently on screen, in the order they are shown. */
  siblings?: string[];
  onNavigate?: (id: string) => void;
}) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<"match" | "posting" | "tracking">("match");

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setTab("match");
    api
      .job(jobId)
      .then((d) => !cancelled && setJob(d))
      .catch(() => !cancelled && toast.error("Could not load that job."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const patch = useCallback(
    async (changes: Parameters<typeof api.updateJob>[1], message?: string) => {
      if (!job) return;
      try {
        const updated = await api.updateJob(job.id, changes);
        setJob(updated);
        onChanged?.(updated);
        if (message) toast.success(message);
      } catch {
        toast.error("That change did not save.");
      }
    },
    [job, onChanged],
  );

  const index = jobId ? siblings.indexOf(jobId) : -1;
  const previousId = index > 0 ? siblings[index - 1] : undefined;
  const nextId =
    index >= 0 && index < siblings.length - 1 ? siblings[index + 1] : undefined;

  // Memoised because the keyboard effect depends on them; a fresh closure on
  // every render would tear down and re-register the listener each time.
  const goPrevious = useMemo(
    () => (previousId && onNavigate ? () => onNavigate(previousId) : undefined),
    [previousId, onNavigate],
  );
  const goNext = useMemo(
    () => (nextId && onNavigate ? () => onNavigate(nextId) : undefined),
    [nextId, onNavigate],
  );

  // j/k, because this is a list you move through with your hands on the
  // keyboard. Arrow keys are left alone so the drawer can still be scrolled.
  useEffect(() => {
    if (!jobId) return;
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "j" && goNext) {
        event.preventDefault();
        goNext();
      } else if (event.key === "k" && goPrevious) {
        event.preventDefault();
        goPrevious();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [jobId, goNext, goPrevious]);

  return (
    <Drawer open={!!jobId} onClose={onClose} label="Job detail">
      {loading && !job ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : !job ? null : (
        <>
          <Header
            job={job}
            onClose={onClose}
            nav={
              <DrawerNav
                position={index + 1}
                total={siblings.length}
                onPrevious={goPrevious}
                onNext={goNext}
              />
            }
          />

          <div className="flex gap-0.5 border-b border-border px-4">
            {([
              ["match", "Match"],
              ["posting", "Posting"],
              ["tracking", "Tracking"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                onClick={() => setTab(value)}
                className={cn(
                  "-mb-px border-b-2 px-3 py-2 text-[12px] transition-colors",
                  tab === value
                    ? "border-foreground font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {tab === "match" && <MatchTab job={job} />}
            {tab === "posting" && <PostingTab job={job} />}
            {tab === "tracking" && <TrackingTab job={job} onPatch={patch} />}
          </div>

          <Footer job={job} onPatch={patch} />
        </>
      )}
    </Drawer>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * The line that decides what the reader does next.
 *
 * A bare "68 of 100" reads as a failing grade to anyone who has ever sat an
 * exam, and 68 here is a role worth an evening. So the panel says so in a
 * sentence before showing any breakdown. Below the threshold it says the
 * opposite just as plainly, rather than going quiet and leaving the number to
 * be interpreted.
 */
function Verdict({ score, blocked }: { score: number; blocked: boolean }) {
  if (blocked) {
    return (
      <p className="flex items-start gap-2 rounded-lg border border-warn/40 bg-warn-soft/40 px-3 py-2.5 text-[12.5px]">
        <TriangleAlert className="mt-px size-4 shrink-0 text-warn" />
        <span>
          <strong className="font-medium">Check the requirements first.</strong> This
          posting states a condition — citizenship, clearance or sponsorship — that may
          rule the role out whatever your fit.
        </span>
      </p>
    );
  }

  if (isWorthApplying(score)) {
    return (
      <p className="flex items-start gap-2 rounded-lg border border-ok/40 bg-ok-soft/40 px-3 py-2.5 text-[12.5px]">
        <Check className="mt-px size-4 shrink-0 text-ok" />
        <span>
          <strong className="font-medium">Worth applying.</strong> You will not meet
          every line below, and you are not expected to — a job description is what an
          employer would like, not a minimum.
        </span>
      </p>
    );
  }

  return (
    <p className="rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-[12.5px] text-muted-foreground">
      <strong className="font-medium text-foreground">A long shot.</strong> Below the
      threshold you set for a realistic application. The breakdown below shows which
      part pulled it down.
    </p>
  );
}

function Header({
  job,
  onClose,
  nav,
}: {
  job: JobDetail;
  onClose: () => void;
  nav?: React.ReactNode;
}) {
  return (
    <div className="border-b border-border p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {job.is_new && <Badge variant="info">New</Badge>}
            {job.tier === "dream" && <Badge variant="outline">Shortlist</Badge>}
            {!job.is_open && <Badge variant="outline">Closed</Badge>}
            {job.role_category && <Badge>{job.role_category}</Badge>}
            <FlagBadges flags={job.flags} />
          </div>

          <h2 className="mt-1.5 text-[15px] font-semibold leading-snug">{job.title}</h2>

          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <Building2 className="size-3" />
              {job.company_name}
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="size-3" />
              {job.city || job.location_raw || "location not stated"}
            </span>
            {job.remote_label !== "Not stated" && <span>{job.remote_label}</span>}
            <span>{postedAge(job.age_days, job.posted_at)}</span>
            {job.salary.display && (
              <span className="tabular" title={job.salary.evidence}>
                {job.salary.display}
              </span>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="flex items-center gap-1">
            {nav}
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
              <X />
            </Button>
          </span>
          <MatchScore score={job.score} size="lg" showLabel />
        </div>
      </div>
    </div>
  );
}

function MatchTab({ job }: { job: JobDetail }) {
  const band = matchBand(job.score);
  // A blocking flag is a reason the role may be closed to you regardless of
  // fit -- citizenship, sponsorship. Language is a hurdle, not a wall, and is
  // already priced into the score, so it does not suppress the verdict.
  const blocked = job.flags.some((flag) => isBlockingFlag(flag.code));

  return (
    <div className="space-y-5 p-4">
      <Verdict score={job.score} blocked={blocked} />

      <section>
        <p className="mb-2 text-[11px] font-medium text-muted-foreground">
          {MATCH_LABELS[band]} · {job.score} of 100
        </p>
        <ScoreBreakdown sub={job.sub_scores} />
      </section>

      {job.match_reasons.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[12px] font-medium">Why this matches</h3>
          <ul className="space-y-1">
            {job.match_reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-[12.5px]">
                <Check className="mt-0.5 size-3.5 shrink-0 text-ok" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {job.match_gaps.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[12px] font-medium">Gaps and things to check</h3>
          <ul className="space-y-1">
            {job.match_gaps.map((gap) => (
              <li key={gap} className="flex gap-2 text-[12.5px] text-muted-foreground">
                <span className="mt-0.5 shrink-0 text-warn">△</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {job.flags.length > 0 && (
        <section className="rounded-lg border border-warn/30 bg-warn-soft/30 p-3">
          <h3 className="mb-1.5 text-[12px] font-medium">Before you spend time on this</h3>
          {job.flags.map((flag) => (
            <p key={flag.code} className="text-[12px]">
              <Badge variant={flag.code === "DEUTSCH" ? "warn" : "danger"}>{flag.code}</Badge>{" "}
              {flag.why}
              {flag.evidence && (
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  Matched on “{flag.evidence}”
                </span>
              )}
            </p>
          ))}
        </section>
      )}

      {job.skills.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-[12px] font-medium">Skills the posting names</h3>
          <div className="flex flex-wrap gap-1">
            {job.skills.map((skill) => (
              <Badge key={skill} variant="outline">
                {skill}
              </Badge>
            ))}
          </div>
        </section>
      )}

      <Facts job={job} />
    </div>
  );
}

function Facts({ job }: { job: JobDetail }) {
  const rows: [string, React.ReactNode][] = [
    ["Seniority", job.seniority_label],
    [
      "Experience asked",
      job.experience_min_years ? `${job.experience_min_years}+ years` : "not stated",
    ],
    ["Language", job.language_label],
    [
      "Salary",
      job.salary.display ? (
        <span>
          {job.salary.display}
          {job.salary.is_derived && (
            <span className="ml-1 text-[10px] text-muted-foreground">derived</span>
          )}
        </span>
      ) : (
        "not stated"
      ),
    ],
    ["Posted", job.posted_at ?? "not stated"],
    ["Discovered", relativeTime(job.first_seen_at)],
    ["Last verified", relativeTime(job.last_seen_at)],
    ["Seen in scans", String(job.times_seen)],
  ];

  return (
    <section>
      <h3 className="mb-1.5 text-[12px] font-medium">Details</h3>
      <dl className="grid grid-cols-[130px_1fr] gap-y-1 text-[11.5px]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mb-1.5 mt-4 text-[12px] font-medium">Where this came from</h3>
      <div className="space-y-1">
        {job.sources.map((source) => (
          <a
            key={`${source.provider}-${source.external_id}`}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-[11.5px] text-muted-foreground hover:text-foreground"
          >
            {source.provider}
            {source.is_primary && <Badge variant="outline">primary</Badge>}
            <ExternalLink className="size-3" />
          </a>
        ))}
      </div>

      {job.draft_folder && (
        <div className="mt-4 rounded-md border border-border bg-card p-2.5">
          <p className="flex items-center gap-1.5 text-[11.5px] font-medium">
            <FileText className="size-3.5" />
            A draft is ready
          </p>
          <code className="mt-1 block font-mono text-[10.5px] break-all text-muted-foreground">
            data/drafts/{job.draft_folder}
          </code>
          <p className="mt-1 text-[10.5px] text-muted-foreground">
            Cover letter, the saved advertisement and a checklist. Nothing is ever submitted
            for you.
          </p>
        </div>
      )}
    </section>
  );
}

function PostingTab({ job }: { job: JobDetail }) {
  if (!job.description) {
    return (
      <div className="p-4">
        <p className="text-[12.5px] text-muted-foreground">
          This source publishes only a short preview. Open the original for the full
          advertisement.
        </p>
        <Button asChild size="sm" variant="outline" className="mt-3">
          <a href={job.url} target="_blank" rel="noopener noreferrer">
            Open original <ExternalLink />
          </a>
        </Button>
      </div>
    );
  }
  return (
    <div className="p-4">
      {job.summary && (
        <p className="mb-3 rounded-md bg-muted/50 p-2.5 text-[12px] text-muted-foreground">
          {job.summary}
        </p>
      )}
      <div className="whitespace-pre-line text-[12.5px] leading-relaxed">{job.description}</div>
    </div>
  );
}

function TrackingTab({
  job,
  onPatch,
}: {
  job: JobDetail;
  onPatch: (c: Parameters<typeof api.updateJob>[1], m?: string) => void;
}) {
  const [notes, setNotes] = useState(job.notes);
  const [contact, setContact] = useState(job.contact_person);
  const [followUp, setFollowUp] = useState(job.follow_up_at ?? "");
  const [salaryTalk, setSalaryTalk] = useState(job.salary_discussion);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setNotes(job.notes);
    setContact(job.contact_person);
    setFollowUp(job.follow_up_at ?? "");
    setSalaryTalk(job.salary_discussion);
  }, [job.id, job.notes, job.contact_person, job.follow_up_at, job.salary_discussion]);

  const dirty =
    notes !== job.notes ||
    contact !== job.contact_person ||
    salaryTalk !== job.salary_discussion ||
    (followUp || null) !== job.follow_up_at;

  async function save() {
    setSaving(true);
    await onPatch(
      {
        notes,
        contact_person: contact,
        salary_discussion: salaryTalk,
        follow_up_at: followUp || null,
      },
      "Saved",
    );
    setSaving(false);
  }

  return (
    <div className="space-y-3 p-4">
      <p className="rounded-md bg-muted/50 p-2.5 text-[11px] text-muted-foreground">
        These fields are yours. A scan never overwrites them, so re-running discovery can
        never lose what you typed here.
      </p>

      <Field label="Stage">
        <Select
          className="w-full"
          value={job.status}
          onChange={(e) =>
            onPatch(
              { status: e.target.value as ApplicationStatus },
              `Moved to ${STATUS_LABELS[e.target.value] ?? e.target.value}`,
            )
          }
        >
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        {job.applied_at && (
          <p className="mt-1 text-[11px] text-muted-foreground">Applied {job.applied_at}</p>
        )}
      </Field>

      <Field label="Contact person">
        <Input value={contact} onChange={(e) => setContact(e.target.value)} />
      </Field>

      <Field label="Follow up on">
        <Input type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
      </Field>

      <Field label="Salary discussion">
        <Input
          value={salaryTalk}
          onChange={(e) => setSalaryTalk(e.target.value)}
          placeholder="What was discussed"
        />
      </Field>

      <Field label="Notes">
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="min-h-28" />
      </Field>

      <Button className="w-full" size="sm" disabled={!dirty || saving} onClick={save}>
        {saving && <Loader2 className="animate-spin" />}
        {dirty ? "Save" : "Saved"}
      </Button>

      {job.history.length > 0 && (
        <>
          <Separator />
          <div>
            <h3 className="mb-1.5 text-[12px] font-medium">History</h3>
            <ol className="space-y-1">
              {job.history.map((event, i) => (
                <li key={i} className="text-[11.5px]">
                  <span className="text-muted-foreground">{relativeTime(event.at)}</span>{" "}
                  {STATUS_LABELS[event.from_status] ?? event.from_status} →{" "}
                  <strong>{STATUS_LABELS[event.to_status] ?? event.to_status}</strong>
                  {event.note && (
                    <span className="block text-muted-foreground">{event.note}</span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function Footer({
  job,
  onPatch,
}: {
  job: JobDetail;
  onPatch: (c: Parameters<typeof api.updateJob>[1], m?: string) => void;
}) {
  const inPipeline = PIPELINE_STAGES.includes(job.status as ApplicationStatus);

  return (
    <div className="flex items-center gap-2 border-t border-border p-3">
      <Button
        variant="outline"
        size="sm"
        onClick={() => onPatch({ starred: !job.starred }, job.starred ? "Removed" : "Saved")}
      >
        <Star className={cn("size-3.5", job.starred && "fill-warn text-warn")} />
        {job.starred ? "Saved" : "Save"}
      </Button>

      {!inPipeline && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onPatch({ status: "interested" }, "Added to your pipeline")}
        >
          <Briefcase className="size-3.5" />
          Track
        </Button>
      )}

      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPatch({ hidden: true }, "Ignored")}
        title="Hide this from every view"
      >
        Ignore
      </Button>

      {/*
        The primary action says what you are about to do, and only claims what
        the score supports. Above the line it is an invitation to apply; below
        it, the honest action is still to read the posting, so the button says
        that instead of pretending.
      */}
      <Button asChild size="sm" className="ml-auto">
        <a href={job.url} target="_blank" rel="noopener noreferrer">
          {isWorthApplying(job.score) ? "Prepare application" : "Open original"}
          <ExternalLink />
        </a>
      </Button>
    </div>
  );
}

/**
 * Move through the list without closing the panel.
 *
 * Reading a job is a comparison, not a lookup: the question is almost always
 * "is this better than the last one". Closing the drawer to answer it loses
 * your place in a list of seventy, so the drawer carries the list with it.
 */
function DrawerNav({
  position,
  total,
  onPrevious,
  onNext,
}: {
  position: number;
  total: number;
  onPrevious?: () => void;
  onNext?: () => void;
}) {
  if (total <= 1) return null;
  return (
    <span className="flex items-center gap-0.5">
      <Button
        variant="ghost"
        size="icon"
        onClick={onPrevious}
        disabled={!onPrevious}
        aria-label="Previous job"
        title="Previous job (k)"
      >
        <ChevronUp className="size-4" />
      </Button>
      <span className="tabular px-1 text-[11px] text-muted-foreground">
        {position} / {total}
      </span>
      <Button
        variant="ghost"
        size="icon"
        onClick={onNext}
        disabled={!onNext}
        aria-label="Next job"
        title="Next job (j)"
      >
        <ChevronDown className="size-4" />
      </Button>
    </span>
  );
}
