"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Loader2,
  Moon,
  RefreshCw,
  Search,
  Sun,
} from "lucide-react";
import { toast } from "sonner";
import { useScanState } from "@/lib/hooks";
import { cn, relativeTime, untilTime } from "@/lib/utils";
import { Button } from "@/components/ui/primitives";
import { NotificationBell } from "@/components/shell/notifications";
import { useCommandPalette } from "@/components/shell/command-palette";

/**
 * The application top bar.
 *
 * Four things only: where you are, how to find anything, whether the scanner
 * is working, and what has happened. Everything else belongs on a page.
 */
export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  const router = useRouter();
  const { open } = useCommandPalette();
  const { state, start, starting, progress } = useScanState();

  async function runScan() {
    const result = await start();
    if (result.ok) {
      toast.success("Scan started", {
        description: "Checking every source. This usually takes under a minute.",
      });
      // Give it long enough to have written something worth seeing.
      setTimeout(() => router.refresh(), 45_000);
    } else {
      toast.warning("A scan is already running", { description: result.message });
    }
  }

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-border bg-background/95 px-5 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="min-w-0">
        <h1 className="truncate text-[13px] font-semibold tracking-tight">{title}</h1>
        {subtitle && (
          <p className="truncate text-[11px] leading-tight text-muted-foreground">{subtitle}</p>
        )}
      </div>

      <button
        onClick={open}
        className="ml-auto hidden w-64 items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-ring hover:text-foreground lg:flex"
      >
        <Search className="size-3.5" />
        <span>Search or jump to…</span>
        <kbd className="ml-auto rounded border border-border px-1 py-px font-mono text-[10px]">
          ⌘K
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1 lg:ml-0">
        <ScanIndicator
          running={state?.running ?? false}
          progress={progress}
          nextAt={state?.next_run_at}
          lastAt={state?.last_finished_at}
        />

        <Button
          variant="ghost"
          size="icon"
          onClick={runScan}
          disabled={starting || state?.running}
          title={state?.running ? "A scan is already running" : "Run a scan now"}
          aria-label="Run a scan now"
        >
          {starting || state?.running ? (
            <Loader2 className="animate-spin" />
          ) : (
            <RefreshCw />
          )}
        </Button>

        <NotificationBell />
        <ThemeToggle />
      </div>
    </header>
  );
}

function ScanIndicator({
  running,
  progress,
  nextAt,
  lastAt,
}: {
  running: boolean;
  progress: number | null;
  nextAt?: string | null;
  lastAt?: string | null;
}) {
  if (running) {
    return (
      <span className="hidden items-center gap-2 rounded-md bg-info-soft px-2 py-1 text-[11px] text-info sm:flex">
        <span className="size-1.5 animate-pulse rounded-full bg-info" />
        {/* Sources completed, not an invented percentage of elapsed time. */}
        Scanning{progress !== null ? ` · ${progress}%` : "…"}
      </span>
    );
  }
  return (
    <span className="hidden px-2 text-[11px] text-muted-foreground sm:block">
      {lastAt ? `Synced ${relativeTime(lastAt)}` : "Not scanned yet"}
      {nextAt && ` · next ${untilTime(nextAt)}`}
    </span>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState<boolean | null>(null);

  // Read once on mount; the pre-paint script in layout.tsx owns the initial value.
  if (dark === null && typeof document !== "undefined") {
    setDark(document.documentElement.classList.contains("dark"));
  }

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("careeros.theme", next ? "dark" : "light");
    } catch {
      /* private mode: the toggle still works for this session */
    }
    setDark(next);
  }

  return (
    <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
      <Sun className={cn("size-4", !dark && "hidden")} />
      <Moon className={cn("size-4", dark && "hidden")} />
    </Button>
  );
}
