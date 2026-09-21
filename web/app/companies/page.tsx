import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { api, ApiError, type CompanyOut } from "@/lib/api";
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
import { relativeTime } from "@/lib/utils";

export const dynamic = "force-dynamic";
export const metadata = { title: "Companies" };

const TIER_LABEL: Record<string, string> = {
  dream: "Shortlist",
  high: "High priority",
  normal: "Normal",
  ignored: "Ignored",
};

export default async function CompaniesPage() {
  let companies: CompanyOut[];
  try {
    companies = await api.companies();
  } catch (error) {
    return (
      <>
        <PageHeader title="Companies" />
        <div className="p-6">
          <EmptyState
            title="Cannot reach the API"
            hint={error instanceof ApiError ? error.message : "Start the stack first."}
          />
        </div>
      </>
    );
  }

  const automated = companies.filter((c) => c.is_automated);
  const manual = companies.filter((c) => !c.is_automated);

  return (
    <>
      <PageHeader
        title="Companies"
        subtitle={`${automated.length} checked automatically, ${manual.length} by hand`}
      />

      <div className="space-y-6 p-6">
        <Card>
          <CardHeader>
            <CardTitle>Checked every hour</CardTitle>
            <p className="text-xs text-muted-foreground">
              Employers with a readable careers endpoint. Adding one is a line in
              <code className="mx-1 font-mono">config/profile.yml</code>.
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="min-w-44">Company</TableHead>
                  <TableHead className="w-28">Priority</TableHead>
                  <TableHead className="w-28">Industry</TableHead>
                  <TableHead className="w-28">Source</TableHead>
                  <TableHead className="w-24 text-right">Open roles</TableHead>
                  <TableHead className="w-24 text-right">New this week</TableHead>
                  <TableHead className="w-28">Last checked</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {automated.map((company) => (
                  <TableRow key={company.id}>
                    <TableCell className="text-sm font-medium">
                      {company.open_roles > 0 ? (
                        <Link
                          href={`/jobs?company=${encodeURIComponent(company.name)}`}
                          className="hover:underline"
                        >
                          {company.name}
                        </Link>
                      ) : (
                        company.name
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={company.tier === "dream" ? "info" : "outline"}>
                        {TIER_LABEL[company.tier] ?? company.tier}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {company.industry || "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {company.adapter}
                    </TableCell>
                    <TableCell className="tabular text-right text-sm">
                      {company.open_roles || <span className="text-muted-foreground">0</span>}
                    </TableCell>
                    <TableCell className="tabular text-right text-sm">
                      {company.new_roles_7d ? (
                        <span className="text-ok">{company.new_roles_7d}</span>
                      ) : (
                        <span className="text-muted-foreground">0</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {relativeTime(company.last_checked_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Checked by hand</CardTitle>
            <p className="max-w-2xl text-xs text-muted-foreground">
              These render their listings with JavaScript and publish no open feed, so nothing
              can read them automatically. They are listed rather than omitted, because a
              silently missing employer looks the same as one with no vacancies.
            </p>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {manual.map((company) => (
                <li key={company.id}>
                  <a
                    href={company.careers_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-accent"
                  >
                    <span className="min-w-0 truncate">{company.name}</span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {company.tier === "dream" && <Badge variant="outline">◆</Badge>}
                      <ExternalLink className="size-3 text-muted-foreground" />
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
