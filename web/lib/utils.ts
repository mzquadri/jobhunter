import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Days since publication, written the way a person would say it. */
export function postedAge(ageDays: number | null | undefined, postedAt?: string | null): string {
  if (ageDays === null || ageDays === undefined) return postedAt ?? "date not given";
  if (ageDays <= 0) return "today";
  if (ageDays === 1) return "yesterday";
  return `${ageDays}d ago`;
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const minutes = Math.round((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function untilTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const minutes = Math.round((new Date(iso).getTime() - now) / 60_000);
  if (minutes <= 0) return "due now";
  if (minutes < 60) return `in ${minutes}m`;
  return `in ${Math.round(minutes / 60)}h`;
}

/** Score bands, matching the server's chart buckets exactly. */
export function scoreBand(score: number): "strong" | "good" | "fair" | "weak" {
  if (score >= 80) return "strong";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "weak";
}

export function scoreColor(score: number): string {
  const band = scoreBand(score);
  if (band === "strong") return "text-ok";
  if (band === "good") return "text-foreground";
  if (band === "fair") return "text-muted-foreground";
  return "text-muted-foreground/60";
}

/** German is a hurdle; citizenship and sponsorship are walls. */
export function isBlockingFlag(code: string): boolean {
  return code !== "DEUTSCH";
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export function compactNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}
