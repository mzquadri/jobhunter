import type { Job } from "./types";

/** How the age of a posting is written. Sources only give day precision, so
 *  claiming "3 hours ago" would be inventing detail we do not have. */
export function postedAge(job: Job): string {
  if (job.age_days === null) return job.posted_on ?? "date not given";
  if (job.age_days <= 0) return "posted today";
  if (job.age_days === 1) return "posted yesterday";
  return `posted ${job.age_days} days ago`;
}

/** How long ago the last sweep ran. This one really is live. */
export function sinceSweep(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "no sweep yet";
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "swept just now";
  if (minutes === 1) return "swept 1 min ago";
  if (minutes < 60) return `swept ${minutes} min ago`;
  if (minutes < 120) return "swept 1 hour ago";
  return `swept ${Math.round(minutes / 60)} hours ago`;
}

export function untilNext(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const minutes = Math.round((new Date(iso).getTime() - now) / 60000);
  if (minutes <= 0) return "next sweep due";
  if (minutes === 1) return "next in 1 min";
  if (minutes < 60) return `next in ${minutes} min`;
  return `next in ${Math.round(minutes / 60)} h`;
}

/** Score bands. Green is "go", matching the cockpit convention used for flags. */
export function scoreBand(score: number): "go" | "mid" | "low" {
  if (score >= 60) return "go";
  if (score >= 35) return "mid";
  return "low";
}

export function isWarning(code: string): boolean {
  // German is a hurdle; citizenship and sponsorship are walls.
  return code !== "DEUTSCH";
}

export function duration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}
