/**
 * Typed client for the CareerOS backend.
 *
 * Every type is derived from `lib/api-types.ts`, generated from the API's own
 * OpenAPI document (`npm run generate:types`), so the contract has one
 * definition and the two sides cannot drift apart.
 *
 * The backend is an implementation detail of this application. Nothing in the
 * product asks the user to think about it.
 */

import type { components, operations } from "./api-types";

type Schemas = components["schemas"];

export type JobSummary = Schemas["JobSummary"];
export type JobDetail = Schemas["JobDetail"];
export type JobPage = Schemas["JobPage"];
export type JobPatch = Schemas["JobPatch"];
export type Stats = Schemas["Stats"];
export type Charts = Schemas["Charts"];
export type CompanyOut = Schemas["CompanyOut"];
export type CompanyPatch = Schemas["CompanyPatch"];
export type RunOut = Schemas["RunOut"];
export type RunDetail = Schemas["RunDetail"];
export type ProviderHealthOut = Schemas["ProviderHealthOut"];
export type SavedSearchOut = Schemas["SavedSearchOut"];
export type ApplicationStatus = Schemas["ApplicationStatus"];
export type Flag = Schemas["Flag"];
export type SubScores = Schemas["SubScores"];
export type NamedCount = Schemas["NamedCount"];
export type DayCount = Schemas["DayCount"];
export type NotificationOut = Schemas["NotificationOut"];
export type NotificationPage = Schemas["NotificationPage"];
export type ScanStateOut = Schemas["ScanStateOut"];
export type SettingsOut = Schemas["SettingsOut"];
export type OnboardingState = Schemas["OnboardingState"];
export type Analytics = Schemas["Analytics"];
export type Coverage = Schemas["Coverage"];
export type CoverageBucket = Schemas["CoverageBucket"];

export type JobQuery = NonNullable<operations["list_jobs_api_jobs_get"]["parameters"]["query"]>;

/**
 * Server components run inside the web container, where `localhost` is the
 * container itself. The browser cannot resolve the compose service name.
 * Two different answers, one variable each.
 */
const BASE =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True when the backend could not be reached at all. */
  get isOffline() {
    return this.status === 0;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("CareerOS cannot reach its backend.", 0);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      /* a non-JSON error body is not worth a second failure */
    }
    throw new ApiError(detail, response.status);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function qs(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    params.set(key, String(value));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const api = {
  // jobs
  jobs: (query: JobQuery = {}) => request<JobPage>(`/api/jobs${qs(query)}`),
  job: (id: string) => request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`),
  updateJob: (id: string, patch: JobPatch) =>
    request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // overview
  stats: () => request<Stats>("/api/stats"),
  analytics: (days = 30) => request<Analytics>(`/api/analytics${qs({ days })}`),

  // companies
  companies: (
    query: {
      tier?: string;
      automated?: boolean;
      industry?: string;
      country?: string;
      source_status?: string;
    } = {},
  ) => request<CompanyOut[]>(`/api/companies${qs(query)}`),
  coverage: () => request<Coverage>("/api/coverage"),
  company: (id: string) => request<CompanyOut>(`/api/companies/${encodeURIComponent(id)}`),
  companyJobs: (id: string, includeClosed = false) =>
    request<JobPage>(
      `/api/companies/${encodeURIComponent(id)}/jobs${qs({ include_closed: includeClosed })}`,
    ),
  updateCompany: (id: string, patch: CompanyPatch) =>
    request<CompanyOut>(`/api/companies/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  // automation
  runs: (limit = 30) => request<RunOut[]>(`/api/runs${qs({ limit })}`),
  run: (id: number) => request<RunDetail>(`/api/runs/${id}`),
  providers: () => request<ProviderHealthOut[]>("/api/providers"),
  scanState: () => request<ScanStateOut>("/api/scans"),
  startScan: () => request<ScanStateOut>("/api/scans", { method: "POST" }),

  // notifications
  notifications: (limit = 30, unreadOnly = false) =>
    request<NotificationPage>(`/api/notifications${qs({ limit, unread_only: unreadOnly })}`),
  signals: (limit = 8) => request<NotificationOut[]>(`/api/notifications/signals${qs({ limit })}`),
  markRead: (id: number) =>
    request<NotificationOut>(`/api/notifications/${id}/read`, { method: "POST" }),
  markAllRead: () => request<NotificationPage>("/api/notifications/read-all", { method: "POST" }),

  // saved searches
  searches: () => request<SavedSearchOut[]>("/api/searches"),
  searchResults: (id: number, limit = 100) =>
    request<JobPage>(`/api/searches/${id}/results${qs({ limit })}`),

  // settings
  settings: () => request<SettingsOut>("/api/settings"),
  patchSettings: (patch: Record<string, unknown>) =>
    request<SettingsOut>("/api/settings", { method: "PATCH", body: JSON.stringify(patch) }),
  resetSettings: () => request<SettingsOut>("/api/settings/reset", { method: "POST" }),
  onboardingState: () => request<OnboardingState>("/api/settings/onboarding"),
  completeOnboarding: (document?: Record<string, unknown>) =>
    request<SettingsOut>("/api/settings/onboarding/complete", {
      method: "POST",
      body: JSON.stringify(document ?? null),
    }),

  health: () => request<{ status: string; database: string }>("/api/health"),
};

/* -------------------------------------------------------------------------- */
/* Vocabulary                                                                  */
/* -------------------------------------------------------------------------- */

export const STATUS_LABELS: Record<string, string> = {
  new: "New",
  reviewing: "Reviewing",
  interested: "Interested",
  to_apply: "Preparing",
  applied: "Applied",
  interview: "Recruiter screen",
  technical_interview: "Technical",
  hr_interview: "Final",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  expired: "Expired",
  ignored: "Ignored",
};

/** The pipeline board, in the order an application actually moves. */
export const PIPELINE_STAGES: ApplicationStatus[] = [
  "interested",
  "to_apply",
  "applied",
  "interview",
  "technical_interview",
  "hr_interview",
  "offer",
  "rejected",
];

export const ALL_STATUSES: ApplicationStatus[] = [
  "new",
  "reviewing",
  ...PIPELINE_STAGES,
  "withdrawn",
  "expired",
  "ignored",
];

/**
 * Match bands.
 *
 * UI categories, not claims about the employer's opinion — nothing here is
 * called a "perfect" match. The band that matters is `worth_applying`: a role
 * where you meet roughly 60% of what was described is one to apply to, because
 * a job description is a wish list rather than a minimum. The product is built
 * around that line, so the vocabulary is too.
 */
export type MatchBand =
  | "exceptional"
  | "strong"
  | "good"
  | "worth_applying"
  | "stretch"
  | "low";

/** The line at or above which applying is worth the evening. */
export const WORTH_APPLYING = 60;
/** The line at which a role goes to the top of the morning list. */
export const HIGH_PRIORITY = 80;

export function matchBand(score: number): MatchBand {
  if (score >= 90) return "exceptional";
  if (score >= HIGH_PRIORITY) return "strong";
  if (score >= 70) return "good";
  if (score >= WORTH_APPLYING) return "worth_applying";
  if (score >= 50) return "stretch";
  return "low";
}

export const MATCH_LABELS: Record<MatchBand, string> = {
  exceptional: "Exceptional match",
  strong: "Strong match",
  good: "Good match",
  worth_applying: "Worth applying",
  stretch: "Stretch",
  low: "Low relevance",
};

/** Shorter, for a table cell where the score is already visible. */
export const MATCH_LABELS_SHORT: Record<MatchBand, string> = {
  exceptional: "Exceptional",
  strong: "Strong",
  good: "Good",
  worth_applying: "Worth applying",
  stretch: "Stretch",
  low: "Low",
};

/** Whether the product should actively encourage an application. */
export function isWorthApplying(score: number): boolean {
  return score >= WORTH_APPLYING;
}
