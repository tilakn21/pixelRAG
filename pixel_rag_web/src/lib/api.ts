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
// Deduplicated on purpose. Eight separate call sites hit /api/health on mount
// purely to build the `${lib_hash}_${sync_version}` cache-buster, so a single
// page view could fire it 2-3 times (the page, plus PhotoGrid, plus
// LibrarySelector in the nav). Health also runs COUNT(*) over photos and
// people, which is not free on a 28k library. One in-flight promise is shared,
// and the result is reused briefly so a page load costs exactly one request.
let _healthPromise: Promise<HealthResponse> | null = null;
let _healthFetchedAt = 0;
const HEALTH_TTL_MS = 30_000;

export function fetchHealth(force = false): Promise<HealthResponse> {
  const now = Date.now();
  if (!force && _healthPromise && now - _healthFetchedAt < HEALTH_TTL_MS) {
    return _healthPromise;
  }
  _healthFetchedAt = now;
  _healthPromise = request<HealthResponse>("/api/health").catch((e) => {
    _healthPromise = null; // never cache a failure
    throw e;
  });
  return _healthPromise;
}

/** Call after any mutation that changes the active library or sync state. */
export function invalidateHealth() {
  _healthPromise = null;
  _healthFetchedAt = 0;
}

/** The `${lib_hash}_${sync_version}` string every media URL needs. */
export async function getLibHash(): Promise<string> {
  const h = await fetchHealth();
  return `${h.lib_hash}_${h.sync_version}`;
}

// ── Category counts ───────────────────────────────────────────────────────────
export function fetchCategoryCounts(
  libHash?: string
): Promise<{ counts: Record<string, number>; total: number }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ counts: Record<string, number>; total: number }>(
    `/api/photos/categories${sp}`
  );
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

// ── Delete & export ───────────────────────────────────────────────────────────
export type DeleteMode = "trash" | "permanent" | "forget";

export interface DeleteResult {
  requested: number;
  removed_from_library: number;
  files_affected: number;
  files_already_missing: number;
  mode: DeleteMode;
  errors: string[];
  note: string | null;
}

export function deletePhotos(
  args: { photo_ids?: number[]; person_id?: number; mode: DeleteMode },
  libHash?: string
): Promise<DeleteResult> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<DeleteResult>(`/api/photos/delete${sp}`, {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export interface ExportResult {
  folder: string;
  requested: number;
  copied: number;
  skipped_missing: number;
  errors: string[];
}

export function exportAlbum(
  args: { photo_ids?: number[]; person_id?: number; name: string; destination?: string },
  libHash?: string
): Promise<ExportResult> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<ExportResult>(`/api/albums/export${sp}`, {
    method: "POST",
    body: JSON.stringify(args),
  });
}

export type ExportSize = "original" | "web";

export interface ZipResult {
  blob: Blob;
  filename: string;
  added: number;
  skipped: number;
}

/**
 * Download the selection as a zip.
 *
 * Deliberately not routed through `request<T>()` — that helper parses JSON and
 * forces a JSON content type, and this response is binary.
 */
export async function zipAlbum(
  args: { photo_ids?: number[]; person_id?: number; name: string; size?: ExportSize },
  libHash?: string
): Promise<ZipResult> {
  const sp = libHash ? `?h=${libHash}` : "";
  const res = await fetch(`${API_URL}/api/albums/zip${sp}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) {
    let message = `Download failed (${res.status})`;
    try {
      const body = await res.json();
      message = body.detail?.error ?? body.detail ?? message;
    } catch {
      /* binary or empty body */
    }
    throw new Error(message);
  }
  return {
    blob: await res.blob(),
    filename: `${args.name || "PixelRAG"}.zip`,
    added: Number(res.headers.get("X-Photos-Added") ?? 0),
    skipped: Number(res.headers.get("X-Photos-Skipped") ?? 0),
  };
}

/** Open an exported folder in Finder. macOS only, and path-restricted server-side. */
export function revealFolder(path: string, libHash?: string): Promise<{ opened: string }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ opened: string }>(`/api/albums/reveal${sp}`, {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

/** All photo ids for a person — powers "Select all" inside a cluster. */
export function fetchPersonPhotoIds(
  personId: number,
  libHash?: string
): Promise<{ photo_ids: number[]; count: number }> {
  const sp = libHash ? `?h=${libHash}` : "";
  return request<{ photo_ids: number[]; count: number }>(
    `/api/identities/${personId}/photo-ids${sp}`
  );
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
