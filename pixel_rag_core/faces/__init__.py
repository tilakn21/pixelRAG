# pixel_rag_core/faces/cluster_faces.py

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# We used to define generic geometry constants here for dlib.
# Insightface handles this natively now.

# The DBSCAN import is removed as per the user's implied change in the snippet.
# from sklearn.cluster import DBSCAN


def _load_face_embeddings(db_path: Path) -> Tuple[np.ndarray, List[int]]:
    """
    Load all face embeddings and return:
      X: (n_faces, dim) array
      face_ids: list of face_id in same order as rows in X
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT face_id, dim, embedding FROM face_embeddings")
    rows = cur.fetchall()
    conn.close()

    face_ids: List[int] = []
    vectors: List[np.ndarray] = []

    for face_id, dim, emb_blob in rows:
        # reconstruct numpy array
        vec = np.frombuffer(emb_blob, dtype=np.float64, count=dim)
        face_ids.append(face_id)
        vectors.append(vec)

    if not vectors:
        return np.empty((0,)), []

    X = np.vstack(vectors)
    return X, face_ids


def _get_next_cluster_offset(conn: sqlite3.Connection) -> int:
    """
    Find current max cluster.id and return next offset to avoid id collisions.
    """
    cur = conn.cursor()
    cur.execute("SELECT MAX(id) FROM clusters")
    row = cur.fetchone()
    max_id = row[0] if row and row[0] is not None else -1
    return max_id + 1


def cluster_all_faces(db_path: str, eps: float = 0.45, min_samples: int = 4) -> Dict[int, int]:
    """
    Run DBSCAN clustering on all face embeddings and assign cluster_id to faces.

    Returns: mapping face_id -> cluster_id (for non-noise faces).
    """
    db_path = Path(db_path)
    X, face_ids = _load_face_embeddings(db_path)

    if X.size == 0:
        print("[PixelRAG] No face embeddings found to cluster.")
        return {}

    print(f"[PixelRAG] Clustering {len(face_ids)} faces...")

    # Run DBSCAN
    clt = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
    labels = clt.fit_predict(X)  # -1 means noise

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Base offset so we don't overwrite existing cluster IDs
    base_cluster = _get_next_cluster_offset(conn)

    face_to_cluster: Dict[int, int] = {}
    new_clusters = set()

    for face_id, lbl in zip(face_ids, labels):
        if lbl == -1:
            # noise: we leave cluster_id as NULL
            continue

        cluster_id = base_cluster + int(lbl)
        face_to_cluster[face_id] = cluster_id
        new_clusters.add(cluster_id)

        # update faces table
        cur.execute(
            "UPDATE faces SET cluster_id = ? WHERE id = ?",
            (cluster_id, face_id),
        )

    # Insert clusters into clusters table if not exists
    for cid in new_clusters:
        cur.execute(
            """
            INSERT OR IGNORE INTO clusters (id, person_id, label)
            VALUES (?, NULL, NULL)
            """,
            (cid,),
        )

    conn.commit()
    conn.close()

    print(f"[PixelRAG] Assigned clusters to {len(face_to_cluster)} faces.")
    print(f"[PixelRAG] New clusters created: {len(new_clusters)}")

    return face_to_cluster
