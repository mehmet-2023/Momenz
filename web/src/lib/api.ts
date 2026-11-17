import type {
  Event,
  EventList,
  EventPhotoList,
  Folder,
  Job,
  RegisterPayload,
  SearchResponse,
  User,
} from "./types";

const BASE = "/api/v1";
const CSRF_COOKIE = "momenz_csrf";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function cookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const found = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  return found ? decodeURIComponent(found.slice(name.length + 1)) : null;
}

export async function ensureCsrf(): Promise<void> {
  await fetch(`${BASE}/auth/csrf`, { credentials: "include" });
}

export async function apiResponse(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = cookie(CSRF_COOKIE);
    if (token) headers.set("X-CSRF-Token", token);
  }
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  return fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
}

async function parse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = data?.error || {};
    throw new ApiError(
      response.status,
      error.code || "request_failed",
      error.message || "İstek başarısız oldu.",
    );
  }
  return data as T;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  return parse<T>(await apiResponse(path, options));
}

// ------------------------------------------------------------------ auth
export const auth = {
  me: () => api<User>("/auth/me"),
  login: (email: string, password: string) =>
    api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (payload: RegisterPayload) =>
    api<{ message: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  logout: () =>
    api<{ message: string }>("/auth/logout", { method: "POST" }),
};

// ------------------------------------------------------------------ folders
export async function listFolders(): Promise<Folder[]> {
  const data = await api<{ items: Folder[] }>("/folders");
  return data.items;
}

export async function createFolder(url: string): Promise<{ folder: Folder; jobId: string }> {
  const response = await apiResponse("/folders", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
  const folder = await parse<Folder>(response);
  return {
    folder,
    jobId: response.headers.get("X-Job-ID") || "",
  };
}

export function deleteFolder(key: string): Promise<{ message: string }> {
  return api(`/folders/${encodeURIComponent(key)}`, { method: "DELETE" });
}

// ------------------------------------------------------------------ jobs
export const getJob = (id: string) => api<Job>(`/jobs/${id}`);

// ------------------------------------------------------------------ events
export type EventFilters = {
  upcoming?: boolean;
  category?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export function listEvents(filters: EventFilters = {}): Promise<EventList> {
  const params = new URLSearchParams();
  if (filters.upcoming) params.set("upcoming", "true");
  if (filters.category && filters.category !== "tumu")
    params.set("category", filters.category);
  if (filters.q) params.set("q", filters.q);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  const suffix = params.toString() ? `?${params}` : "";
  return api<EventList>(`/events${suffix}`);
}

export const getEvent = (slug: string) => api<Event>(`/events/${encodeURIComponent(slug)}`);
export const getMyEvents = () => api<EventList>("/events/mine");
export const getEventPhotos = (slug: string, limit = 24) =>
  api<EventPhotoList>(`/events/${encodeURIComponent(slug)}/photos?limit=${limit}`);

export async function createEvent(payload: {
  title: string;
  description: string;
  category: string;
  location: string;
  event_date?: string;
  url: string;
  include_subfolders: boolean;
}): Promise<{ event: Event; jobId: string }> {
  const response = await apiResponse("/events", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const event = await parse<Event>(response);
  return { event, jobId: response.headers.get("X-Job-ID") || "" };
}

export const joinEvent = (slug: string) =>
  api<{ message: string }>(`/events/${encodeURIComponent(slug)}/join`, {
    method: "POST",
  });

export const leaveEvent = (slug: string) =>
  api<{ message: string }>(`/events/${encodeURIComponent(slug)}/join`, {
    method: "DELETE",
  });

// ------------------------------------------------------------------ search
export async function searchFace(
  folderKey: string,
  file: File,
  threshold?: number,
): Promise<SearchResponse> {
  const form = new FormData();
  form.append("folder_key", folderKey);
  form.append("file", file);
  if (threshold !== undefined) form.append("threshold", String(threshold));
  return api<SearchResponse>("/search", { method: "POST", body: form });
}
