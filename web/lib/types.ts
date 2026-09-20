/** Mirrors api/app/schemas.py. Keep the two in step. */

export type Tier = "DREAM" | "PRIORITY" | "NORMAL";
export type SortKey = "newest" | "score" | "company";
export type JobStatus = "new" | "shortlisted" | "applied" | "rejected" | "closed";

export interface Flag {
  code: string;
  why: string;
}

export interface Job {
  id: string;
  company: string;
  title: string;
  url: string;
  location: string;
  source: string;
  tier: Tier;
  salary: string;
  posted_on: string | null;
  score: number;
  flags: Flag[];
  skills: string[];
  domains: string[];
  first_seen: string;
  last_seen: string;
  is_new: boolean;
  is_open: boolean;
  starred: boolean;
  hidden: boolean;
  status: JobStatus;
  notes: string;
  applied_on: string | null;
  draft_folder: string;
  excerpt: string;
  age_days: number | null;
}

export interface JobPage {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface DayCount {
  day: string;
  label: string;
  age_days: number;
  count: number;
}

export interface SourceProblem {
  source: string;
  detail: string;
}

export interface Sweep {
  id: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number;
  postings_fetched: number;
  matched: number;
  new_jobs: number;
  closed_jobs: number;
  drafts_written: number;
  sources_ok: number;
  sources_total: number;
  status: string;
  error: string;
  problems: SourceProblem[];
}

export interface Stats {
  total_open: number;
  fresh_48h: number;
  new_since_last_sweep: number;
  dream: number;
  no_warnings: number;
  starred: number;
  applied: number;
  max_age_days: number;
  headline: string;
  histogram: DayCount[];
  last_sweep: Sweep | null;
  next_sweep_at: string | null;
  watchlist: { name: string; url: string }[];
}

export interface JobQuery {
  q?: string;
  tier?: Tier;
  country?: "de" | "ch" | "at" | "eu";
  fresh_hours?: number;
  only_new?: boolean;
  only_starred?: boolean;
  only_clean?: boolean;
  status?: JobStatus;
  min_score?: number;
  sort?: SortKey;
  limit?: number;
}
