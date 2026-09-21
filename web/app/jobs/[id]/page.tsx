import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { JobActions } from "@/components/jobs/actions";
import { ScoreBreakdown, Score, FlagBadges } from "@/components/jobs/bits";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Separator,
} from "@/components/ui/primitives";
import { postedAge, relativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const job = await api.job(decodeURIComponent(id));
    return { title: `${job.title} · ${job.company_name}` };
  } catch {
    return { title: "Job" };
  }
}

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  let job;
  try {
    job = await api.job(decodeURIComponent(id));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const facts: [string, React.ReactNode][] = [
    ["Company", job.company_name],
    ["Location", job.location_raw || job.city || "not stated"],
    ["Arrangement", job.remote_label],
    ["Employment", job.employment_type === "unknown" ? "not stated" : "Full-time"],
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
            <span className="ml-1 text-xs text-muted-foreground">(derived)</span>
          )}
        </span>
      ) : (
        "not stated"
      ),
    ],
    ["Posted", job.posted_at ? `${job.posted_at} · ${postedAge(job.age_days)}` : "not stated"],
    ["First discovered", relativeTime(job.first_seen_at)],
    ["Last verified", relativeTime(job.last_seen_at)],
    ["Seen in runs", String(job.times_seen)],
  ];

  return (
    <>
      <header className="border-b border-border px-6 py-4">
        <Button asChild variant="ghost" size="sm" className="-ml-2 mb-2 text-muted-foreground">
          <Link href="/jobs">
            <ArrowLeft />
            All jobs
          </Link>
        </Button>

        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold tracking-tight">{job.title}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {job.company_name} · {job.city || job.location_raw || "location not stated"}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {job.is_new && <Badge variant="info">NEW</Badge>}
              {job.tier === "dream" && <Badge variant="outline">◆ shortlist</Badge>}
              {!job.is_open && <Badge variant="outline">closed</Badge>}
              {job.role_category && <Badge>{job.role_category}</Badge>}
              <FlagBadges flags={job.flags} />
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <Score value={job.score} size="lg" />
              <p className="text-[11px] text-muted-foreground">match</p>
            </div>
            <Button asChild>
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                Open original
                <ExternalLink />
              </a>
            </Button>
          </div>
        </div>
      </header>

      <div className="grid gap-6 p-6 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0 space-y-6">
          {job.flags.length > 0 && (
            <Card className="border-warn/40">
              <CardHeader>
                <CardTitle>Check before you spend time on this</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {job.flags.map((flag) => (
                  <div key={flag.code} className="text-sm">
                    <Badge variant={flag.code === "DEUTSCH" ? "warn" : "danger"}>
                      {flag.code}
                    </Badge>{" "}
                    {flag.why}
                    {flag.evidence && (
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Matched on “{flag.evidence}”
                      </p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Why this matched</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {job.match_reasons.length > 0 && (
                <ul className="space-y-1">
                  {job.match_reasons.map((reason) => (
                    <li key={reason} className="flex gap-2 text-sm">
                      <span className="text-ok">+</span>
                      {reason}
                    </li>
                  ))}
                </ul>
              )}
              {job.match_gaps.length > 0 && (
                <>
                  <Separator />
                  <ul className="space-y-1">
                    {job.match_gaps.map((gap) => (
                      <li key={gap} className="flex gap-2 text-sm text-muted-foreground">
                        <span className="text-warn">−</span>
                        {gap}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {job.skills.length > 0 && (
                <>
                  <Separator />
                  <div className="flex flex-wrap gap-1">
                    {job.skills.map((skill) => (
                      <Badge key={skill} variant="outline">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {job.language_evidence && (
            <Card>
              <CardHeader>
                <CardTitle>Language requirement</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{job.language_label}</p>
                <p className="mt-1 text-xs text-muted-foreground">{job.language_evidence}</p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>The posting</CardTitle>
              {job.summary && <p className="text-xs text-muted-foreground">{job.summary}</p>}
            </CardHeader>
            <CardContent>
              {job.description ? (
                <div className="max-h-[32rem] overflow-y-auto pr-2 text-sm leading-relaxed whitespace-pre-line scrollbar-thin">
                  {job.description}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  This source publishes only a short preview. Open the original for the full
                  advertisement.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-4">
          <JobActions job={job} />

          <Card>
            <CardHeader>
              <CardTitle>Match breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              <ScoreBreakdown sub={job.sub_scores} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Facts</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-1.5 text-sm">
                {facts.map(([label, value]) => (
                  <div key={label} className="flex gap-2">
                    <dt className="w-32 shrink-0 text-xs text-muted-foreground">{label}</dt>
                    <dd className="min-w-0 flex-1 text-xs">{value}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Where this came from</CardTitle>
              <p className="text-xs text-muted-foreground">
                Every source that reported this vacancy.
              </p>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {job.sources.map((source) => (
                <a
                  key={`${source.provider}-${source.external_id}`}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between gap-2 text-xs hover:underline"
                >
                  <span className="flex items-center gap-1.5">
                    {source.provider}
                    {source.is_primary && <Badge variant="outline">primary</Badge>}
                  </span>
                  <ExternalLink className="size-3 shrink-0 text-muted-foreground" />
                </a>
              ))}
            </CardContent>
          </Card>

          {job.draft_folder && (
            <Card>
              <CardHeader>
                <CardTitle>Draft prepared</CardTitle>
              </CardHeader>
              <CardContent>
                <code className="block rounded bg-muted px-2 py-1 font-mono text-[11px] break-all">
                  data/drafts/{job.draft_folder}
                </code>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  Cover letter, the saved advertisement and a checklist. Nothing is ever
                  submitted for you.
                </p>
              </CardContent>
            </Card>
          )}

          {job.history.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>History</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {job.history.map((event, i) => (
                  <div key={i} className="text-xs">
                    <span className="text-muted-foreground">{relativeTime(event.at)}</span>{" "}
                    {event.from_status} → <strong>{event.to_status}</strong>
                    {event.note && (
                      <p className="text-muted-foreground">{event.note}</p>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </>
  );
}
