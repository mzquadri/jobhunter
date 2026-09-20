"use client";

import { useEffect, useState } from "react";
import type { Stats } from "@/lib/types";
import { sinceSweep, untilNext } from "@/lib/format";

/**
 * The header readout. This is the one place the page spends boldness: a live
 * sweep clock and a posting histogram, which together are what make the thing
 * read as an instrument rather than a list. Everything below stays quiet.
 */
export function Telemetry({
  stats,
  onSweep,
  sweeping,
}: {
  stats: Stats;
  onSweep: () => void;
  sweeping: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  const peak = Math.max(1, ...stats.histogram.map((d) => d.count));

  const cells = [
    { value: stats.fresh_48h, label: "posted in 48 hours", live: true },
    { value: stats.new_since_last_sweep, label: "new since last sweep" },
    { value: stats.total_open, label: `open, under ${stats.max_age_days} days` },
    { value: stats.dream, label: "dream companies" },
    { value: stats.starred, label: "starred" },
    { value: stats.applied, label: "applied" },
  ];

  return (
    <header className="pt-6">
      <div className="flex flex-wrap items-baseline gap-4 border-b-2 border-ink pb-3">
        <h1 className="text-[25px] font-semibold tracking-[0.17em]">JOBHUNTER</h1>
        <p className="text-[13px] text-ink-2">{stats.headline}</p>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={onSweep}
            disabled={sweeping}
            className="border border-rule px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink disabled:opacity-50"
          >
            {sweeping ? "Sweeping…" : "Sweep now"}
          </button>
          <ThemeToggle />
        </div>
      </div>

      <div className="grid grid-cols-1 border border-t-0 border-rule bg-panel lg:grid-cols-[1fr_auto]">
        <div className="flex overflow-x-auto">
          {cells.map((cell) => (
            <div
              key={cell.label}
              className="min-w-[104px] flex-1 border-r border-hair px-4 py-3 last:border-r-0"
            >
              <span
                className={`num block text-[28px] leading-none font-semibold ${
                  cell.live ? "text-live" : ""
                }`}
              >
                {cell.value}
              </span>
              <span className="mt-1.5 block text-[11.5px] text-ink-2">{cell.label}</span>
            </div>
          ))}
        </div>

        <div className="min-w-[300px] border-t border-hair px-4 py-3 lg:border-t-0 lg:border-l">
          <div className="mb-2 flex justify-between text-[11.5px] text-ink-2">
            <span>Postings per day, last {stats.max_age_days} days</span>
            <span className="flex items-center gap-2">
              <i
                className={`pulse block h-[7px] w-[7px] shrink-0 rounded-full ${
                  stats.last_sweep?.status === "ok" ? "bg-go" : "bg-caution"
                }`}
              />
              <b className="font-semibold text-ink-2">
                {sinceSweep(stats.last_sweep?.finished_at, now)}
              </b>
              {stats.next_sweep_at && (
                <span className="text-ink-3">· {untilNext(stats.next_sweep_at, now)}</span>
              )}
            </span>
          </div>
          <div className="flex h-[38px] items-end gap-[2px]">
            {stats.histogram.map((day) => (
              <span
                key={day.day}
                title={`${day.label}: ${day.count}`}
                style={{ height: `${Math.round((day.count / peak) * 100)}%` }}
                className={`relative min-h-px flex-1 ${
                  day.count === 0 ? "bg-rule" : day.age_days <= 2 ? "bg-live" : "bg-ink-2"
                }`}
              />
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("jobhunter.theme");
    if (saved === "light" || saved === "dark") {
      setTheme(saved);
      document.documentElement.setAttribute("data-theme", saved);
    }
  }, []);

  function toggle() {
    const current =
      theme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("jobhunter.theme", next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="border border-rule px-3 py-1.5 text-[13px] text-ink-2 hover:text-ink"
    >
      Theme
    </button>
  );
}
