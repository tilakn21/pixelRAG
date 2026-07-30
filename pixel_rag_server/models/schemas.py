# pixel_rag_server/models/schemas.py
"""Pydantic response models for all API endpoints."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PhotoResponse(BaseModel):
    id: int
    path: str
    filename: str
    taken_at: Optional[str] = None
    scene_category: Optional[str] = None
    scene_confidence: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    has_faces: bool = False
    person_ids: List[int] = Field(default_factory=list)
    person_names: List[str] = Field(default_factory=list)
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: Optional[str] = None
    scene_tags: List[str] = Field(default_factory=list)
    matched_face_id: Optional[int] = None
    thumbnail_url: Optional[str] = None
    lib_hash: Optional[str] = None
    semantic_score: Optional[float] = None


class PaginatedPhotos(BaseModel):
    items: List[PhotoResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class PersonResponse(BaseModel):
    id: int
    name: Optional[str] = None
    confirmed: bool = False
    purity_score: Optional[float] = None
    quality: Optional[str] = None  # "good", "fair", "poor"
    face_count: int = 0
    cover_face_url: Optional[str] = None


class SearchIntent(BaseModel):
    names: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    month: Optional[int] = None
    city: Optional[str] = None
    scene_category: Optional[str] = None
    exclusive: bool = False


class SearchResponse(BaseModel):
    query: str
    intent: SearchIntent
    results: List[PhotoResponse]
    total_count: int
    execution_time_ms: int


class SyncStatus(BaseModel):
    status: str = "idle"  # "idle", "running", "complete", "error"
    progress: int = 0
    step_name: Optional[str] = None
    step_index: int = 0
    total_steps: int = 0
    sub_progress: int = 0
    sub_message: Optional[str] = None
    current_file: Optional[str] = None  # Deprecated in favor of sub_message, but keeping for compatibility
    photos_processed: int = 0
    photos_total: int = 0
    error_message: Optional[str] = None
    logs: List[str] = Field(default_factory=list)


class SearchSuggestions(BaseModel):
    person_names: List[str] = Field(default_factory=list)
    cities: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    photo_count: int = 0
    person_count: int = 0
    library_path: str = ""
    known_libraries: List[str] = Field(default_factory=list)
    lib_hash: str = ""
    sync_version: int = 0


class HealthzResponse(BaseModel):
    """Response model for the /healthz liveness probe."""
    status: str = "ok"
    stalled_since: Optional[str] = None


class SuggestedMerge(BaseModel):
    identity_a_id: int
    identity_b_id: int
    similarity_score: float
    sample_face_a: Optional[str] = None
    sample_face_b: Optional[str] = None


class TagByPhotoResponse(BaseModel):
    person: PersonResponse
    clusters_absorbed: int
    total_photos: int
    message: str
