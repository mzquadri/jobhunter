"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Briefcase,
  Building2,
  LayoutDashboard,
  Settings as SettingsIcon,
  SlidersHorizontal,
} from "lucide-react";
import { Wordmark } from "@/components/brand/logo";
import { useScanState } from "@/lib/hooks";
import { cn, relativeTime } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard, exact: true },
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/applications", label: "Applications", icon: SlidersHorizontal },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/automation", label: "Automation", icon: Activity },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Sidebar() {
  const pathname = usePathname();
  const { state } = useScanState();

  // First run gets the whole window. Navigation you cannot use yet is noise.
  if (pathname === "/onboarding") return null;

  return (
    <aside className="sticky top-0 hidden h-screen w-[208px] shrink-0 flex-col border-r border-border bg-sidebar md:flex">
      <div className="flex h-12 items-center px-3.5">
        <Link href="/" aria-label="CareerOS home">
          <Wordmark />
        </Link>
      </div>

      <nav className="flex-1 space-y-px px-2 py-1">
        {NAV.map(({ href, label, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] transition-colors",
                active
                  ? "bg-sidebar-active font-medium text-foreground"
                  : "text-muted-foreground hover:bg-sidebar-hover hover:text-foreground",
              )}
            >
              <Icon className="size-[15px] shrink-0" strokeWidth={active ? 2.1 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>

      <SystemStatus running={state?.running ?? false} lastAt={state?.last_finished_at} lastStatus={state?.last_status} />
    </aside>
  );
}

function SystemStatus({
  running,
  lastAt,
  lastStatus,
}: {
  running: boolean;
  lastAt?: string | null;
  lastStatus?: string;
}) {
  const tone =
    running ? "bg-info" : lastStatus === "ok" ? "bg-ok" : lastStatus ? "bg-warn" : "bg-muted-foreground";

  return (
    <div className="border-t border-border px-3.5 py-2.5">
      <Link
        href="/automation"
        className="flex items-center gap-2 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <span className={cn("size-1.5 shrink-0 rounded-full", tone, running && "animate-pulse")} />
        {running ? "Scanning…" : lastAt ? `Synced ${relativeTime(lastAt)}` : "Not scanned yet"}
      </Link>
      {/* Attribution, kept to one quiet line. */}
      <p className="mt-1.5 text-[10px] text-muted-foreground/60">Built by Zamin Labs</p>
    </div>
  );
}
