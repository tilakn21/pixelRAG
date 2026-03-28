# pixel_rag_server/routers/identities.py
"""Identities router — CRUD, merge, and split for face clusters."""

import sqlite3

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from pixel_rag_core.faces.cluster_faces import update_person_profile
from pixel_rag_server.models.schemas import PersonResponse

router = APIRouter(tags=["identities"])


def _person_from_row(row: dict, db_path: str) -> PersonResponse:
    """Build a PersonResponse from a database row."""
    person_id = row["id"]
    purity = row["purity_score"]

    # Derive quality level
    quality = None
    if purity is not None:
        if purity > 0.72:
            quality = "good"
        elif purity >= 0.60:
            quality = "fair"
        else:
            quality = "poor"

    # Get face count
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    face_count = conn.execute(
        "SELECT COUNT(*) FROM faces WHERE person_id = ?", (person_id,)
    ).fetchone()[0]

    # Get cover face ID
    cover_face = conn.execute(
        "SELECT id FROM faces WHERE person_id = ? LIMIT 1", (person_id,)
    ).fetchone()
    conn.close()

    cover_url = f"/api/media/face/{cover_face[0]}" if cover_face else None

    return PersonResponse(
        id=person_id,
        name=row["name"],
        confirmed=bool(row["confirmed"]),
        purity_score=purity,
        quality=quality,
        face_count=face_count,
        cover_face_url=cover_url,
    )


@router.get("/identities", response_model=list[PersonResponse])
async def list_identities(
    request: Request,
    confirmed_only: bool = Query(False),
):
    """List all persons ordered by face count descending."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    query = """
        SELECT p.* 
        FROM people p
        WHERE (p.confirmed = 1 OR (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) >= 2)
    """
    params: list = []

    if confirmed_only:
        query += " AND p.confirmed = 1"

    # Order by face count descending
    query += """
        ORDER BY (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) DESC
    """

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [_person_from_row(dict(row), db_path) for row in rows]

@router.get("/identities/{person_id}", response_model=PersonResponse)
async def get_person_details(request: Request, person_id: int):
    """Fetch details for a single person cluster."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    return _person_from_row(dict(row), db_path)


class RenameBody(BaseModel):
    name: str


@router.patch("/identities/{person_id}", response_model=PersonResponse)
async def rename_person(request: Request, person_id: int, body: RenameBody):
    """Update a person's name and mark as confirmed."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Verify person exists
    row = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    conn.execute(
        "UPDATE people SET name = ?, confirmed = 1 WHERE id = ?",
        (body.name.strip(), person_id),
    )
    # Recompute profile to pick a representative face for the search gallery
    update_person_profile(conn, person_id)
    conn.commit()

    updated = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    return _person_from_row(dict(updated), db_path)


class MergeBody(BaseModel):
    source_person_id: int


@router.post("/identities/{person_id}/merge", response_model=PersonResponse)
async def merge_persons(request: Request, person_id: int, body: MergeBody):
    """Merge another cluster into this person."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    target = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    source = conn.execute(
        "SELECT * FROM people WHERE id = ?", (body.source_person_id,)
    ).fetchone()

    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Target person not found"})
    if not source:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Source person not found"})

    # Reassign all faces from source to target
    conn.execute(
        "UPDATE faces SET person_id = ? WHERE person_id = ?",
        (person_id, body.source_person_id),
    )
    # Update clusters
    conn.execute(
        "UPDATE clusters SET person_id = ? WHERE person_id = ?",
        (person_id, body.source_person_id),
    )
    # Delete source person
    conn.execute("DELETE FROM people WHERE id = ?", (body.source_person_id,))
    conn.commit()

    # Recompute centroid and purity for the merged person
    update_person_profile(conn, person_id)
    conn.commit()

    updated = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    return _person_from_row(dict(updated), db_path)


class SplitBody(BaseModel):
    face_ids: list[int]


@router.post("/identities/{person_id}/split")
async def split_cluster(request: Request, person_id: int, body: SplitBody):
    """Split selected faces into a new, unconfirmed person."""
    db_path = request.app.state.db_path

    if not body.face_ids:
        raise HTTPException(status_code=400, detail={"error": "No faces to split"})

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Create new person
    cur = conn.execute(
        "INSERT INTO people (name, confirmed) VALUES (?, 0)",
        (f"Split_from_{person_id}",),
    )
    new_person_id = cur.lastrowid

    # Move selected faces
    placeholders = ",".join("?" for _ in body.face_ids)
    conn.execute(
        f"UPDATE faces SET person_id = ? WHERE id IN ({placeholders})",
        [new_person_id] + body.face_ids,
    )
    conn.commit()

    # Recompute both centroids
    update_person_profile(conn, person_id)
    update_person_profile(conn, new_person_id)
    conn.commit()

    original = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    new_person = conn.execute(
        "SELECT * FROM people WHERE id = ?", (new_person_id,)
    ).fetchone()
    conn.close()

    return {
        "original": _person_from_row(dict(original), db_path),
        "new": _person_from_row(dict(new_person), db_path),
    }


@router.get("/identities/{person_id}/similar", response_model=list[PersonResponse])
async def get_similar_clusters(request: Request, person_id: int):
    """Get top 5 similar unconfirmed clusters by centroid cosine similarity."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    target = conn.execute(
        "SELECT centroid_embedding FROM people WHERE id = ?", (person_id,)
    ).fetchone()

    if not target or not target["centroid_embedding"]:
        conn.close()
        return []

    target_vec = np.frombuffer(target["centroid_embedding"], dtype=np.float32)
    target_vec = target_vec / (np.linalg.norm(target_vec) + 1e-10)

    # Get all unconfirmed persons with centroids
    candidates = conn.execute(
        "SELECT * FROM people WHERE confirmed = 0 AND id != ? AND centroid_embedding IS NOT NULL",
        (person_id,),
    ).fetchall()

    similarities = []
    for c in candidates:
        c_vec = np.frombuffer(c["centroid_embedding"], dtype=np.float32)
        c_vec = c_vec / (np.linalg.norm(c_vec) + 1e-10)
        sim = float(np.dot(target_vec, c_vec))
        similarities.append((dict(c), sim))

    # Sort by similarity descending and take top 5
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_5 = similarities[:5]

    conn.close()

    return [_person_from_row(row_data, db_path) for row_data, _ in top_5]


@router.get("/identities/{person_id}/faces")
async def get_person_faces(request: Request, person_id: int):
    """Get all face IDs for a person (used by the split UI)."""
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        "SELECT id FROM faces WHERE person_id = ?", (person_id,)
    ).fetchall()
    conn.close()

    return {"face_ids": [r[0] for r in rows]}


@router.delete("/identities/{person_id}")
async def delete_person(request: Request, person_id: int):
    """
    Dissolves a person cluster. 
    Removes the person record and unlinks all associated faces (sets them back to NULL).
    """
    db_path = request.app.state.db_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Check if exists
    row = conn.execute("SELECT id FROM people WHERE id = ?", (person_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    try:
        # 1. Unlink all faces
        conn.execute("UPDATE faces SET person_id = NULL WHERE person_id = ?", (person_id,))
        # 2. Delete person record
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail={"error": f"Failed to delete cluster: {e}"})

    conn.close()
    return {"message": "Cluster dissolved successfully", "person_id": person_id}


