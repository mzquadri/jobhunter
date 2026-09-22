"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { CalendarClock, GripVertical, Plus } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  PIPELINE_STAGES,
  STATUS_LABELS,
  type ApplicationStatus,
  type JobSummary,
} from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { JobDrawer } from "@/components/jobs/drawer";
import { FlagBadges, MatchScore } from "@/components/jobs/shared";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Page,
  Select,
  Skeleton,
} from "@/components/ui/primitives";
import { cn, relativeTime } from "@/lib/utils";

type Columns = Record<string, JobSummary[]>;

/** How many roles one column will load. Far above a realistic pipeline. */
const PER_STAGE = 200;

/** Terminal stages sit apart: they are history, not work in progress. */
const CLOSED_STAGES: ApplicationStatus[] = ["rejected"];
const ACTIVE_STAGES = PIPELINE_STAGES.filter((s) => !CLOSED_STAGES.includes(s));

const STAGE_HINT: Partial<Record<ApplicationStatus, string>> = {
  interested: "Worth a closer look",
  to_apply: "CV and letter being prepared",
  applied: "Sent, waiting for a reply",
  interview: "First conversation booked",
  technical_interview: "Technical round",
  hr_interview: "Final round",
  offer: "Offer on the table",
  rejected: "Closed",
};

const STAGE_ACCENT: Partial<Record<ApplicationStatus, string>> = {
  offer: "bg-ok",
  rejected: "bg-muted-foreground/40",
  interview: "bg-info",
  technical_interview: "bg-info",
  hr_interview: "bg-info",
};

/**
 * The application pipeline.
 *
 * One board, one card per role you are actually pursuing. Cards move between
 * stages by dragging or through the menu on the card — the menu exists because
 * dragging is not available to every input device, not as a second-class path.
 *
 * Order inside a column is computed, not stored: roles with a follow-up due
 * rise to the top, then the strongest match. The board therefore never implies
 * a manual ordering it would silently lose on the next load.
 */
export function ApplicationsBoard() {
  const [openJob, setOpenJob] = useState<string | null>(null);
  const [dragging, setDragging] = useState<JobSummary | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const { data, error, loading, refresh, setData } = useResource<Columns>(
    async () => {
      const pages = await Promise.all(
        PIPELINE_STAGES.map((status) =>
          api.jobs({ status, limit: PER_STAGE, include_closed: true }),
        ),
      );
      return Object.fromEntries(
        PIPELINE_STAGES.map((status, i) => [status, sortColumn(pages[i].items)]),
      );
    },
    [],
  );

  const sensors = useSensors(
    // A small distance so a click to open the drawer is not read as a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );

  const move = useCallback(
    async (job: JobSummary, to: ApplicationStatus, { silent = false } = {}) => {
      const from = job.status;
      if (from === to) return;

      setData((prev) => (prev ? applyMove(prev, job, to) : prev));

      try {
        const updated = await api.updateJob(job.id, { status: to });
        // Replace the optimistic card with what the server actually stored —
        // it also sets applied_at and the follow-up date.
        setData((prev) =>
          prev
            ? {
                ...prev,
                [to]: sortColumn(prev[to].map((j) => (j.id === job.id ? { ...j, ...updated } : j))),
              }
            : prev,
        );
        if (!silent) {
          toast.success(`Moved to ${STATUS_LABELS[to]}`, {
            description: job.title,
            action: { label: "Undo", onClick: () => void move(job, from, { silent: true }) },
          });
        }
      } catch {
        setData((prev) => (prev ? applyMove(prev, { ...job, status: to }, from) : prev));
        toast.error("That move did not save.");
      }
    },
    [setData],
  );

  function onDragStart(event: DragStartEvent) {
    setDragging((event.active.data.current as { job?: JobSummary })?.job ?? null);
  }

  function onDragEnd(event: DragEndEvent) {
    setDragging(null);
    const to = event.over?.id as ApplicationStatus | undefined;
    const job = (event.active.data.current as { job?: JobSummary })?.job;
    if (to && job && PIPELINE_STAGES.includes(to)) void move(job, to);
  }

  const total = useMemo(
    () => (data ? PIPELINE_STAGES.reduce((n, s) => n + data[s].length, 0) : 0),
    [data],
  );

  if (error) {
    return (
      <Page>
        <ErrorState
          title={error.isOffline ? "CareerOS cannot reach its backend" : "Could not load your pipeline"}
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
      <Page>
        <div className="flex gap-3 overflow-hidden">
          {ACTIVE_STAGES.map((stage) => (
            <div key={stage} className="w-[264px] shrink-0 space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ))}
        </div>
      </Page>
    );
  }

  const columns = data ?? {};

  if (total === 0) {
    return (
      <Page>
        <EmptyState
          title="Nothing in your pipeline yet"
          hint="Open a role in Jobs and set it to Interested. It appears here, and CareerOS reminds you when a reply is overdue."
          action={
            <Button asChild size="sm" className="mt-1">
              <Link href="/jobs?min_score=70">
                <Plus /> Find roles to track
              </Link>
            </Button>
          }
        />
      </Page>
    );
  }

  const visible = showClosed ? PIPELINE_STAGES : ACTIVE_STAGES;
  const closedCount = CLOSED_STAGES.reduce((n, s) => n + (columns[s]?.length ?? 0), 0);

  return (
    <Page className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-[12px] text-muted-foreground">
          {total} {total === 1 ? "role" : "roles"} tracked. Drag a card to move it, or use the menu
          on the card.
        </p>
        {closedCount > 0 && (
          <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setShowClosed((v) => !v)}>
            {showClosed ? "Hide" : "Show"} rejected ({closedCount})
          </Button>
        )}
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCorners}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={() => setDragging(null)}
      >
        <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-thin">
          {visible.map((stage) => (
            <Column
              key={stage}
              stage={stage}
              jobs={columns[stage] ?? []}
              onOpen={setOpenJob}
              onMove={move}
            />
          ))}
        </div>

        <DragOverlay dropAnimation={null}>
          {dragging && (
            <div className="w-[248px] rotate-1 opacity-95">
              <CardBody job={dragging} />
            </div>
          )}
        </DragOverlay>
      </DndContext>

      <JobDrawer
        jobId={openJob}
        onClose={() => setOpenJob(null)}
        onChanged={() => void refresh(true)}
      />
    </Page>
  );
}

/* -------------------------------------------------------------------------- */

function Column({
  stage,
  jobs,
  onOpen,
  onMove,
}: {
  stage: ApplicationStatus;
  jobs: JobSummary[];
  onOpen: (id: string) => void;
  onMove: (job: JobSummary, to: ApplicationStatus) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });

  return (
    <section
      ref={setNodeRef}
      aria-label={STATUS_LABELS[stage]}
      className={cn(
        "flex w-[264px] shrink-0 flex-col rounded-lg border border-border bg-card/40 transition-colors",
        isOver && "border-ring bg-accent/40",
      )}
    >
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className={cn("size-1.5 rounded-full", STAGE_ACCENT[stage] ?? "bg-muted-foreground")} />
        <h2 className="text-[12.5px] font-semibold tracking-tight">{STATUS_LABELS[stage]}</h2>
        <span className="tabular ml-auto text-[11px] text-muted-foreground">{jobs.length}</span>
      </header>

      <div className="min-h-24 flex-1 space-y-2 p-2">
        {jobs.length === 0 ? (
          <p className="px-1 py-6 text-center text-[11px] text-muted-foreground/70">
            {STAGE_HINT[stage]}
          </p>
        ) : (
          jobs.map((job) => (
            <Card key={job.id} job={job} onOpen={() => onOpen(job.id)} onMove={onMove} />
          ))
        )}
      </div>
    </section>
  );
}

function Card({
  job,
  onOpen,
  onMove,
}: {
  job: JobSummary;
  onOpen: () => void;
  onMove: (job: JobSummary, to: ApplicationStatus) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: job.id,
    data: { job },
  });

  return (
    <div
      ref={setNodeRef}
      className={cn("group relative", isDragging && "opacity-40")}
    >
      <CardBody job={job} onOpen={onOpen} />

      <div className="absolute right-1 top-1 flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <Select
          value={job.status}
          aria-label={`Move ${job.title} to another stage`}
          onChange={(e) => onMove(job, e.target.value as ApplicationStatus)}
          onClick={(e) => e.stopPropagation()}
          className="h-6 border-transparent bg-card px-1 text-[10px]"
        >
          {PIPELINE_STAGES.map((stage) => (
            <option key={stage} value={stage}>
              {STATUS_LABELS[stage]}
            </option>
          ))}
        </Select>
        <button
          {...listeners}
          {...attributes}
          aria-label={`Drag ${job.title} to another stage`}
          className="cursor-grab rounded p-0.5 text-muted-foreground hover:bg-accent active:cursor-grabbing"
        >
          <GripVertical className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

/** The card's visible content, shared with the drag overlay. */
function CardBody({ job, onOpen }: { job: JobSummary; onOpen?: () => void }) {
  const overdue = isOverdue(job.follow_up_at);

  return (
    <article
      onClick={onOpen}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onKeyDown={(e) => {
        if (onOpen && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onOpen();
        }
      }}
      className={cn(
        "rounded-md border border-border bg-card p-2.5 text-left shadow-sm transition-colors",
        onOpen && "cursor-pointer hover:border-ring/50",
      )}
    >
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[12.5px] font-medium leading-snug">{job.title}</p>
        <MatchScore score={job.score} />
      </div>

      <p className="mt-1 truncate text-[11px] text-muted-foreground">
        {job.company_name}
        {(job.city || job.location_raw) && ` · ${job.city || job.location_raw}`}
      </p>

      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        {job.tier === "dream" && <Badge variant="outline">Shortlist</Badge>}
        {!job.is_open && <Badge variant="outline">Posting closed</Badge>}
        <FlagBadges flags={job.flags} />
      </div>

      {job.follow_up_at && (
        <p
          className={cn(
            "mt-1.5 flex items-center gap-1 text-[10.5px]",
            overdue ? "text-warn" : "text-muted-foreground",
          )}
        >
          <CalendarClock className="size-3" />
          {overdue ? "Follow up — due " : "Follow up "}
          {relativeTime(job.follow_up_at)}
        </p>
      )}
    </article>
  );
}

/* -------------------------------------------------------------------------- */

/** Due first, then strongest match. Never a stored order the board would lose. */
function sortColumn(jobs: JobSummary[]): JobSummary[] {
  return [...jobs].sort((a, b) => {
    const dueA = isOverdue(a.follow_up_at) ? 0 : 1;
    const dueB = isOverdue(b.follow_up_at) ? 0 : 1;
    if (dueA !== dueB) return dueA - dueB;
    return b.score - a.score;
  });
}

function applyMove(columns: Columns, job: JobSummary, to: ApplicationStatus): Columns {
  const next: Columns = { ...columns };
  for (const stage of PIPELINE_STAGES) {
    next[stage] = (next[stage] ?? []).filter((j) => j.id !== job.id);
  }
  next[to] = sortColumn([...next[to], { ...job, status: to }]);
  return next;
}

function isOverdue(iso: string | null | undefined): boolean {
  return !!iso && new Date(iso).getTime() <= Date.now();
}
