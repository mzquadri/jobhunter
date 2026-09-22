"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Building2, ExternalLink, Search } from "lucide-react";
import { toast } from "sonner";
import { api, type CompanyOut, type CompanyPatch, type JobSummary } from "@/lib/api";
import { useDebounced, useResource } from "@/lib/hooks";
import { JobDrawer } from "@/components/jobs/drawer";
import { JobFeedRow } from "@/components/jobs/shared";
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Input,
  Page,
  Select,
  Separator,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableSkeleton,
  Tabs,
  Textarea,
} from "@/components/ui/primitives";
import { cn, relativeTime } from "@/lib/utils";

type Tier = NonNullable<CompanyPatch["tier"]>;

/** What this screen edits. Narrower than CompanyPatch, whose fields are all
 *  nullable — spreading those into a CompanyOut would widen columns the row
 *  type declares as non-null. */
type CompanyEdit = { tier?: Tier; enabled?: boolean; notes?: string };

const TIERS: { value: Tier; label: string }[] = [
  { value: "dream", label: "Shortlist" },
  { value: "high", label: "High priority" },
  { value: "normal", label: "Normal" },
  { value: "ignored", label: "Not interested" },
];

const TIER_LABEL: Record<string, string> = Object.fromEntries(
  TIERS.map((t) => [t.value, t.label]),
);

/**
 * What is actually known about reaching an employer's jobs.
 *
 * "Tracked" and "monitored" are different words here and they mean different
 * things. Only `live` and `idle` describe a source that has answered; the rest
 * say plainly that nothing is being fetched, which is more useful than a row
 * implying coverage that does not exist.
 */
const SOURCE_STATUS: Record<
  string,
  { label: string; tone: "ok" | "warn" | "danger" | "outline"; hint: string }
> = {
  live: { label: "Live", tone: "ok", hint: "Answering, and returning roles." },
  idle: {
    label: "No openings",
    tone: "outline",
    hint: "Answering normally; nothing open right now.",
  },
  degraded: {
    label: "Degraded",
    tone: "warn",
    hint: "Answering, but failing often enough that results may be incomplete.",
  },
  rate_limited: {
    label: "Rate limited",
    tone: "warn",
    hint: "Refusing us for now. Backed off rather than retried harder.",
  },
  broken: {
    label: "Broken",
    tone: "danger",
    hint: "Had a working source; it stopped answering.",
  },
  manual: {
    label: "By hand",
    tone: "outline",
    hint: "No machine-readable source. Open their careers site to check.",
  },
};

/**
 * The employers CareerOS watches.
 *
 * Two facts decide everything on this screen: whether an employer publishes a
 * feed the scanner can read, and how much you care about them. Employers with
 * no readable feed are listed plainly rather than hidden — a missing employer
 * and an employer with no vacancies look identical otherwise.
 */
export function Companies() {
  const [text, setText] = useState("");
  const query = useDebounced(text, 200).trim().toLowerCase();
  const [view, setView] = useState("all");
  const [industry, setIndustry] = useState("");
  const [openCompany, setOpenCompany] = useState<CompanyOut | null>(null);

  const { data, error, loading, refresh, setData } = useResource(() => api.companies(), []);

  const patch = useCallback(
    async (company: CompanyOut, changes: CompanyEdit) => {
      setData((prev) => prev?.map((c) => (c.id === company.id ? { ...c, ...changes } : c)) ?? prev);
      try {
        const updated = await api.updateCompany(company.id, changes);
        setData((prev) => prev?.map((c) => (c.id === company.id ? updated : c)) ?? prev);
        setOpenCompany((prev) => (prev?.id === company.id ? updated : prev));
        if (changes.tier) toast.success(`${company.name} moved to ${TIER_LABEL[changes.tier]}`);
        else if (changes.enabled !== undefined)
          toast.success(changes.enabled ? `Watching ${company.name}` : `Paused ${company.name}`);
      } catch {
        toast.error("That change did not save.");
        void refresh(true);
      }
    },
    [refresh, setData],
  );

  // Memoised so the two useMemo blocks below are not invalidated by a fresh
  // empty array on every render.
  const companies = useMemo(() => data ?? [], [data]);

  const counts = useMemo(
    () => ({
      all: companies.length,
      dream: companies.filter((c) => c.tier === "dream").length,
      hiring: companies.filter((c) => c.worth_applying > 0).length,
      automated: companies.filter((c) => c.is_automated).length,
      manual: companies.filter((c) => !c.is_automated).length,
    }),
    [companies],
  );

  const industries = useMemo(
    () =>
      Array.from(new Set(companies.map((c) => c.industry).filter(Boolean))).sort(),
    [companies],
  );

  const rows = useMemo(() => {
    let list = companies;
    if (view === "dream") list = list.filter((c) => c.tier === "dream");
    else if (view === "hiring") list = list.filter((c) => c.worth_applying > 0);
    else if (view === "automated") list = list.filter((c) => c.is_automated);
    else if (view === "manual") list = list.filter((c) => !c.is_automated);
    if (industry) list = list.filter((c) => c.industry === industry);
    if (query) {
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(query) ||
          c.industry.toLowerCase().includes(query) ||
          (c.adapter ?? "").toLowerCase().includes(query),
      );
    }
    // Open roles first, then the ones you care most about.
    const rank = { dream: 0, high: 1, normal: 2, ignored: 3 } as Record<string, number>;
    // Employers you could apply to today first, then the ones you care most
    // about, then everyone else. Open-role count is the tie-break, not the lead:
    // forty irrelevant vacancies are worth less than one 78% match.
    return [...list].sort(
      (a, b) =>
        Number(b.worth_applying > 0) - Number(a.worth_applying > 0) ||
        (rank[a.tier] ?? 9) - (rank[b.tier] ?? 9) ||
        b.worth_applying - a.worth_applying ||
        b.best_score - a.best_score ||
        a.name.localeCompare(b.name),
    );
  }, [companies, query, view, industry]);

  if (error) {
    return (
      <Page>
        <ErrorState
          title={error.isOffline ? "CareerOS cannot reach its backend" : "Could not load employers"}
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

  return (
    <Page className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-52 flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search employers"
            className="h-8 pl-8 text-[13px]"
            aria-label="Search employers"
          />
        </div>
        <Tabs
          value={view}
          onChange={setView}
          options={[
            { value: "all", label: "All", count: counts.all },
            { value: "dream", label: "Shortlist", count: counts.dream },
            { value: "hiring", label: "Worth applying", count: counts.hiring },
            { value: "automated", label: "Read automatically", count: counts.automated },
            { value: "manual", label: "By hand", count: counts.manual },
          ]}
        />
        <Select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          aria-label="Filter by industry"
          className="h-8 text-[12px]"
        >
          <option value="">Every industry</option>
          {industries.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </Select>
      </div>

      {loading && !data ? (
        <TableSkeleton rows={10} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No employers match"
          hint={
            query
              ? "Nothing here matches that search. Try a shorter term."
              : "Nothing in this view yet."
          }
        />
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Employer</TableHead>
                <TableHead className="w-28">Worth applying</TableHead>
                <TableHead className="w-20">Best</TableHead>
                <TableHead className="w-20">Open</TableHead>
                <TableHead className="w-24">New (7d)</TableHead>
                <TableHead className="w-32">Source</TableHead>
                <TableHead className="w-32">Last checked</TableHead>
                <TableHead className="w-36">Priority</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((company) => (
                <TableRow
                  key={company.id}
                  onClick={() => setOpenCompany(company)}
                  className={cn("cursor-pointer", !company.enabled && "opacity-55")}
                >
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <span className="text-[13px] font-medium">{company.name}</span>
                      {company.tier === "dream" && <Badge variant="outline">Shortlist</Badge>}
                      {!company.enabled && <Badge variant="outline">Paused</Badge>}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      {[
                        company.industry || "industry not recorded",
                        company.parent_name && `part of ${company.parent_name}`,
                        company.country?.toUpperCase(),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </TableCell>
                  <TableCell className="tabular text-[13px]">
                    {company.worth_applying > 0 ? (
                      <span className="font-medium text-ok">{company.worth_applying}</span>
                    ) : (
                      <span className="text-muted-foreground/60">—</span>
                    )}
                  </TableCell>
                  <TableCell className="tabular text-[13px]">
                    {company.best_score > 0 ? (
                      company.best_score
                    ) : (
                      <span className="text-muted-foreground/60">—</span>
                    )}
                  </TableCell>
                  <TableCell className="tabular text-[13px] text-muted-foreground">
                    {company.open_roles > 0 ? company.open_roles : "—"}
                  </TableCell>
                  <TableCell className="tabular text-[13px]">
                    {company.new_roles_7d > 0 ? (
                      <span className="text-ok">+{company.new_roles_7d}</span>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell>
                    <SourceBadge company={company} />
                  </TableCell>
                  <TableCell className="text-[11.5px] text-muted-foreground">
                    {company.last_checked_at ? relativeTime(company.last_checked_at) : "never"}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Select
                      value={company.tier}
                      aria-label={`Priority for ${company.name}`}
                      onChange={(e) => patch(company, { tier: e.target.value as Tier })}
                      className="h-7 w-full text-[11.5px]"
                    >
                      {TIERS.map((tier) => (
                        <option key={tier.value} value={tier.value}>
                          {tier.label}
                        </option>
                      ))}
                    </Select>
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    {/* Not every employer record carries a careers URL. An
                        anchor with an empty href would reload this page. */}
                    {company.careers_url ? (
                      <a
                        href={company.careers_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open the careers site of ${company.name}`}
                        title="Open their careers site"
                        className="inline-flex size-7 items-center justify-center rounded text-muted-foreground hover:bg-accent hover:text-foreground"
                      >
                        <ExternalLink className="size-3.5" />
                      </a>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <CompanyDrawer
        company={openCompany}
        onClose={() => setOpenCompany(null)}
        onPatch={patch}
      />
    </Page>
  );
}

/* -------------------------------------------------------------------------- */

function CompanyDrawer({
  company,
  onClose,
  onPatch,
}: {
  company: CompanyOut | null;
  onClose: () => void;
  onPatch: (company: CompanyOut, changes: CompanyEdit) => void;
}) {
  const [openJob, setOpenJob] = useState<string | null>(null);

  const jobs = useResource(
    () => (company ? api.companyJobs(company.id) : Promise.resolve(null)),
    [company?.id],
  );

  const patchJob = useCallback(
    async (job: JobSummary, changes: { starred?: boolean; hidden?: boolean }) => {
      try {
        await api.updateJob(job.id, changes);
        toast.success(changes.hidden ? "Ignored" : changes.starred ? "Saved" : "Removed from saved");
        void jobs.refresh(true);
      } catch {
        toast.error("That change did not save.");
      }
    },
    [jobs],
  );

  return (
    <Drawer open={!!company} onClose={onClose} label="Employer detail">
      {company && (
        <>
          <header className="border-b border-border p-4">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-muted">
                <Building2 className="size-4 text-muted-foreground" />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-[15px] font-semibold tracking-tight">{company.name}</h2>
                <p className="mt-0.5 text-[12px] text-muted-foreground">
                  {company.industry || "industry not recorded"}
                </p>
              </div>
              {company.careers_url && (
                <Button variant="outline" size="sm" asChild>
                  <a href={company.careers_url} target="_blank" rel="noopener noreferrer">
                    Careers site <ExternalLink />
                  </a>
                </Button>
              )}
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
              <Fact label="Open roles" value={company.open_roles} />
              <Fact label="New in 7 days" value={company.new_roles_7d} />
              <Fact
                label="Last checked"
                value={company.last_checked_at ? relativeTime(company.last_checked_at) : "never"}
              />
            </div>
          </header>

          <div className="flex-1 overflow-y-auto scrollbar-thin">
            <section className="space-y-3 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-[12px] text-muted-foreground" htmlFor="tier">
                  Priority
                </label>
                <Select
                  id="tier"
                  value={company.tier}
                  onChange={(e) => onPatch(company, { tier: e.target.value as Tier })}
                  className="h-8 text-[12px]"
                >
                  {TIERS.map((tier) => (
                    <option key={tier.value} value={tier.value}>
                      {tier.label}
                    </option>
                  ))}
                </Select>

                <Button
                  variant={company.enabled ? "outline" : "default"}
                  size="sm"
                  className="ml-auto"
                  onClick={() => onPatch(company, { enabled: !company.enabled })}
                >
                  {company.enabled ? "Pause scanning" : "Resume scanning"}
                </Button>
              </div>

              <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[11.5px] text-muted-foreground">
                {company.is_automated
                  ? `Read automatically through their ${company.adapter} job feed.`
                  : company.careers_url
                    ? "This employer publishes no feed CareerOS can read, so their roles are not scanned. Open their careers site to check by hand."
                    : "This employer publishes no feed CareerOS can read, and no careers URL is recorded for them."}
              </p>

              <div>
                <label className="mb-1 block text-[12px] text-muted-foreground" htmlFor="notes">
                  Your notes
                </label>
                <Textarea
                  id="notes"
                  defaultValue={company.notes}
                  placeholder="Contacts, referrals, what you learned in a call."
                  onBlur={(e) =>
                    e.target.value !== company.notes && onPatch(company, { notes: e.target.value })
                  }
                  className="text-[12.5px]"
                />
                <p className="mt-1 text-[10.5px] text-muted-foreground">
                  Saved when you click away. Stays on this machine.
                </p>
              </div>
            </section>

            <Separator />

            <section className="p-4">
              <h3 className="mb-2 text-[12.5px] font-semibold tracking-tight">Open roles</h3>
              {jobs.loading && !jobs.data ? (
                <div className="space-y-1.5">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : !jobs.data?.items.length ? (
                <p className="py-6 text-center text-[11.5px] text-muted-foreground">
                  {company.is_automated
                    ? "Nothing open that matches your profile right now."
                    : "Nothing here — this employer is not scanned."}
                </p>
              ) : (
                <div className="rounded-md border border-border">
                  {jobs.data.items.map((job) => (
                    <JobFeedRow
                      key={job.id}
                      job={job}
                      onOpen={() => setOpenJob(job.id)}
                      onPatch={(changes) => patchJob(job, changes)}
                    />
                  ))}
                </div>
              )}
            </section>
          </div>

          <JobDrawer
            jobId={openJob}
            onClose={() => setOpenJob(null)}
            onChanged={() => void jobs.refresh(true)}
          />
        </>
      )}
    </Drawer>
  );
}

/**
 * What is known about this employer's source, in one badge.
 *
 * The adapter name goes in the tooltip rather than the label: "greenhouse"
 * tells the user nothing about whether their jobs are arriving, which is the
 * only question this column answers.
 */
function SourceBadge({ company }: { company: CompanyOut }) {
  const status = SOURCE_STATUS[company.source_status] ?? SOURCE_STATUS.manual;
  const detail = company.is_automated
    ? `${status.hint} Read through ${company.adapter}.`
    : company.discovered_from
      ? `${status.hint} Found through ${company.discovered_from}.`
      : status.hint;
  return (
    <Badge variant={status.tone} title={detail}>
      {status.label}
    </Badge>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-md border border-border px-2.5 py-1.5">
      <p className="text-[10.5px] text-muted-foreground">{label}</p>
      <p className="tabular mt-0.5 text-[13px] font-medium">{value}</p>
    </div>
  );
}
