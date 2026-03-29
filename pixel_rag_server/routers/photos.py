# pixel_rag_server/routers/photos.py
"""Photos router — paginated photo listing with filters."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Query, Request

from pixel_rag_server.models.schemas import PaginatedPhotos, PhotoResponse

router = APIRouter(tags=["photos"])


def _get_people_for_photo(conn: sqlite3.Connection, photo_id: int) -> tuple[list[int], list[str]]:
    """Get all confirmed person IDs and names linked to a photo via faces."""
    rows = conn.execute(
        """
        SELECT DISTINCT p.id, p.name
        FROM faces f
        JOIN people p ON f.person_id = p.id
        WHERE f.photo_id = ? AND p.confirmed = 1
        """,
        (photo_id,),
    ).fetchall()
    ids = [r[0] for r in rows]
    names = [r[1] for r in rows]
    return ids, names


@router.get("/photos", response_model=PaginatedPhotos)
async def list_photos(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    scene_category: Optional[str] = Query(None),
    person_id: Optional[int] = Query(None),
    sort_by: str = Query("taken_at", pattern="^(taken_at|filename|scene_confidence)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """Return paginated photos with optional filtering."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
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

    items = []
    for row in rows:
        photo_id_val = row["id"]
        path = row["path"]
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        
        person_ids, person_names = _get_people_for_photo(conn, photo_id_val)

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
                person_ids=person_ids,
                person_names=person_names,
                camera_make=row["camera_make"],
                camera_model=row["camera_model"],
                latitude=row["latitude"],
                longitude=row["longitude"],
                description=row["description"],
                scene_tags=[t.strip() for t in row["scene_tags"].split(",")] if row["scene_tags"] else [],
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
