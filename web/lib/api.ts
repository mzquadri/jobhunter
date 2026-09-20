import type { Job, JobPage, JobQuery, Stats } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
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
    // A failed fetch here almost always means the API container is not up,
    // so say that rather than surfacing "Failed to fetch".
    throw new ApiError(`Cannot reach the API at ${BASE}. Is it running?`, 0);
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(body.slice(0, 300) || response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

function toQueryString(query: JobQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) {
      params.set(key, String(value));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const api = {
  jobs: (query: JobQuery = {}) => request<JobPage>(`/api/jobs${toQueryString(query)}`),

  job: (id: string) => request<Job>(`/api/jobs/${encodeURIComponent(id)}`),

  updateJob: (id: string, patch: Partial<Pick<Job, "starred" | "hidden" | "status" | "notes">>) =>
    request<Job>(`/api/jobs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  stats: () => request<Stats>("/api/stats"),

  runSweep: () => request<{ status: string; detail: string }>("/api/sweeps", { method: "POST" }),
};

export { ApiError };
