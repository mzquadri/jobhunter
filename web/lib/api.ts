/**
 * Typed client for the JobHunter API.
 *
 * Every type here is derived from `lib/api-types.ts`, which is generated from
 * the API's own OpenAPI document (`npm run generate:types`). The contract has
 * one definition, so the two sides cannot drift apart.
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
export type RunOut = Schemas["RunOut"];
export type RunDetail = Schemas["RunDetail"];
export type ProviderHealthOut = Schemas["ProviderHealthOut"];
export type SavedSearchOut = Schemas["SavedSearchOut"];
export type ApplicationStatus = Schemas["ApplicationStatus"];
export type Flag = Schemas["Flag"];
export type SubScores = Schemas["SubScores"];
export type NamedCount = Schemas["NamedCount"];
export type DayCount = Schemas["DayCount"];

export type JobQuery = NonNullable<operations["list_jobs_api_jobs_get"]["parameters"]["query"]>;

/**
 * Where the API lives, which is not the same answer on both sides.
 *
 * Server components run inside the `web` container, so `localhost` there is
 * the container itself, not the API. They need the compose service name.
 * The browser cannot resolve that name and needs the published host port.
 *
 * NEXT_PUBLIC_API_URL is inlined at build time and is the browser's answer;
 * API_INTERNAL_URL is read at runtime and is the server's.
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
    // A failed fetch here almost always means the API container is not up.
    // Saying so beats surfacing "Failed to fetch".
    throw new ApiError(`Cannot reach the API at ${BASE}. Is the stack running?`, 0);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
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
  jobs: (query: JobQuery = {}) => request<JobPage>(`/api/jobs${qs(query)}`),
  job: (id: string) => request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`),
  updateJob: (id: string, patch: JobPatch) =>
    request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  stats: () => request<Stats>("/api/stats"),
  companies: (query: { tier?: string; automated?: boolean } = {}) =>
    request<CompanyOut[]>(`/api/companies${qs(query)}`),
  runs: (limit = 30) => request<RunOut[]>(`/api/runs${qs({ limit })}`),
  run: (id: number) => request<RunDetail>(`/api/runs/${id}`),
  providers: () => request<ProviderHealthOut[]>("/api/providers"),
  searches: () => request<SavedSearchOut[]>("/api/searches"),
  searchResults: (id: number, limit = 100) =>
    request<JobPage>(`/api/searches/${id}/results${qs({ limit })}`),
  health: () => request<{ status: string; database: string }>("/api/health"),
};

export const STATUS_LABELS: Record<string, string> = {
  new: "New",
  reviewing: "Reviewing",
  interested: "Interested",
  to_apply: "To apply",
  applied: "Applied",
  interview: "Interview",
  technical_interview: "Technical interview",
  hr_interview: "HR interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  expired: "Expired",
  ignored: "Ignored",
};

/** The order the pipeline actually moves through. */
export const STATUS_ORDER: ApplicationStatus[] = [
  "new",
  "reviewing",
  "interested",
  "to_apply",
  "applied",
  "interview",
  "technical_interview",
  "hr_interview",
  "offer",
  "rejected",
  "withdrawn",
  "expired",
  "ignored",
];
