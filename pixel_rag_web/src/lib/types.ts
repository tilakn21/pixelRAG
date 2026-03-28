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
  current_file: string | null;
  photos_processed: number;
  photos_total: number;
  error_message: string | null;
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
}
