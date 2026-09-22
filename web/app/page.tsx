import { Suspense } from "react";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { Overview } from "@/components/overview/overview";
import { TopBar } from "@/components/shell/topbar";
import { Page, Skeleton } from "@/components/ui/primitives";

export const metadata = { title: "Overview" };

export default async function OverviewPage() {
  /*
    Checked on the server so a first-time visitor never sees an empty dashboard
    flash before the wizard. A backend that is still starting is not a reason
    to send anyone to setup, so only a clear "not onboarded" redirects.
  */
  let onboarded = true;
  try {
    onboarded = (await api.onboardingState()).onboarded;
  } catch {
    /* the overview shows its own connection error */
  }
  // Outside the try on purpose: redirect() signals by throwing, and a catch
  // around it would swallow the redirect instead of performing it.
  if (!onboarded) redirect("/onboarding");

  return (
    <>
      <TopBar title="Overview" />
      <Suspense fallback={<OverviewSkeleton />}>
        <Overview />
      </Suspense>
    </>
  );
}

function OverviewSkeleton() {
  return (
    <Page className="space-y-4">
      <Skeleton className="h-16 w-full max-w-md" />
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Skeleton className="h-96" />
        <Skeleton className="h-96" />
      </div>
    </Page>
  );
}
