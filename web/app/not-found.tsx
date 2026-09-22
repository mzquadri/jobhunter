import Link from "next/link";
import { Mark } from "@/components/brand/logo";
import { Button } from "@/components/ui/primitives";

export const metadata = { title: "Not found" };

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-1 items-center justify-center p-8">
      <div className="flex max-w-sm flex-col items-center text-center">
        <Mark className="size-8 text-muted-foreground" />
        <p className="tabular mt-5 text-[13px] font-medium text-muted-foreground">404</p>
        <h1 className="mt-1 text-lg font-semibold tracking-tight">Nothing here</h1>
        <p className="mt-2 text-[13px] text-muted-foreground">
          That page does not exist. A job you are looking for may also have closed — closed
          roles stay in Jobs, with the date they were removed.
        </p>
        <div className="mt-5 flex gap-2">
          <Button asChild size="sm">
            <Link href="/">Back to Overview</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href="/jobs">Browse jobs</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
