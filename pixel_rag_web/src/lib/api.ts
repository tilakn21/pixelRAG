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
  TagByPhotoResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

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
  person_ids?: string;
  sort_by?: string;
  sort_order?: string;
  libHash?: string;
}): Promise<PaginatedPhotos> {
  const sp = new URLSearchParams();
  if (params.page) sp.set("page", String(params.page));
  if (params.page_size) sp.set("page_size", String(params.page_size));
  if (params.scene_category) sp.set("scene_category", params.scene_category);
  if (params.person_id) sp.set("person_id", String(params.person_id));
  if (params.person_ids) sp.set("person_ids", params.person_ids);
  if (params.sort_by) sp.set("sort_by", params.sort_by);
  if (params.sort_order) sp.set("sort_order", params.sort_order);
  if (params.libHash) sp.set("h", params.libHash);
  return request<PaginatedPhotos>(`/api/photos?${sp.toString()}`);
}

// ── Media URL helpers (never scattered across components) ─────────────────────
export function getThumbUrl(photoId: number, size: number = 400, libHash?: string): string {
  const h = libHash ? `&h=${libHash}` : "";
  return `${API_URL}/api/media/thumb/${photoId}?size=${size}${h}`;
}

export function getPhotoUrl(photoId: number, libHash?: string): string {
  const h = libHash ? `?h=${libHash}` : "";
  return `${API_URL}/api/media/photo/${photoId}${h}`;
}

export function getFaceUrl(faceId: number, libHash?: string): string {
  const h = libHash ? `?h=${libHash}` : "";
  return `${API_URL}/api/media/face/${faceId}${h}`;
}

// ── Search ────────────────────────────────────────────────────────────────────
export function searchPhotos(query: string, libHash?: string): Promise<SearchResponse> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<SearchResponse>(`/api/search${sp}`, {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export function searchByFace(file: File, libHash?: string): Promise<SearchResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const sp = libHash ? `?h=${libHash}` : "";

  return fetch(`${API_URL}/api/search/face${sp}`, {
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

export function fetchSearchSuggestions(libHash?: string): Promise<SearchSuggestions> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<SearchSuggestions>(`/api/search/suggestions${sp}`);
}

// ── Sync ──────────────────────────────────────────────────────────────────────
export function startSync(libHash?: string): Promise<{ message: string; status: string }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ message: string; status: string }>(`/api/sync/start${sp}`, {
    method: "POST",
  });
}

export function fetchSyncStatus(libHash?: string): Promise<SyncStatus> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<SyncStatus>(`/api/sync/status${sp}`);
}

// ── Identities ────────────────────────────────────────────────────────────────
export function fetchIdentities(confirmedOnly?: boolean, libHash?: string): Promise<Person[]> {
  const sp = new URLSearchParams();
  if (confirmedOnly) sp.set("confirmed_only", "true");
  if (libHash) sp.set("h", libHash);
  const qs = sp.toString() ? `?${sp.toString()}` : "";
  return request<Person[]>(`/api/identities${qs}`);
}

export function fetchPerson(personId: number, libHash?: string): Promise<Person> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<Person>(`/api/identities/${personId}${sp}`);
}

export function renamePerson(personId: number, name: string, libHash?: string): Promise<Person> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<Person>(`/api/identities/${personId}${sp}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function mergePersons(
  targetId: number,
  sourceId: number,
  libHash?: string
): Promise<Person> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<Person>(`/api/identities/${targetId}/merge${sp}`, {
    method: "POST",
    body: JSON.stringify({ source_person_id: sourceId }),
  });
}

export function batchMergePersons(
  targetId: number,
  sourceIds: number[],
  libHash?: string
): Promise<Person> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<Person>(`/api/identities/${targetId}/batch-merge${sp}`, {
    method: "POST",
    body: JSON.stringify({ source_person_ids: sourceIds }),
  });
}

export function splitCluster(
  personId: number,
  faceIds: number[],
  libHash?: string
): Promise<{ original: Person; new: Person }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ original: Person; new: Person }>(
    `/api/identities/${personId}/split${sp}`,
    {
      method: "POST",
      body: JSON.stringify({ face_ids: faceIds }),
    }
  );
}

export function fetchSimilarPersons(personId: number, libHash?: string): Promise<Person[]> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<Person[]>(`/api/identities/${personId}/similar${sp}`);
}

export function fetchPersonFaces(
  personId: number,
  libHash?: string
): Promise<{ face_ids: number[] }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ face_ids: number[] }>(
    `/api/identities/${personId}/faces${sp}`
  );
}

export function deletePerson(personId: number, libHash?: string): Promise<{ message: string; person_id: number }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ message: string; person_id: number }>(`/api/identities/${personId}${sp}`, {
    method: "DELETE",
  });
}

export function batchDissolve(personIds: number[], libHash?: string): Promise<{ message: string }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ message: string }>(`/api/identities/batch-delete${sp}`, {
    method: "POST",
    body: JSON.stringify({ person_ids: personIds }),
  });
}

export function tagByPhoto(file: File, name: string, libHash?: string): Promise<TagByPhotoResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("name", name);
  const sp = libHash ? `?h=${libHash}` : "";

  return fetch(`${API_URL}/api/identities/tag-by-photo${sp}`, {
    method: "POST",
    body: formData,
    // Note: Don't set Content-Type header, fetch will set it with boundary
  }).then(async (res) => {
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail?.error ?? body.detail ?? "Tag by photo failed");
    }
    return res.json();
  });
}

// ── Config ────────────────────────────────────────────────────────────────────
export function setLibraryPath(path: string): Promise<{ status: string; library_path: string; db_path: string }> {
  return request<{ status: string; library_path: string; db_path: string }>("/api/config/library", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function fetchLibraries(): Promise<{ libraries: string[] }> {
  return request<{ libraries: string[] }>("/api/config/libraries");
}

export function browseLibrary(): Promise<{ path: string | null }> {
  return request<{ path: string | null }>("/api/config/browse", {
    method: "POST",
  });
}

export function deleteLibrary(path: string, wipeData: boolean = false): Promise<{ status: string; deleted: string }> {
  const sp = new URLSearchParams();
  sp.set("path", path);
  if (wipeData) sp.set("wipe_data", "true");
  return request<{ status: string; deleted: string }>(`/api/config/library?${sp.toString()}`, {
    method: "DELETE",
  });
}
