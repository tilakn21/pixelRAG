// pixel_rag_web/src/lib/types.ts

export type SceneCategory =
  | "landscape"
  | "document"
  | "food"
  | "architecture"
  | "people"
  | "other";

export type PersonQuality = "good" | "fair" | "poor";

export interface Photo {
  id: number;
  path: string;
  filename: string;
  taken_at: string | null;
  scene_category: string | null;
  scene_confidence: number | null;
  city: string | null;
  state: string | null;
  country: string | null;
  has_faces: boolean;
  person_ids: number[];
  person_names: string[];
  camera_make: string | null;
  camera_model: string | null;
  latitude: number | null;
  longitude: number | null;
  description: string | null;
  scene_tags: string[];
  matched_face_id?: number | null;
  thumbnail_url?: string | null;
  lib_hash?: string | null;
  semantic_score?: number | null;
}

export interface PaginatedPhotos {
  items: Photo[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface Person {
  id: number;
  name: string | null;
  confirmed: boolean;
  purity_score: number | null;
  quality: PersonQuality | null;
  face_count: number;
  cover_face_url: string | null;
}

export interface SearchIntent {
  names: string[];
  year: number | null;
  month: number | null;
  city: string | null;
  scene_category: string | null;
  exclusive: boolean;
}

export interface SearchResponse {
  query: string;
  intent: SearchIntent;
  results: Photo[];
  total_count: number;
  execution_time_ms: number;
}

export interface SyncStatus {
  status: "idle" | "running" | "complete" | "error";
  progress: number;
  step_name: string | null;
  step_index: number;
  total_steps: number;
  sub_progress: number;
  sub_message: string | null;
  current_file: string | null;
  photos_processed: number;
  photos_total: number;
  error_message: string | null;
  logs: string[];
}

export interface SearchSuggestions {
  person_names: string[];
  cities: string[];
}

export interface HealthResponse {
  status: string;
  photo_count: number;
  person_count: number;
  library_path: string;
  known_libraries: string[];
  lib_hash: string;
  sync_version: number;
}

export interface TagByPhotoResponse {
  person: Person;
  clusters_absorbed: number;
  total_photos: number;
  message: string;
}
