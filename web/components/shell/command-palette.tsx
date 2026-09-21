"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Briefcase,
  Building2,
  LayoutDashboard,
  Moon,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  SlidersHorizontal,
  Star,
} from "lucide-react";
import { toast } from "sonner";
import { api, type JobSummary } from "@/lib/api";
import { useDebounced, useHotkey, useScanState } from "@/lib/hooks";

interface PaletteContext {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<PaletteContext>({
  open: () => {},
  close: () => {},
  isOpen: false,
});

export const useCommandPalette = () => useContext(Ctx);

/**
 * The command palette.
 *
 * Functional, not decorative: every entry either navigates somewhere real or
 * performs an action the product actually supports. Job search runs against
 * the API, so ⌘K is a genuine way to find a role, not a list of page links.
 */
export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<JobSummary[]>([]);
  const debounced = useDebounced(query, 200);
  const router = useRouter();
  const { start } = useScanState();

  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
  }, []);

  useHotkey("k", open, { meta: true, allowInInput: true });

  useEffect(() => {
    if (!isOpen || debounced.trim().length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    api
      .jobs({ q: debounced.trim(), limit: 6, sort: "score" })
      .then((page) => !cancelled && setResults(page.items))
      .catch(() => !cancelled && setResults([]));
    return () => {
      cancelled = true;
    };
  }, [debounced, isOpen]);

  const go = useCallback(
    (href: string) => {
      close();
      router.push(href);
    },
    [close, router],
  );

  const actions = useMemo(
    () => [
      { id: "overview", label: "Go to Overview", icon: LayoutDashboard, run: () => go("/") },
      { id: "jobs", label: "Go to Jobs", icon: Briefcase, run: () => go("/jobs") },
      {
        id: "applications",
        label: "Go to Applications",
        icon: SlidersHorizontal,
        run: () => go("/applications"),
      },
      { id: "companies", label: "Go to Companies", icon: Building2, run: () => go("/companies") },
      { id: "automation", label: "Go to Automation", icon: Activity, run: () => go("/automation") },
      { id: "analytics", label: "Go to Analytics", icon: BarChart3, run: () => go("/analytics") },
      { id: "settings", label: "Go to Settings", icon: SettingsIcon, run: () => go("/settings") },
    ],
    [go],
  );

  const filters = useMemo(
    () => [
      { id: "today", label: "Jobs posted today", run: () => go("/jobs?max_age_days=1") },
      { id: "new", label: "New since last scan", run: () => go("/jobs?only_new=true") },
      { id: "high", label: "High matches (80+)", run: () => go("/jobs?min_score=80") },
      { id: "munich", label: "Munich roles", run: () => go("/jobs?q=munich") },
      { id: "germany", label: "Germany", run: () => go("/jobs?country=de") },
      { id: "swiss", label: "Switzerland", run: () => go("/jobs?country=ch") },
      { id: "english", label: "English-only roles", run: () => go("/jobs?language=english_only") },
      { id: "dream", label: "Shortlisted employers", run: () => go("/jobs?tier=dream") },
      { id: "saved", label: "Saved jobs", run: () => go("/jobs?only_starred=true") },
    ],
    [go],
  );

  return (
    <Ctx.Provider value={{ open, close, isOpen }}>
      {children}

      <Command.Dialog
        open={isOpen}
        onOpenChange={(next) => (next ? open() : close())}
        label="Command palette"
        className="fixed inset-0 z-50"
      >
        <div
          className="absolute inset-0 bg-black/50 backdrop-blur-[1px]"
          onClick={close}
          aria-hidden
        />
        <div className="absolute left-1/2 top-[18vh] w-[92vw] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover shadow-2xl">
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Search jobs, or jump to a page…"
              className="h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>

          <Command.List className="max-h-[54vh] overflow-y-auto p-1.5 scrollbar-thin">
            <Command.Empty className="px-3 py-8 text-center text-xs text-muted-foreground">
              Nothing matches “{query}”.
            </Command.Empty>

            {results.length > 0 && (
              <Command.Group heading="Jobs" className="palette-group">
                {results.map((job) => (
                  <Command.Item
                    key={job.id}
                    value={`job-${job.id}-${job.title}-${job.company_name}`}
                    onSelect={() => go(`/jobs?open=${encodeURIComponent(job.id)}`)}
                    className="palette-item"
                  >
                    <span className="tabular w-7 shrink-0 text-right text-[11px] text-muted-foreground">
                      {job.score}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{job.title}</span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {job.company_name}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            <Command.Group heading="Views" className="palette-group">
              {filters.map((item) => (
                <Command.Item
                  key={item.id}
                  value={`view ${item.label}`}
                  onSelect={item.run}
                  className="palette-item"
                >
                  <Star className="size-3.5 shrink-0 text-muted-foreground" />
                  {item.label}
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading="Navigate" className="palette-group">
              {actions.map(({ id, label, icon: Icon, run }) => (
                <Command.Item
                  key={id}
                  value={`go ${label}`}
                  onSelect={run}
                  className="palette-item"
                >
                  <Icon className="size-3.5 shrink-0 text-muted-foreground" />
                  {label}
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading="Actions" className="palette-group">
              <Command.Item
                value="run scan now refresh"
                onSelect={async () => {
                  close();
                  const result = await start();
                  if (result.ok) toast.success("Scan started");
                  else toast.warning("A scan is already running", { description: result.message });
                }}
                className="palette-item"
              >
                <RefreshCw className="size-3.5 shrink-0 text-muted-foreground" />
                Run a scan now
              </Command.Item>
              <Command.Item
                value="toggle theme dark light"
                onSelect={() => {
                  const next = !document.documentElement.classList.contains("dark");
                  document.documentElement.classList.toggle("dark", next);
                  try {
                    localStorage.setItem("careeros.theme", next ? "dark" : "light");
                  } catch {
                    /* private mode */
                  }
                  close();
                }}
                className="palette-item"
              >
                <Moon className="size-3.5 shrink-0 text-muted-foreground" />
                Toggle theme
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="flex items-center gap-3 border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <ArrowRight className="size-3" /> to select
            </span>
            <span>↑↓ to navigate</span>
            <span className="ml-auto">esc to close</span>
          </div>
        </div>
      </Command.Dialog>
    </Ctx.Provider>
  );
}
