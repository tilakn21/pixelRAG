# pixel_rag_server/routers/search.py
"""Search router — NLP search via Gemini intent parser."""

import sqlite3
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel

from pixel_rag_server.models.schemas import (
    PhotoResponse,
    SearchIntent,
    SearchResponse,
    SearchSuggestions,
)

router = APIRouter(tags=["search"])

def _map_photos(db_path: str, photos: list) -> list[PhotoResponse]:
    """Helper to convert list of raw photo dicts into PhotoResponse objects."""
    photo_responses = []
    if not photos:
        return photo_responses

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    for photo in photos:
        photo_id = photo.get("id", 0)
        path = photo.get("path", "")
        filename = path.rsplit("/", 1)[-1] if "/" in path else path

        person_rows = conn.execute(
            """
            SELECT DISTINCT p.id, p.name 
            FROM faces f
            JOIN people p ON f.person_id = p.id
            WHERE f.photo_id = ? AND p.confirmed = 1 AND f.person_id IS NOT NULL
            """,
            (photo_id,),
        ).fetchall()

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
                person_ids=[r[0] for r in person_rows],
                person_names=[r[1] for r in person_rows],
                camera_make=photo.get("camera_make"),
                camera_model=photo.get("camera_model"),
            )
        )
    conn.close()
    return photo_responses


class SearchQuery(BaseModel):
    query: str


@router.post("/search", response_model=SearchResponse)
async def search_photos(request: Request, body: SearchQuery):
    """Parse a natural-language query with Gemini and return matching photos."""
    db_path = request.app.state.db_path
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
        photo_responses = _map_photos(db_path, results["photos"])

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
async def search_by_face(request: Request, file: UploadFile = File(...)):
    """Search for all photos containing the face in the uploaded image."""
    db_path = request.app.state.db_path
    start = time.time()
    
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Failed to read image: {e}"})

    from pixel_rag_core.faces.face_search import find_person_by_image
    
    # 1. Identity match via Gallery
    match_result = find_person_by_image(db_path, content)
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
    photo_responses = _map_photos(db_path, photos)
    
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
async def get_search_suggestions(request: Request):
    """Return person names and cities for autocomplete."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")

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
