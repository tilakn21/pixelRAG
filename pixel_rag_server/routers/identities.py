# pixel_rag_server/routers/identities.py
"""Identities router — CRUD, merge, and split for face clusters."""

import sqlite3

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request, Depends, UploadFile, File, Form
from pydantic import BaseModel

from pixel_rag_core.faces.cluster_faces import update_person_profile, compute_suggested_merges
from pixel_rag_server.models.schemas import PersonResponse, SuggestedMerge, TagByPhotoResponse
from pixel_rag_server.dependencies import get_db_path, LibraryContext

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

    # Get face count and representative face
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        face_count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id = ?", (person_id,)
        ).fetchone()[0]

        # Try to find representative face, fallback to first face
        cover_face = conn.execute(
            "SELECT id FROM faces WHERE person_id = ? ORDER BY is_representative DESC LIMIT 1",
            (person_id,)
        ).fetchone()
    finally:
        conn.close()

    # Get lib_hash from library manager
    from pixel_rag_server.services.library_manager import get_path_hash
    from pathlib import Path
    import os
    lib_path = row["folder_root"]
    lib_hash = get_path_hash(lib_path)
    
    sync_version = 0
    try:
        import hashlib
        lib_hash_12 = hashlib.md5(lib_path.encode()).hexdigest()[:12]
        face_cache_dir = Path.home() / ".pixelrag" / "thumbs" / lib_hash_12 / "faces"
        if face_cache_dir.exists():
            sync_version = int(face_cache_dir.stat().st_mtime)
    except Exception:
        pass

    cover_url = f"/api/media/face/{cover_face[0]}?h={lib_hash}_{sync_version}" if cover_face else None

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
def list_identities(
    request: Request,
    confirmed_only: bool = Query(False),
    lib_ctx: LibraryContext = Depends(get_db_path),
):
    """List all persons ordered by face count descending, suppressing singletons."""
    db_path = lib_ctx.db_path
    import os
    MIN_CLUSTER_SIZE = int(os.environ.get("PIXELRAG_MIN_CLUSTER_SIZE", "2"))

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    query = f"""
        SELECT p.* 
        FROM people p
        WHERE p.folder_root = ?
          AND (p.confirmed = 1 OR (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) >= {MIN_CLUSTER_SIZE})
    """
    params: list = [lib_ctx.library_path]

    if confirmed_only:
        query += " AND p.confirmed = 1"

    # Order by face count descending
    query += """
        ORDER BY (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) DESC
    """

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [_person_from_row(dict(row), db_path) for row in rows]


@router.get("/identities/graph")
def get_identities_graph(request: Request, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Get node and edge data for the Memory Graph."""
    import hashlib
    db_path = lib_ctx.db_path
    import os
    MIN_CLUSTER_SIZE = int(os.environ.get("PIXELRAG_MIN_CLUSTER_SIZE", "2"))

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Nodes: All people in this library
    nodes_query = f"""
        SELECT p.*, 
               (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) as face_count,
               (SELECT f.id FROM faces f WHERE f.person_id = p.id ORDER BY is_representative DESC LIMIT 1) as cover_face_id
        FROM people p
        WHERE p.folder_root = ?
          AND (p.confirmed = 1 OR (SELECT COUNT(*) FROM faces f WHERE f.person_id = p.id) >= {MIN_CLUSTER_SIZE})
    """
    nodes_rows = conn.execute(nodes_query, (lib_ctx.library_path,)).fetchall()
    
    nodes = []
    lib_hash = hashlib.md5(lib_ctx.library_path.encode()).hexdigest()[:8]
    
    sync_version = 0
    import os
    from pathlib import Path
    try:
        import hashlib
        lib_hash_12 = hashlib.md5(lib_ctx.library_path.encode()).hexdigest()[:12]
        face_cache_dir = Path.home() / ".pixelrag" / "thumbs" / lib_hash_12 / "faces"
        if face_cache_dir.exists():
            sync_version = int(face_cache_dir.stat().st_mtime)
    except Exception:
        pass
    
    valid_person_ids = set()
    for r in nodes_rows:
        if r["face_count"] > 0:
            valid_person_ids.add(r["id"])
            cover_url = f"/api/media/face/{r['cover_face_id']}?h={lib_hash}_{sync_version}" if r["cover_face_id"] else None
            nodes.append({
                "id": str(r["id"]),  # react-force-graph expects string/number IDs
                "name": r["name"],
                "face_count": r["face_count"],
                "cover_face_url": cover_url,
                "confirmed": bool(r["confirmed"])
            })

    # Edges: Co-occurrences
    edges_query = """
        SELECT f1.person_id as source, f2.person_id as target, COUNT(DISTINCT f1.photo_id) as weight
        FROM faces f1
        JOIN faces f2 ON f1.photo_id = f2.photo_id
        WHERE f1.person_id < f2.person_id
          AND f1.person_id IS NOT NULL 
          AND f2.person_id IS NOT NULL
        GROUP BY source, target
    """
    edges_rows = conn.execute(edges_query).fetchall()
    
    links = []
    for r in edges_rows:
        if r["source"] in valid_person_ids and r["target"] in valid_person_ids:
            links.append({
                "source": str(r["source"]),
                "target": str(r["target"]),
                "weight": r["weight"]
            })

    conn.close()
    return {"nodes": nodes, "links": links}


@router.get("/identities/{person_id}", response_model=PersonResponse)
def get_person_details(request: Request, person_id: int, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Fetch details for a single person cluster."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    return _person_from_row(dict(row), db_path)


class RenameBody(BaseModel):
    name: str


@router.patch("/identities/{person_id}", response_model=PersonResponse)
def rename_person(request: Request, person_id: int, body: RenameBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Update a person's name and mark as confirmed."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Verify person exists in this library
    row = conn.execute("SELECT * FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    try:
        conn.execute(
            "UPDATE people SET name = ?, confirmed = 1 WHERE id = ?",
            (body.name.strip(), person_id),
        )
    except sqlite3.IntegrityError:
        # User renamed to a person that already exists! Perform automatic merge within the same library.
        existing = conn.execute("SELECT id FROM people WHERE name = ? AND folder_root = ?", (body.name.strip(), lib_ctx.library_path)).fetchone()
        if existing:
            target_id = existing[0]
            conn.close()
            # Call the merge logic internally (by delegating to our merge routing logic)
            return merge_persons(request, target_id, MergeBody(source_person_id=person_id), lib_ctx=lib_ctx)
    
    # Recompute profile to pick a representative face for the search gallery
    update_person_profile(conn, person_id)
    conn.commit()

    updated = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    return _person_from_row(dict(updated), db_path)


class MergeBody(BaseModel):
    source_person_id: int


@router.post("/identities/{person_id}/merge", response_model=PersonResponse)
def merge_persons(request: Request, person_id: int, body: MergeBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Merge another cluster into this person."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    target = conn.execute("SELECT * FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    source = conn.execute(
        "SELECT * FROM people WHERE id = ? AND folder_root = ?", (body.source_person_id, lib_ctx.library_path)
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

    # FIX 4: Recalculate true merged centroid manually from all faces now belonging to target
    # BEFORE calling update_person_profile so it reads the new combined baseline.
    rows = conn.execute(
        "SELECT fe.embedding FROM face_embeddings fe JOIN faces f ON fe.face_id = f.id WHERE f.person_id = ?",
        (person_id,)
    ).fetchall()
    
    if rows:
        embeddings = [np.frombuffer(r[0], dtype=np.float32) for r in rows]
        X = np.array(embeddings)
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        X_norm = X / (norms + 1e-10)
        new_centroid = X_norm.mean(axis=0)
        new_centroid = new_centroid / (np.linalg.norm(new_centroid) + 1e-10)
        
        conn.execute(
            "UPDATE people SET centroid_embedding = ? WHERE id = ?",
            (new_centroid.astype(np.float32).tobytes(), person_id)
        )
        conn.commit()

    # Recompute purity and scrub outliers using the new baseline DB centroid
    from pixel_rag_core.faces.cluster_faces import update_person_profile
    update_person_profile(conn, person_id)
    conn.commit()

    updated = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    return _person_from_row(dict(updated), db_path)


class BatchMergeBody(BaseModel):
    source_person_ids: list[int]


@router.post("/identities/{person_id}/batch-merge", response_model=PersonResponse)
def batch_merge_persons(request: Request, person_id: int, body: BatchMergeBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Merge multiple clusters into this person."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    target = conn.execute("SELECT * FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Target person not found"})

    if not body.source_person_ids:
        conn.close()
        raise HTTPException(status_code=400, detail={"error": "No source person IDs provided"})

    placeholders = ",".join(["?"] * len(body.source_person_ids))
    
    # Verify all sources exist in this library
    sources = conn.execute(
        f"SELECT id FROM people WHERE id IN ({placeholders}) AND folder_root = ?", 
        (*body.source_person_ids, lib_ctx.library_path)
    ).fetchall()
    
    if len(sources) != len(body.source_person_ids):
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "One or more source persons not found or invalid"})

    try:
        # Reassign all faces from sources to target
        conn.execute(
            f"UPDATE faces SET person_id = ? WHERE person_id IN ({placeholders})",
            (person_id, *body.source_person_ids),
        )
        # Update clusters
        conn.execute(
            f"UPDATE clusters SET person_id = ? WHERE person_id IN ({placeholders})",
            (person_id, *body.source_person_ids),
        )
        # Delete source persons
        conn.execute(f"DELETE FROM people WHERE id IN ({placeholders})", body.source_person_ids)
        conn.commit()

        # Recalculate true merged centroid manually from all faces now belonging to target
        rows = conn.execute(
            "SELECT fe.embedding FROM face_embeddings fe JOIN faces f ON fe.face_id = f.id WHERE f.person_id = ?",
            (person_id,)
        ).fetchall()
        
        if rows:
            embeddings = [np.frombuffer(r[0], dtype=np.float32) for r in rows]
            X = np.array(embeddings)
            norms = np.linalg.norm(X, axis=1, keepdims=True)
            X_norm = X / (norms + 1e-10)
            new_centroid = X_norm.mean(axis=0)
            new_centroid = new_centroid / (np.linalg.norm(new_centroid) + 1e-10)
            
            conn.execute(
                "UPDATE people SET centroid_embedding = ? WHERE id = ?",
                (new_centroid.astype(np.float32).tobytes(), person_id)
            )
            conn.commit()

        update_person_profile(conn, person_id)
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail={"error": f"Failed to batch merge clusters: {e}"})

    updated = conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    conn.close()

    return _person_from_row(dict(updated), db_path)


class SplitBody(BaseModel):
    face_ids: list[int]


@router.post("/identities/{person_id}/split")
def split_cluster(request: Request, person_id: int, body: SplitBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Split selected faces into a new, unconfirmed person."""
    db_path = lib_ctx.db_path
    if not body.face_ids:
        raise HTTPException(status_code=400, detail={"error": "No faces to split"})

    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # Create new person in this library's folder_root
    cur = conn.execute(
        "INSERT INTO people (name, confirmed, folder_root) VALUES (?, 0, ?)",
        (f"Split_from_{person_id}", lib_ctx.library_path),
    )
    new_person_id = cur.lastrowid

    # Move selected faces and DISCONNECT from old clusters
    placeholders = ",".join("?" for _ in body.face_ids)
    conn.execute(
        f"UPDATE faces SET person_id = ?, cluster_id = NULL WHERE id IN ({placeholders})",
        [new_person_id] + body.face_ids,
    )
    conn.commit()

    # Recompute both centroids
    update_person_profile(conn, person_id)
    update_person_profile(conn, new_person_id)
    conn.commit()

    original = conn.execute("SELECT * FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    new_person = conn.execute(
        "SELECT * FROM people WHERE id = ? AND folder_root = ?", (new_person_id, lib_ctx.library_path)
    ).fetchone()
    conn.close()

    return {
        "original": _person_from_row(dict(original), db_path),
        "new": _person_from_row(dict(new_person), db_path),
    }


@router.get("/identities/suggested-merges", response_model=list[SuggestedMerge])
async def get_suggested_merges(request: Request, lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Read-only endpoint to compute and fetch mathematically similar identities 
    that might correspond to the same person.
    Runs asynchronously in an executor to prevent completely blocking the ASGI event loop
    during O(n^2) similarity scans.
    """
    db_path = lib_ctx.db_path
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, compute_suggested_merges, db_path, lib_ctx.library_path)


@router.get("/identities/{person_id}/similar", response_model=list[PersonResponse])
def get_similar_clusters(request: Request, person_id: int, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Get top 5 similar unconfirmed clusters by centroid cosine similarity."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    target = conn.execute(
        "SELECT centroid_embedding FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)
    ).fetchone()

    if not target or not target["centroid_embedding"]:
        conn.close()
        return []

    target_vec = np.frombuffer(target["centroid_embedding"], dtype=np.float32)
    t_norm = np.linalg.norm(target_vec)
    target_vec = target_vec / (t_norm if t_norm > 1e-8 else 1.0)

    # Get all unconfirmed persons with centroids in SAME library
    candidates = conn.execute(
        "SELECT * FROM people WHERE confirmed = 0 AND id != ? AND folder_root = ? AND centroid_embedding IS NOT NULL",
        (person_id, lib_ctx.library_path),
    ).fetchall()

    similarities = []
    for c in candidates:
        c_vec = np.frombuffer(c["centroid_embedding"], dtype=np.float32)
        c_norm = np.linalg.norm(c_vec)
        c_vec = c_vec / (c_norm if c_norm > 1e-8 else 1.0)
        sim = float(np.dot(target_vec, c_vec))
        similarities.append((dict(c), sim))

    # Sort by similarity descending and take top 5
    similarities.sort(key=lambda x: x[1], reverse=True)
    top_5 = similarities[:5]

    conn.close()

    return [_person_from_row(row_data, db_path) for row_data, _ in top_5]


@router.get("/identities/{person_id}/faces")
def get_person_faces(request: Request, person_id: int, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Get all face IDs for a person (used by the split UI)."""
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        "SELECT id FROM faces WHERE person_id = ?", (person_id,)
    ).fetchall()
    conn.close()

    return {"face_ids": [r[0] for r in rows]}


@router.delete("/identities/{person_id}")
def delete_person(request: Request, person_id: int, lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Dissolves a person cluster. 
    Removes the person record and unlinks all associated faces (sets them back to NULL).
    """
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Check if exists in this library
    row = conn.execute("SELECT id FROM people WHERE id = ? AND folder_root = ?", (person_id, lib_ctx.library_path)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Person not found"})

    try:
        # 1. Unlink all faces
        conn.execute("UPDATE faces SET person_id = NULL, cluster_id = NULL WHERE person_id = ?", (person_id,))
        # 2. Unlink clusters
        conn.execute("UPDATE clusters SET person_id = NULL WHERE person_id = ?", (person_id,))
        # 3. Delete person record
        conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail={"error": f"Failed to delete cluster: {e}"})

    conn.close()
    return {"message": "Cluster dissolved successfully", "person_id": person_id}


class BatchDeleteBody(BaseModel):
    person_ids: list[int]


@router.post("/identities/batch-delete")
def batch_delete_persons(request: Request, body: BatchDeleteBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Dissolves multiple person clusters. 
    Removes the person records and unlinks all associated faces.
    """
    db_path = lib_ctx.db_path
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    
    if not body.person_ids:
        conn.close()
        return {"message": "No clusters provided"}

    placeholders = ",".join(["?"] * len(body.person_ids))
    
    # Check if all exist in this library
    rows = conn.execute(
        f"SELECT id FROM people WHERE id IN ({placeholders}) AND folder_root = ?", 
        (*body.person_ids, lib_ctx.library_path)
    ).fetchall()
    
    if len(rows) != len(body.person_ids):
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "One or more persons not found or invalid"})

    try:
        # 1. Unlink all faces
        conn.execute(f"UPDATE faces SET person_id = NULL, cluster_id = NULL WHERE person_id IN ({placeholders})", body.person_ids)
        # 2. Unlink clusters
        conn.execute(f"UPDATE clusters SET person_id = NULL WHERE person_id IN ({placeholders})", body.person_ids)
        # 3. Delete person records
        conn.execute(f"DELETE FROM people WHERE id IN ({placeholders})", body.person_ids)
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail={"error": f"Failed to batch delete clusters: {e}"})

    conn.close()
    return {"message": f"{len(body.person_ids)} clusters dissolved successfully"}


@router.post("/identities/tag-by-photo", response_model=TagByPhotoResponse)
def tag_by_photo(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(...),
    lib_ctx: LibraryContext = Depends(get_db_path),
):
    """
    Upload a reference photo of a person + their name.
    Finds ALL matching clusters and merges them into one confirmed identity.
    
    This eliminates the need to manually name hundreds of clusters one by one.
    """
    db_path = lib_ctx.db_path
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "Name is required."})

    # 1. Read and extract face embedding from the uploaded image
    try:
        content = file.file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Failed to read image: {e}"})

    import io
    import cv2
    from PIL import Image, ImageOps

    try:
        pil_img = Image.open(io.BytesIO(content))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Invalid image format: {e}"})

    from pixel_rag_core.faces.face_search import _get_search_app
    app = _get_search_app()
    faces = app.get(img)

    if not faces:
        raise HTTPException(status_code=400, detail={"error": "No face detected in the uploaded image."})

    # Pick the largest face
    largest_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
    emb = largest_face.normed_embedding
    if emb is None:
        raise HTTPException(status_code=400, detail={"error": "Could not extract face embedding."})

    emb_norm = emb / (np.linalg.norm(emb) + 1e-10)

    # 2. Compare against ALL person centroids in this library
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    all_people = conn.execute(
        "SELECT id, name, centroid_embedding, confirmed FROM people "
        "WHERE folder_root = ? AND centroid_embedding IS NOT NULL",
        (lib_ctx.library_path,)
    ).fetchall()

    if not all_people:
        conn.close()
        raise HTTPException(status_code=400, detail={"error": "No clusters found in this library. Run a sync first."})

    # 3. Find all matching clusters (similarity > 0.65)
    TAG_SIMILARITY_THRESHOLD = 0.65
    matching_ids = []
    for row in all_people:
        centroid = np.frombuffer(row["centroid_embedding"], dtype=np.float32)
        c_norm = centroid / (np.linalg.norm(centroid) + 1e-10)
        sim = float(np.dot(emb_norm, c_norm))
        if sim >= TAG_SIMILARITY_THRESHOLD:
            matching_ids.append((row["id"], sim, bool(row["confirmed"])))

    if not matching_ids:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail={"error": "No matching clusters found for this face. The person may not appear in your library."}
        )

    # Sort by similarity descending
    matching_ids.sort(key=lambda x: x[1], reverse=True)

    # 4. Check if there's already a confirmed identity with this name
    existing = conn.execute(
        "SELECT id FROM people WHERE name = ? AND folder_root = ?",
        (name, lib_ctx.library_path)
    ).fetchone()

    if existing:
        target_id = existing["id"]
    else:
        # Use the highest-similarity cluster as the target
        target_id = matching_ids[0][0]
        conn.execute(
            "UPDATE people SET name = ?, confirmed = 1 WHERE id = ?",
            (name, target_id)
        )

    # 5. Merge all other matching clusters into the target
    clusters_absorbed = 0
    for (pid, sim, is_confirmed) in matching_ids:
        if pid == target_id:
            continue
        # Don't absorb already-confirmed identities (they might be intentionally different)
        if is_confirmed:
            continue
        
        # Move faces from source to target
        conn.execute(
            "UPDATE faces SET person_id = ? WHERE person_id = ?",
            (target_id, pid)
        )
        conn.execute(
            "UPDATE clusters SET person_id = ? WHERE person_id = ?",
            (target_id, pid)
        )
        conn.execute("DELETE FROM people WHERE id = ?", (pid,))
        clusters_absorbed += 1

    # 6. Ensure target is confirmed
    conn.execute(
        "UPDATE people SET name = ?, confirmed = 1 WHERE id = ?",
        (name, target_id)
    )
    conn.commit()

    # 7. Recompute centroid from all merged faces
    emb_rows = conn.execute(
        "SELECT fe.embedding FROM face_embeddings fe "
        "JOIN faces f ON fe.face_id = f.id WHERE f.person_id = ?",
        (target_id,)
    ).fetchall()

    if emb_rows:
        merged_embs = np.array([np.frombuffer(r[0], dtype=np.float32) for r in emb_rows])
        merged_norms = np.linalg.norm(merged_embs, axis=1, keepdims=True)
        merged_norm = merged_embs / (merged_norms + 1e-10)
        new_centroid = merged_norm.mean(axis=0)
        new_centroid = new_centroid / (np.linalg.norm(new_centroid) + 1e-10)
        conn.execute(
            "UPDATE people SET centroid_embedding = ? WHERE id = ?",
            (new_centroid.astype(np.float32).tobytes(), target_id)
        )
        conn.commit()

    # 8. Recompute profile (purity, gallery representatives)
    update_person_profile(conn, target_id)
    conn.commit()

    # 9. Count total photos for this person
    total_photos = conn.execute(
        "SELECT COUNT(DISTINCT photo_id) FROM faces WHERE person_id = ?",
        (target_id,)
    ).fetchone()[0]

    # Build response
    updated = conn.execute("SELECT * FROM people WHERE id = ?", (target_id,)).fetchone()
    conn.close()

    person_response = _person_from_row(dict(updated), db_path)

    return TagByPhotoResponse(
        person=person_response,
        clusters_absorbed=clusters_absorbed,
        total_photos=total_photos,
        message=f"Named '{name}' — absorbed {clusters_absorbed} clusters ({total_photos} photos)"
    )
