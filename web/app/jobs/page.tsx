import { Suspense } from "react";
import { JobExplorer } from "@/components/jobs/explorer";
import { PageHeader } from "@/components/shell/sidebar";
import { Skeleton } from "@/components/ui/primitives";

export const metadata = { title: "Jobs" };

export default function JobsPage() {
  return (
    <>
      <PageHeader
        title="Jobs"
        subtitle="Everything currently open that matches your profile"
      />
      {/*
        The explorer reads the query string so links like /jobs?min_score=70
        land pre-filtered. useSearchParams() opts a component out of static
        prerendering, so it needs a boundary for the shell to render first.
      */}
      <Suspense fallback={<ExplorerSkeleton />}>
        <JobExplorer />
      </Suspense>
    </>
  );
}

function ExplorerSkeleton() {
  return (
    <div className="space-y-3 p-6">
      <Skeleton className="h-9 w-full" />
      {Array.from({ length: 8 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
