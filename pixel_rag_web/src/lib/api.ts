// pixel_rag_web/src/lib/api.ts
/**
 * Typed API client for the PixelRAG FastAPI backend.
 * All fetch calls are centralized here with error handling.
 */

import type {
  HealthResponse,
  PaginatedPhotos,
  Person,
  SearchResponse,
  SearchSuggestions,
  SyncStatus,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body.detail?.error ?? body.detail ?? message;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

// ── Health ────────────────────────────────────────────────────────────────────
export function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

// ── Photos ────────────────────────────────────────────────────────────────────
export function fetchPhotos(params: {
  page?: number;
  page_size?: number;
  scene_category?: string;
  person_id?: number;
  sort_by?: string;
  sort_order?: string;
}): Promise<PaginatedPhotos> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.page_size) sp.set("page_size", String(params.page_size));
  if (params.scene_category) sp.set("scene_category", params.scene_category);
  if (params.person_id) sp.set("person_id", String(params.person_id));
  if (params.sort_by) sp.set("sort_by", params.sort_by);
  if (params.sort_order) sp.set("sort_order", params.sort_order);
  return request<PaginatedPhotos>(`/api/photos?${sp.toString()}`);
}

// ── Media URL helpers (never scattered across components) ─────────────────────
export function getThumbUrl(photoId: number, size: number = 400): string {
  return `${API_URL}/api/media/thumb/${photoId}?size=${size}`;
}

export function getPhotoUrl(photoId: number): string {
  return `${API_URL}/api/media/photo/${photoId}`;
}

export function getFaceUrl(faceId: number): string {
  return `${API_URL}/api/media/face/${faceId}`;
}

// ── Search ────────────────────────────────────────────────────────────────────
export function searchPhotos(query: string): Promise<SearchResponse> {
  return request<SearchResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export function searchByFace(file: File): Promise<SearchResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return fetch(`${API_URL}/api/search/face`, {
    method: "POST",
    body: formData,
    // Note: Don't set Content-Type header, fetch will set it with boundary
  }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail?.error ?? body.detail ?? "Upload failed");
    }
    return res.json();
  });
}

export function fetchSearchSuggestions(): Promise<SearchSuggestions> {
  return request<SearchSuggestions>("/api/search/suggestions");
}

// ── Sync ──────────────────────────────────────────────────────────────────────
export function startSync(): Promise<{ message: string; status: string }> {
  return request<{ message: string; status: string }>("/api/sync/start", {
    method: "POST",
  });
}

export function fetchSyncStatus(): Promise<SyncStatus> {
  return request<SyncStatus>("/api/sync/status");
}

// ── Identities ────────────────────────────────────────────────────────────────
export function fetchIdentities(confirmedOnly?: boolean): Promise<Person[]> {
  const sp = confirmedOnly ? "?confirmed_only=true" : "";
  return request<Person[]>(`/api/identities${sp}`);
}

export function fetchPerson(personId: number): Promise<Person> {
  return request<Person>(`/api/identities/${personId}`);
}

export function renamePerson(personId: number, name: string): Promise<Person> {
  return request<Person>(`/api/identities/${personId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function mergePersons(
  targetId: number,
  sourceId: number
): Promise<Person> {
  return request<Person>(`/api/identities/${targetId}/merge`, {
    method: "POST",
    body: JSON.stringify({ source_person_id: sourceId }),
  });
}

export function splitCluster(
  personId: number,
  faceIds: number[]
): Promise<{ original: Person; new: Person }> {
  return request<{ original: Person; new: Person }>(
    `/api/identities/${personId}/split`,
    {
      method: "POST",
      body: JSON.stringify({ face_ids: faceIds }),
    }
  );
}

export function fetchSimilarPersons(personId: number): Promise<Person[]> {
  return request<Person[]>(`/api/identities/${personId}/similar`);
}

export function fetchPersonFaces(
  personId: number
): Promise<{ face_ids: number[] }> {
  return request<{ face_ids: number[] }>(
    `/api/identities/${personId}/faces`
  );
}

// ── Config ────────────────────────────────────────────────────────────────────
export function setLibraryPath(path: string): Promise<{ status: string; library_path: string; db_path: string }> {
  return request<{ status: string; library_path: string; db_path: string }>("/api/config/library", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}
