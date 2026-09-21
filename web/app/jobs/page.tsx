import { Suspense } from "react";
import { JobExplorer } from "@/components/jobs/explorer";
import { TopBar } from "@/components/shell/topbar";
import { Page, TableSkeleton } from "@/components/ui/primitives";

export const metadata = { title: "Jobs" };

export default function JobsPage() {
  return (
    <>
      <TopBar title="Jobs" subtitle="Everything open that matches your profile" />
      {/*
        The explorer reads the query string, so links like /jobs?min_score=80
        land pre-filtered and the command palette can deep-link into a view.
        useSearchParams opts out of static prerendering, hence the boundary.
      */}
      <Suspense
        fallback={
          <Page>
            <TableSkeleton rows={12} />
          </Page>
        }
      >
        <JobExplorer />
      </Suspense>
    </>
  );
}
