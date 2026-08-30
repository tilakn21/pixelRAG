# pixel_rag_server/routers/photos.py
"""Photos router — paginated photo listing with filters."""

import json
import sqlite3
from typing import Optional

from fastapi import APIRouter, Query, Request, Depends
from pixel_rag_server.models.schemas import PaginatedPhotos, PhotoResponse
from pixel_rag_server.dependencies import get_db_path, LibraryContext
from pixel_rag_server.services.library_manager import get_sync_version
from pixel_rag_server.services.db import get_conn

router = APIRouter(tags=["photos"])


def parse_scene_tags(raw: Optional[str]) -> list[str]:
    """
    scene_tags is stored as JSON top-3 [{"category": ..., "score": ...}];
    legacy rows may hold a plain CSV string. Return clean tag names either way.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [d["category"] for d in data if isinstance(d, dict) and "category" in d]
    except (ValueError, TypeError):
        pass
    return [t.strip() for t in raw.split(",") if t.strip()]


# `def`, not `async def` — blocking sqlite work belongs in the threadpool, not
# on the event loop. See the note in routers/media.py.
@router.get("/photos/categories")
def category_counts(request: Request, lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Photo count per scene category, for the category pills.

    One grouped query rather than a COUNT per pill. Lets the UI show sizes and
    hide categories this library has none of, instead of rendering a dozen
    empty buckets.
    """
    conn = get_conn(lib_ctx.db_path, timeout=10)
    try:
        rows = conn.execute(
            "SELECT scene_category, COUNT(*) FROM photos "
            "WHERE scene_category IS NOT NULL GROUP BY scene_category"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    finally:
        conn.close()
    return {"counts": {r[0]: r[1] for r in rows}, "total": total}


@router.get("/photos", response_model=PaginatedPhotos)
def list_photos(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    scene_category: Optional[str] = Query(None),
    person_id: Optional[int] = Query(None),
    person_ids: Optional[str] = Query(None, description="Comma-separated list of person IDs to require ALL to be present"),
    sort_by: str = Query("taken_at", pattern="^(taken_at|filename|scene_confidence)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    lib_ctx: LibraryContext = Depends(get_db_path),
):
    """Return paginated photos with optional filtering."""
    db_path = lib_ctx.db_path
    conn = get_conn(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    # Build query
    where_clauses = []
    params: list = []

    if scene_category == "people":
        where_clauses.append("(p.has_faces = 1 OR p.scene_category = 'people')")
    elif scene_category:
        where_clauses.append("p.scene_category = ?")
        params.append(scene_category)

    if person_id is not None:
        where_clauses.append(
            "p.id IN (SELECT photo_id FROM faces WHERE person_id = ?)"
        )
        params.append(person_id)
        
    if person_ids is not None:
        try:
            ids = [int(x.strip()) for x in person_ids.split(",")]
            for pid in ids:
                where_clauses.append(
                    "p.id IN (SELECT photo_id FROM faces WHERE person_id = ?)"
                )
                params.append(pid)
        except ValueError:
            pass

    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = "WHERE " + where_sql

    # Map sort_by to actual column
    sort_col_map = {
        "taken_at": "p.created_at",
        "filename": "p.path",
        "scene_confidence": "p.scene_confidence",
    }
    sort_col = sort_col_map.get(sort_by, "p.created_at")

    # Count total
    count_sql = f"SELECT COUNT(*) FROM photos p {where_sql}"
    total = conn.execute(count_sql, params).fetchone()[0]

    # Fetch page
    offset = (page - 1) * page_size
    data_sql = f"""
        SELECT p.id, p.path, p.created_at, p.scene_category, p.scene_confidence,
               p.city, p.state, p.country, p.has_faces, p.camera_make, p.camera_model,
               p.description, p.scene_tags, p.latitude, p.longitude
        FROM photos p
        {where_sql}
        ORDER BY {sort_col} {sort_order.upper()} NULLS LAST
        LIMIT ? OFFSET ?
    """
    rows = conn.execute(data_sql, params + [page_size, offset]).fetchall()

    # Batch-load linked people and matched faces for the whole page
    # (previously one query per photo — N+1 on every page load).
    page_photo_ids = [row["id"] for row in rows]
    people_map: dict[int, list[tuple[int, str]]] = {pid: [] for pid in page_photo_ids}
    matched_face_map: dict[int, int] = {}

    if page_photo_ids:
        ph = ",".join("?" * len(page_photo_ids))
        people_rows = conn.execute(
            f"""
            SELECT DISTINCT f.photo_id, p.id, p.name
            FROM faces f
            JOIN people p ON f.person_id = p.id
            WHERE f.photo_id IN ({ph})
            """,
            page_photo_ids,
        ).fetchall()
        for r in people_rows:
            people_map[r[0]].append((r[1], r[2]))

        # If filtering by person, find one face ID per photo for UI alignment
        if person_id is not None:
            face_rows = conn.execute(
                f"SELECT photo_id, MIN(id) FROM faces WHERE person_id = ? "
                f"AND photo_id IN ({ph}) GROUP BY photo_id",
                [person_id, *page_photo_ids],
            ).fetchall()
            matched_face_map = {r[0]: r[1] for r in face_rows}

    # Include sync generation in thumb URLs so browsers refetch after re-syncs
    thumb_bust = f"{lib_ctx.lib_hash}_{get_sync_version(lib_ctx.library_path)}"

    items = []
    for row in rows:
        photo_id_val = row["id"]
        path = row["path"]
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        linked = people_map.get(photo_id_val, [])

        items.append(
            PhotoResponse(
                id=photo_id_val,
                path=path,
                filename=filename,
                taken_at=row["created_at"],
                scene_category=row["scene_category"],
                scene_confidence=row["scene_confidence"],
                city=row["city"],
                state=row["state"],
                country=row["country"],
                has_faces=bool(row["has_faces"]),
                person_ids=[p[0] for p in linked],
                person_names=[p[1] for p in linked],
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                description=row["description"],
                scene_tags=parse_scene_tags(row["scene_tags"]),
                matched_face_id=matched_face_map.get(photo_id_val),
                thumbnail_url=f"/api/media/thumb/{photo_id_val}?size=400&h={thumb_bust}",
                lib_hash=lib_ctx.lib_hash
            )
        )

    conn.close()

    return PaginatedPhotos(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size < total),
    )
