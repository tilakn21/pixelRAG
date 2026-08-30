# pixel_rag_server/routers/search.py
"""Search router — NLP search via Gemini intent parser."""

import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Depends
from pydantic import BaseModel

from pixel_rag_server.models.schemas import (
    PhotoResponse,
    SearchIntent,
    SearchResponse,
    SearchSuggestions,
)
from pixel_rag_server.dependencies import get_db_path, LibraryContext
from pixel_rag_server.services.library_manager import get_sync_version
from pixel_rag_server.routers.photos import parse_scene_tags
from pixel_rag_server.services.db import get_conn

router = APIRouter(tags=["search"])

def _map_photos(db_path: str, photos: list, lib_ctx: LibraryContext) -> list[PhotoResponse]:
    """Helper to convert list of raw photo dicts into PhotoResponse objects."""
    photo_responses = []
    if not photos:
        return photo_responses

    lib_hash = lib_ctx.lib_hash
    thumb_bust = f"{lib_hash}_{get_sync_version(lib_ctx.library_path)}"

    conn = get_conn(db_path, timeout=10)
    conn.row_factory = sqlite3.Row

    # Batch-load confirmed people for all result photos (avoids N+1)
    photo_ids = [photo.get("id", 0) for photo in photos]
    people_map: dict[int, list[tuple[int, str]]] = {pid: [] for pid in photo_ids}
    for i in range(0, len(photo_ids), 500):
        chunk = photo_ids[i:i + 500]
        ph = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"""
            SELECT DISTINCT f.photo_id, p.id, p.name
            FROM faces f
            JOIN people p ON f.person_id = p.id
            WHERE f.photo_id IN ({ph}) AND p.confirmed = 1
            """,
            chunk,
        ):
            people_map[r[0]].append((r[1], r[2]))

    for photo in photos:
        photo_id = photo.get("id", 0)
        path = photo.get("path", "")
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        linked = people_map.get(photo_id, [])

        photo_responses.append(
            PhotoResponse(
                id=photo_id,
                path=path,
                filename=filename,
                taken_at=photo.get("created_at"),
                scene_category=photo.get("scene_category"),
                scene_confidence=photo.get("scene_confidence"),
                city=photo.get("city"),
                state=photo.get("state"),
                country=photo.get("country"),
                has_faces=bool(photo.get("has_faces", 0)),
                person_ids=[p[0] for p in linked],
                person_names=[p[1] for p in linked],
                camera_make=photo.get("camera_make"),
                camera_model=photo.get("camera_model"),
                latitude=photo.get("latitude"),
                longitude=photo.get("longitude"),
                description=photo.get("description"),
                scene_tags=parse_scene_tags(photo.get("scene_tags")),
                thumbnail_url=f"/api/media/thumb/{photo_id}?size=400&h={thumb_bust}",
                lib_hash=lib_hash,
                semantic_score=photo.get("semantic_score")
            )
        )
    conn.close()
    return photo_responses


class SearchQuery(BaseModel):
    query: str


@router.post("/search", response_model=SearchResponse)
def search_photos(request: Request, body: SearchQuery, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Parse a natural-language query with Gemini and return matching photos."""
    db_path = lib_ctx.db_path
    start = time.time()

    try:
        from pixel_rag_core.query_engine import search as core_search

        results = core_search(db_path, body.query)
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "network" in error_msg.lower() or "api" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail={"error": f"Search service temporarily unavailable: {error_msg}"},
            )
        raise HTTPException(
            status_code=500,
            detail={"error": f"Search failed: {error_msg}"},
        )

    elapsed_ms = int((time.time() - start) * 1000)

    # Build response using helper
    photo_responses = []
    if results and "photos" in results:
        photo_responses = _map_photos(db_path, results["photos"], lib_ctx)

    # Extract the intent from core results
    intent_data = results.get("intent", {}) if results else {}
    intent = SearchIntent(
        names=intent_data.get("names", []),
        year=intent_data.get("year"),
        month=intent_data.get("month"),
        city=intent_data.get("city"),
        scene_category=intent_data.get("scene_category"),
        exclusive=intent_data.get("exclusive", False),
    )

    return SearchResponse(
        query=body.query,
        intent=intent,
        results=photo_responses,
        total_count=len(photo_responses),
        execution_time_ms=elapsed_ms,
    )


@router.post("/search/face", response_model=SearchResponse)
def search_by_face(request: Request, file: UploadFile = File(...), lib_ctx: LibraryContext = Depends(get_db_path)):
    """Search for all photos containing the face in the uploaded image."""
    db_path = lib_ctx.db_path
    start = time.time()
    
    try:
        content = file.file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Failed to read image: {e}"})

    from pixel_rag_core.faces.face_search import find_person_by_image
    
    # 1. Identity match via Gallery
    match_result = find_person_by_image(db_path, lib_ctx.library_path, content)
    if "error" in match_result:
        # Using 400 (Bad Request) instead of 404 to avoid confusion with 'path not found'
        raise HTTPException(
            status_code=400, 
            detail={"error": f"Match failed: {match_result['error']}"}
        )
        
    person_id = match_result["person_id"]
    person_name = match_result["name"]

    # 2. Query photos containing this person
    from pixel_rag_core.query_engine import GraphQueryEngine
    engine = GraphQueryEngine(db_path=db_path)
    
    sql_data = engine.build_sql(names=[person_name], date="", location="", scene_category=None, strict=True, exclusive=False)
    photos = engine.execute_query(sql_data["sql"], sql_data["params"])
    
    # 3. Build response
    photo_responses = _map_photos(db_path, photos, lib_ctx)
    
    elapsed_ms = int((time.time() - start) * 1000)
    intent = SearchIntent(names=[person_name])
    
    return SearchResponse(
        query=f"Image Search match: {person_name}",
        intent=intent,
        results=photo_responses,
        total_count=len(photo_responses),
        execution_time_ms=elapsed_ms,
    )


@router.get("/search/suggestions", response_model=SearchSuggestions)
def get_search_suggestions(request: Request, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Return person names and cities for autocomplete."""
    db_path = lib_ctx.db_path
    conn = get_conn(db_path, timeout=10)

    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM people WHERE confirmed = 1 ORDER BY name"
        ).fetchall()
    ]
    cities = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT city FROM photos WHERE city IS NOT NULL AND city != '' ORDER BY city"
        ).fetchall()
    ]

    conn.close()

    return SearchSuggestions(person_names=names, cities=cities)
