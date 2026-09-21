import { api, ApiError, type ProviderHealthOut, type RunOut } from "@/lib/api";
import { PageHeader } from "@/components/shell/sidebar";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/primitives";
import { formatDuration, relativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Discovery" };

const STATE_TONE: Record<string, "ok" | "warn" | "danger" | "outline"> = {
  healthy: "ok",
  degraded: "warn",
  rate_limited: "warn",
  failed: "danger",
  skipped: "outline",
};

export default async function RunsPage() {
  let runs: RunOut[];
  let providers: ProviderHealthOut[];
  try {
    [runs, providers] = await Promise.all([api.runs(20), api.providers()]);
  } catch (error) {
    return (
      <>
        <PageHeader title="Discovery" />
        <div className="p-6">
          <EmptyState
            title="Cannot reach the API"
            hint={error instanceof ApiError ? error.message : "Start the stack first."}
          />
        </div>
      </>
    );
  }

  const latest = runs[0];
  const unhealthy = providers.filter((p) => p.state !== "healthy");

  return (
    <>
      <PageHeader
        title="Discovery"
        subtitle={
          latest
            ? `Last run ${relativeTime(latest.finished_at)} · ${latest.providers_ok}/${latest.providers_checked} sources answered`
            : "No runs yet"
        }
      />

      <div className="space-y-6 p-6">
        {latest && (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Postings read", latest.postings_seen],
              ["Relevant", latest.postings_relevant],
              ["New", latest.jobs_new],
              ["Updated", latest.jobs_updated],
              ["Closed", latest.jobs_closed],
              ["Duplicates merged", latest.duplicates_merged],
              ["Drafts written", latest.drafts_written],
              ["Duration", formatDuration(latest.duration_ms)],
            ].map(([label, value]) => (
              <Card key={String(label)}>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="tabular mt-1 text-xl font-semibold">{value}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Source health</CardTitle>
            <p className="max-w-2xl text-xs text-muted-foreground">
              A run that found nothing because sources broke looks identical to a run where
              nothing was posted — unless the difference is recorded. A source that fails
              repeatedly is backed off rather than retried every hour.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            {unhealthy.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-ok">
                All {providers.length} sources answered on the last run.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Source</TableHead>
                    <TableHead className="w-28">State</TableHead>
                    <TableHead className="w-20 text-right">Failures</TableHead>
                    <TableHead className="w-24">Last ok</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {unhealthy.map((p) => (
                    <TableRow key={p.key}>
                      <TableCell className="text-sm">
                        {p.target}
                        <span className="ml-1.5 text-xs text-muted-foreground">
                          {p.provider}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={STATE_TONE[p.state] ?? "outline"}>{p.state}</Badge>
                      </TableCell>
                      <TableCell className="tabular text-right text-sm">
                        {p.consecutive_failures}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {relativeTime(p.last_ok_at)}
                      </TableCell>
                      <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                        {p.last_error}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run history</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-32">Started</TableHead>
                  <TableHead className="w-20">Status</TableHead>
                  <TableHead className="w-24">Trigger</TableHead>
                  <TableHead className="w-24 text-right">Sources</TableHead>
                  <TableHead className="w-24 text-right">Read</TableHead>
                  <TableHead className="w-20 text-right">New</TableHead>
                  <TableHead className="w-24 text-right">Merged</TableHead>
                  <TableHead className="w-20 text-right">Took</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {relativeTime(run.started_at)}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          run.status === "ok"
                            ? "ok"
                            : run.status === "partial"
                              ? "warn"
                              : "danger"
                        }
                      >
                        {run.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {run.triggered_by}
                    </TableCell>
                    <TableCell className="tabular text-right text-sm">
                      {run.providers_ok}/{run.providers_checked}
                    </TableCell>
                    <TableCell className="tabular text-right text-sm">
                      {run.postings_seen.toLocaleString()}
                    </TableCell>
                    <TableCell className="tabular text-right text-sm">{run.jobs_new}</TableCell>
                    <TableCell className="tabular text-right text-sm text-muted-foreground">
                      {run.duplicates_merged}
                    </TableCell>
                    <TableCell className="tabular text-right text-xs text-muted-foreground">
                      {formatDuration(run.duration_ms)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
