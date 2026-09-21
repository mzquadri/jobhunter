"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Star } from "lucide-react";
import {
  api,
  STATUS_LABELS,
  STATUS_ORDER,
  type ApplicationStatus,
  type JobDetail,
} from "@/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Separator,
  Textarea,
} from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * The application-tracking panel.
 *
 * Everything here is owned by the candidate. A discovery run never writes
 * these fields, so nothing typed in can be lost to a sweep.
 *
 * Note what this panel does *not* do: it never submits anything to an
 * employer. §19 requires explicit human approval before any external
 * application, and the boundary is that this tool records what you did, it
 * does not act on your behalf.
 */
export function JobActions({ job }: { job: JobDetail }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [status, setStatus] = useState<ApplicationStatus>(job.status);
  const [statusNote, setStatusNote] = useState("");
  const [notes, setNotes] = useState(job.notes);
  const [contact, setContact] = useState(job.contact_person);
  const [followUp, setFollowUp] = useState(job.follow_up_at ?? "");
  const [salaryTalk, setSalaryTalk] = useState(job.salary_discussion);
  const [starred, setStarred] = useState(job.starred);

  async function save(changes: Parameters<typeof api.updateJob>[1]) {
    setSaving(true);
    setError(null);
    try {
      await api.updateJob(job.id, changes);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      startTransition(() => router.refresh());
    } catch {
      setError("That did not save. Is the API still running?");
    } finally {
      setSaving(false);
    }
  }

  const dirty =
    notes !== job.notes ||
    contact !== job.contact_person ||
    salaryTalk !== job.salary_discussion ||
    (followUp || null) !== job.follow_up_at;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Your tracking</CardTitle>
        <Button
          variant="ghost"
          size="icon"
          aria-label={starred ? "Remove star" : "Star this job"}
          aria-pressed={starred}
          onClick={() => {
            const next = !starred;
            setStarred(next);
            void save({ starred: next });
          }}
        >
          <Star className={cn("size-4", starred && "fill-warn text-warn")} />
        </Button>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="status">
            Status
          </label>
          <Select
            id="status"
            className="w-full"
            value={status}
            onChange={(e) => {
              const next = e.target.value as ApplicationStatus;
              setStatus(next);
              void save({ status: next, status_note: statusNote || undefined });
              setStatusNote("");
            }}
          >
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
          {job.applied_at && (
            <p className="text-xs text-muted-foreground">Applied {job.applied_at}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="note">
            Note for the next status change
          </label>
          <Input
            id="note"
            value={statusNote}
            onChange={(e) => setStatusNote(e.target.value)}
            placeholder="Optional"
          />
        </div>

        <Separator />

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="contact">
            Contact person
          </label>
          <Input id="contact" value={contact} onChange={(e) => setContact(e.target.value)} />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="followup">
            Follow up on
          </label>
          <Input
            id="followup"
            type="date"
            value={followUp}
            onChange={(e) => setFollowUp(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="salary">
            Salary discussion
          </label>
          <Input
            id="salary"
            value={salaryTalk}
            onChange={(e) => setSalaryTalk(e.target.value)}
            placeholder="What was discussed"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground" htmlFor="notes">
            Notes
          </label>
          <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>

        {error && <p className="text-xs text-danger">{error}</p>}

        <Button
          className="w-full"
          disabled={!dirty || saving || pending}
          onClick={() =>
            save({
              notes,
              contact_person: contact,
              salary_discussion: salaryTalk,
              follow_up_at: followUp || null,
            })
          }
        >
          {saving || pending ? (
            <Loader2 className="animate-spin" />
          ) : saved ? (
            <Check />
          ) : null}
          {saved ? "Saved" : "Save"}
        </Button>
      </CardContent>
    </Card>
  );
}
