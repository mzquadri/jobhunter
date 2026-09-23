"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, PauseCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
  api,
  type IndustryProgressOut,
  type ProviderHealthOut,
  type RunDetail,
  type RunOut,
} from "@/lib/api";
import { useResource, useScanState } from "@/lib/hooks";
import {
  Badge,
  Button,
  Card,
  Drawer,
  EmptyState,
  ErrorState,
  Page,
  Progress,
  Select,
  SectionTitle,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableSkeleton,
} from "@/components/ui/primitives";
import { cn, formatDuration, relativeTime, untilTime } from "@/lib/utils";

/** Cadences worth offering. Anything below 15 minutes would just annoy sources. */
const CADENCES: { value: number; label: string }[] = [
  { value: 15, label: "Every 15 minutes" },
  { value: 30, label: "Every 30 minutes" },
  { value: 60, label: "Every hour" },
  { value: 120, label: "Every 2 hours" },
  { value: 360, label: "Every 6 hours" },
  { value: 720, label: "Twice a day" },
  { value: 1440, label: "Once a day" },
  { value: 0, label: "Only when I ask" },
];

const RUN_TONE: Record<string, "ok" | "warn" | "danger" | "info"> = {
  ok: "ok",
  success: "ok",
  partial: "warn",
  failed: "danger",
  running: "info",
};

/**
 * What the scanner is doing, and what it did.
 *
 * The one screen that admits the product has a backend. Everything here is a
 * measured number the scanner wrote down — no percentage is invented to make
 * a wait feel shorter.
 */
export function Automation() {
  const { state, start, starting, progress, refresh: refreshScan } = useScanState();
  const [openRun, setOpenRun] = useState<number | null>(null);

  const settings = useResource(() => api.settings(), []);
  const runs = useResource(() => api.runs(25), [], { pollMs: 60_000 });
  const providers = useResource(() => api.providers(), [], { pollMs: 60_000 });

  const automation = (settings.data?.profile.automation ?? {}) as {
    scan_interval_minutes?: number;
    enabled?: boolean;
    scan_on_startup?: boolean;
  };

  const setAutomation = useCallback(
    async (changes: Record<string, unknown>, message: string) => {
      try {
        const updated = await api.patchSettings({ automation: changes });
        settings.setData(updated);
        toast.success(message, { description: "The scanner picks this up on its next cycle." });
        void refreshScan();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "That change did not save.");
      }
    },
    [refreshScan, settings],
  );

  async function scanNow() {
    const result = await start();
    if (result.ok) {
      toast.success("Scan started", { description: "Sources are being read now." });
      setTimeout(() => void runs.refresh(true), 3_000);
    } else {
      toast.error(result.message);
    }
  }

  return (
    <Page className="space-y-5">
      {/* status */}
      <Card className="p-4">
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-2 text-[14px] font-semibold tracking-tight">
              {state?.running ? (
                <>
                  <Loader2 className="size-4 animate-spin text-info" /> Scanning now
                </>
              ) : automation.enabled === false || automation.scan_interval_minutes === 0 ? (
                <>
                  <PauseCircle className="size-4 text-muted-foreground" /> Scheduled scanning is off
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-4 text-ok" /> Scanning on schedule
                </>
              )}
            </h2>

            <p className="mt-1 text-[12px] text-muted-foreground">
              {state?.running
                ? `${state.providers_done} of ${state.providers_total} sources read · ` +
                  `${state.postings_seen.toLocaleString()} postings so far` +
                  (state.triggered_by ? ` · started ${state.triggered_by}` : "")
                : state?.last_finished_at
                  ? `Last scan ${relativeTime(state.last_finished_at)} and finished ${state.last_status}.`
                  : "No scan has finished yet."}
              {!state?.running && state?.next_run_at && ` Next scan ${untilTime(state.next_run_at)}.`}
            </p>

            {state?.running && progress !== null && (
              <Progress value={progress} className="mt-2.5 max-w-md" />
            )}
          </div>

          <Button onClick={scanNow} disabled={starting || state?.running} size="sm">
            <RefreshCw className={cn(state?.running && "animate-spin")} />
            {state?.running ? "Scanning" : "Scan now"}
          </Button>
        </div>

        {state?.running && state.by_industry.length > 0 && (
          <ScanBreakdown industries={state.by_industry} />
        )}
      </Card>

      {/* cadence */}
      <Card className="p-4">
        <SectionTitle
          title="Schedule"
          hint="How often CareerOS reads every source you have switched on."
        />
        {settings.loading && !settings.data ? (
          <Skeleton className="h-8 w-64" />
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={String(automation.scan_interval_minutes ?? 60)}
              aria-label="Scan frequency"
              className="h-8 text-[12.5px]"
              onChange={(e) => {
                const minutes = Number(e.target.value);
                void setAutomation(
                  { scan_interval_minutes: minutes },
                  minutes === 0
                    ? "Scheduled scanning turned off"
                    : `Scanning ${CADENCES.find((c) => c.value === minutes)?.label.toLowerCase()}`,
                );
              }}
            >
              {CADENCES.map((cadence) => (
                <option key={cadence.value} value={cadence.value}>
                  {cadence.label}
                </option>
              ))}
            </Select>

            <label className="flex items-center gap-2 text-[12.5px]">
              <input
                type="checkbox"
                className="size-3.5 accent-[var(--color-info)]"
                checked={automation.enabled !== false}
                onChange={(e) =>
                  void setAutomation(
                    { enabled: e.target.checked },
                    e.target.checked ? "Automatic scanning on" : "Automatic scanning paused",
                  )
                }
              />
              Scan automatically
            </label>

            <label className="flex items-center gap-2 text-[12.5px]">
              <input
                type="checkbox"
                className="size-3.5 accent-[var(--color-info)]"
                checked={automation.scan_on_startup !== false}
                onChange={(e) =>
                  void setAutomation(
                    { scan_on_startup: e.target.checked },
                    e.target.checked
                      ? "Will scan when CareerOS starts"
                      : "Will not scan on startup",
                  )
                }
              />
              Scan once when CareerOS starts
            </label>
          </div>
        )}
      </Card>

      {/* history */}
      <div>
        <SectionTitle
          title="Recent scans"
          hint="Every figure below was counted during the scan, not estimated."
        />
        {runs.error ? (
          <ErrorState
            title="Could not load scan history"
            message={runs.error.message}
            retry={() => void runs.refresh()}
          />
        ) : runs.loading && !runs.data ? (
          <TableSkeleton rows={6} />
        ) : !runs.data?.length ? (
          <EmptyState
            title="No scans yet"
            hint="Press Scan now above. The first scan reads every source and usually takes about a minute."
          />
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead className="w-28">Result</TableHead>
                  <TableHead className="w-24">Took</TableHead>
                  <TableHead className="w-28">Sources</TableHead>
                  <TableHead className="w-28">Postings</TableHead>
                  <TableHead className="w-24">Kept</TableHead>
                  <TableHead className="w-20">New</TableHead>
                  <TableHead className="w-24">Closed</TableHead>
                  <TableHead className="w-28">Started by</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.map((run) => (
                  <RunRow key={run.id} run={run} onOpen={() => setOpenRun(run.id)} />
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>

      {/* sources */}
      <div>
        <SectionTitle
          title="Sources"
          hint="A source that keeps failing is backed off automatically rather than hammered."
        />
        {providers.loading && !providers.data ? (
          <TableSkeleton rows={6} />
        ) : !providers.data?.length ? (
          <EmptyState
            title="No sources have reported yet"
            hint="Source health appears after the first scan."
          />
        ) : (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead className="w-28">State</TableHead>
                  <TableHead className="w-28">Success</TableHead>
                  <TableHead className="w-24">Runs</TableHead>
                  <TableHead className="w-32">Last success</TableHead>
                  <TableHead>Last problem</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {providers.data.map((provider) => (
                  <ProviderRow key={provider.key} provider={provider} />
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </div>

      <RunDrawer runId={openRun} onClose={() => setOpenRun(null)} />
    </Page>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * What the scan is actually getting through, by industry.
 *
 * Completed over total, both counted: `done` is employers that have committed
 * a result row this run, `total` is employers whose source the run intends to
 * ask. No percentage is synthesised from elapsed time — a bar that fills on a
 * timer is a lie that happens to look reassuring.
 */
function ScanBreakdown({ industries }: { industries: IndustryProgressOut[] }) {
  return (
    <div className="border-t border-border px-4 py-3">
      <p className="mb-2 text-[11px] text-muted-foreground">
        Sources completed, by industry
      </p>
      <ul className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {industries.map((industry) => {
          const complete = industry.total > 0 && industry.done >= industry.total;
          return (
            <li key={industry.key} className="flex items-center gap-2.5">
              <span className="w-24 shrink-0 truncate text-[11.5px] capitalize">
                {industry.label}
              </span>
              <span className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
                <span
                  className={cn(
                    "block h-full rounded-full transition-[width] duration-500",
                    complete ? "bg-ok" : "bg-info",
                  )}
                  style={{
                    width: `${industry.total ? (industry.done / industry.total) * 100 : 0}%`,
                  }}
                />
              </span>
              <span className="tabular w-12 shrink-0 text-right text-[11px] text-muted-foreground">
                {industry.done} / {industry.total}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function RunRow({ run, onOpen }: { run: RunOut; onOpen: () => void }) {
  return (
    <TableRow onClick={onOpen} className="cursor-pointer">
      <TableCell className="text-[12.5px]">
        {relativeTime(run.started_at)}
        {run.error && (
          <span className="mt-0.5 block truncate text-[11px] text-danger" title={run.error}>
            {run.error}
          </span>
        )}
      </TableCell>
      <TableCell>
        <Badge variant={RUN_TONE[run.status] ?? "default"}>{run.status}</Badge>
      </TableCell>
      <TableCell className="tabular text-[12px] text-muted-foreground">
        {run.finished_at ? formatDuration(run.duration_ms) : "running"}
      </TableCell>
      <TableCell className="tabular text-[12px]">
        {run.providers_ok}/{run.providers_checked}
      </TableCell>
      <TableCell className="tabular text-[12px]">{run.postings_seen.toLocaleString()}</TableCell>
      <TableCell className="tabular text-[12px]">{run.postings_relevant}</TableCell>
      <TableCell className="tabular text-[12px]">
        {run.jobs_new > 0 ? <span className="text-ok">+{run.jobs_new}</span> : "—"}
      </TableCell>
      <TableCell className="tabular text-[12px] text-muted-foreground">
        {run.jobs_closed > 0 ? run.jobs_closed : "—"}
      </TableCell>
      <TableCell className="text-[11.5px] text-muted-foreground">{run.triggered_by}</TableCell>
    </TableRow>
  );
}

function ProviderRow({ provider }: { provider: ProviderHealthOut }) {
  const failing = provider.state !== "ok" && provider.state !== "healthy";
  return (
    <TableRow>
      <TableCell>
        <span className="text-[12.5px] font-medium">{provider.provider}</span>
        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
          {provider.target}
        </span>
      </TableCell>
      <TableCell>
        <Badge variant={failing ? "warn" : "ok"}>{provider.state}</Badge>
        {provider.backoff_until && (
          <span className="mt-0.5 block text-[10.5px] text-muted-foreground">
            paused {untilTime(provider.backoff_until)}
          </span>
        )}
      </TableCell>
      <TableCell className="tabular text-[12px]">
        {provider.total_runs > 0 ? `${Math.round(provider.success_rate * 100)}%` : "—"}
      </TableCell>
      <TableCell className="tabular text-[12px] text-muted-foreground">
        {provider.total_runs}
      </TableCell>
      <TableCell className="text-[11.5px] text-muted-foreground">
        {provider.last_ok_at ? relativeTime(provider.last_ok_at) : "never"}
      </TableCell>
      <TableCell className="max-w-sm">
        {provider.last_error ? (
          <span className="flex items-start gap-1.5 text-[11px] text-muted-foreground">
            <AlertTriangle className="mt-px size-3 shrink-0 text-warn" />
            <span className="line-clamp-2">{provider.last_error}</span>
          </span>
        ) : (
          <span className="text-[11px] text-muted-foreground/60">none</span>
        )}
      </TableCell>
    </TableRow>
  );
}

/* -------------------------------------------------------------------------- */

function RunDrawer({ runId, onClose }: { runId: number | null; onClose: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (runId === null) {
      setRun(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .run(runId)
      .then((detail) => !cancelled && setRun(detail))
      .catch(() => !cancelled && toast.error("Could not load that scan."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <Drawer open={runId !== null} onClose={onClose} label="Scan detail">
      {loading && !run ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : run ? (
        <>
          <header className="border-b border-border p-4">
            <div className="flex items-center gap-2">
              <h2 className="text-[15px] font-semibold tracking-tight">Scan #{run.id}</h2>
              <Badge variant={RUN_TONE[run.status] ?? "default"}>{run.status}</Badge>
            </div>
            <p className="mt-0.5 text-[12px] text-muted-foreground">
              Started {relativeTime(run.started_at)} by {run.triggered_by} ·{" "}
              {run.finished_at ? formatDuration(run.duration_ms) : "still running"}
            </p>
            {run.error && (
              <p className="mt-2 rounded-md border border-danger/30 bg-danger-soft/40 px-2.5 py-1.5 text-[11.5px] text-danger">
                {run.error}
              </p>
            )}
          </header>

          <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
            <div className="grid grid-cols-3 gap-2">
              <Metric label="Postings read" value={run.postings_seen.toLocaleString()} />
              <Metric label="Matched your filters" value={run.postings_relevant} />
              <Metric label="Duplicates merged" value={run.duplicates_merged} />
              <Metric label="New roles" value={run.jobs_new} />
              <Metric label="Updated" value={run.jobs_updated} />
              <Metric label="Closed" value={run.jobs_closed} />
              <Metric label="Employers checked" value={run.companies_checked} />
              <Metric label="Drafts written" value={run.drafts_written} />
              <Metric label="Errors" value={run.errors_count} />
            </div>

            <h3 className="mb-2 mt-5 text-[12.5px] font-semibold tracking-tight">
              Source by source
            </h3>
            <div className="rounded-md border border-border">
              {run.providers.map((p, i) => (
                <div
                  key={`${p.provider}-${p.target}-${i}`}
                  className="flex items-center gap-3 border-b border-border px-3 py-2 last:border-0"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] font-medium">{p.provider}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {p.target}
                    </span>
                    {p.error && (
                      <span className="mt-0.5 block text-[10.5px] text-danger">{p.error}</span>
                    )}
                  </span>
                  <span className="tabular shrink-0 text-right text-[11.5px]">
                    <span className="block">{p.postings.toLocaleString()} postings</span>
                    <span className="block text-muted-foreground">
                      {p.requests_made} {p.requests_made === 1 ? "request" : "requests"} ·{" "}
                      {formatDuration(p.duration_ms)}
                    </span>
                  </span>
                  <Badge variant={p.state === "ok" ? "ok" : "warn"}>{p.state}</Badge>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </Drawer>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md border border-border px-2.5 py-2">
      <p className="text-[10.5px] text-muted-foreground">{label}</p>
      <p className="tabular mt-0.5 text-[15px] font-semibold leading-none">{value}</p>
    </div>
  );
}
