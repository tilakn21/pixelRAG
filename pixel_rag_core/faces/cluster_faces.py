# pixel_rag_core/faces/cluster_faces.py
#
# HDBSCAN-based face clustering with FAISS indexing.
# Replaces the previous incremental greedy assignment approach.
#
# Key improvements:
# - Globally optimal clusters (no order dependency)
# - Proper density-based clustering handles unequal cluster sizes
# - Purity scoring for cluster quality assessment
# - Mean centroids for stable identity representation

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def _load_face_data(db_path: Path) -> Tuple[np.ndarray, List[int], List[int], List[int]]:
    """
    Load all face embeddings and return:
      X: (n_faces, dim) array
      face_ids, cluster_ids, person_ids in same order
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.execute(
        "SELECT f.id, f.cluster_id, f.person_id, fe.dim, fe.embedding "
        "FROM faces f JOIN face_embeddings fe ON f.id = fe.face_id"
    )
    rows = cur.fetchall()
    conn.close()

    face_ids, cluster_ids, person_ids, vectors = [], [], [], []
    for face_id, cluster_id, person_id, dim, emb_blob in rows:
        vec = np.frombuffer(emb_blob, dtype=np.float64, count=dim)
        face_ids.append(face_id)
        cluster_ids.append(cluster_id)
        person_ids.append(person_id)
        vectors.append(vec)

    if not vectors:
        return np.empty((0,)), [], [], []

    X = np.vstack(vectors)
    return X, face_ids, cluster_ids, person_ids


def _compute_purity_score(embeddings: np.ndarray) -> float:
    """
    Compute intra-cluster purity as mean off-diagonal cosine similarity.
    Embeddings should be L2-normalized.
    """
    if len(embeddings) < 2:
        return 1.0

    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normed = embeddings / (norms + 1e-10)

    # Full pairwise cosine similarity via matrix multiplication
    sim_matrix = normed @ normed.T

    # mean of off-diagonal values
    n = len(embeddings)
    # Sum all, subtract diagonal (which is n * 1.0), divide by n*(n-1)
    total = sim_matrix.sum() - np.trace(sim_matrix)
    count = n * (n - 1)
    if count == 0:
        return 1.0
    return float(total / count)


def _compute_centroid(embeddings: np.ndarray) -> np.ndarray:
    """Compute L2-normalized mean embedding centroid."""
    mean = embeddings.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    return mean


def cluster_all_faces(
    db_path: str,
    min_cluster_size: int = 3,
    min_samples: int = 2,
) -> Dict[str, int]:
    """
    Run HDBSCAN clustering on all face embeddings.

    This replaces the incremental greedy assignment with a globally-optimal
    density-based clustering algorithm.

    Key behaviors:
    - Writes ONLY to cluster_id (never touches person_id)
    - Noise faces (HDBSCAN label -1) get cluster_id = NULL
    - Computes mean centroid and purity score for each cluster
    - Creates/updates people rows for new clusters

    :param min_cluster_size: Minimum faces to form a cluster (default 3)
    :param min_samples: HDBSCAN min_samples parameter (default 2)
    """
    import hdbscan

    db_path = Path(db_path)
    X, face_ids, cluster_ids, person_ids = _load_face_data(db_path)

    if len(face_ids) == 0:
        print("[PixelRAG] No face embeddings found to cluster.")
        return {}

    n_faces = len(face_ids)
    if n_faces < min_cluster_size:
        print(f"[PixelRAG] Only {n_faces} faces found. Need at least {min_cluster_size} to construct clusters. Skipping HDBSCAN.")
        return {"clusters_created": 0, "faces_assigned": 0, "noise_faces": 0}

    print(f"[PixelRAG] Clustering {n_faces} faces with HDBSCAN...")

    # L2 normalize embeddings (ArcFace embeddings should already be normalized,
    # but we ensure it here for correctness)
    X_f32 = X.astype(np.float32)
    norms = np.linalg.norm(X_f32, axis=1, keepdims=True)
    X_norm = X_f32 / (norms + 1e-10)

    # Run HDBSCAN
    # Using euclidean distance on L2-normalized vectors is equivalent to cosine distance
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric='euclidean',
        cluster_selection_method='eom',
    )
    labels = clusterer.fit_predict(X_norm)

    # Count results
    unique_labels = set(labels)
    n_clusters = len(unique_labels - {-1})
    n_noise = int(np.sum(labels == -1))
    print(f"[PixelRAG] HDBSCAN found {n_clusters} clusters, {n_noise} noise faces.")

    # ── Database update phase ───────────────────────────────────────────
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Get the next available cluster ID offset
        max_cluster = conn.execute("SELECT MAX(id) FROM clusters").fetchone()[0]
        base_cluster_id = (max_cluster or 0) + 1

        # First, clear all cluster_ids (but NOT person_ids!) for a fresh assignment
        conn.execute("UPDATE faces SET cluster_id = NULL WHERE person_id IS NULL")

        # Map HDBSCAN labels to database cluster IDs
        label_to_cluster_id = {}
        new_clusters_created = 0

        for label in sorted(unique_labels):
            if label == -1:
                continue  # noise faces stay as NULL
            cluster_id = int(base_cluster_id + label)
            label_to_cluster_id[label] = cluster_id

            # Create cluster row
            conn.execute(
                "INSERT OR IGNORE INTO clusters (id, person_id, label) VALUES (?, NULL, NULL)",
                (cluster_id,),
            )
            new_clusters_created += 1

        # Assign faces to clusters
        faces_assigned = 0
        for i, (face_id, lbl) in enumerate(zip(face_ids, labels)):
            # Skip faces that already have a person_id (human-confirmed)
            if person_ids[i] is not None:
                continue

            if lbl == -1:
                # Noise: cluster_id stays NULL
                conn.execute("UPDATE faces SET cluster_id = NULL WHERE id = ?", (int(face_id),))
            else:
                cluster_id = label_to_cluster_id[lbl]
                conn.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (cluster_id, int(face_id)))
                faces_assigned += 1

        conn.commit()

        # ── Compute centroids and purity scores ─────────────────────────────
        print("[PixelRAG] Computing centroids and purity scores...")

        for label, cluster_id in label_to_cluster_id.items():
            # Get indices of faces in this cluster
            mask = labels == label
            cluster_embeddings = X[mask]  # Use original float64 embeddings

            if len(cluster_embeddings) < min_cluster_size:
                continue

            # Compute centroid (L2-normalized mean)
            centroid = _compute_centroid(cluster_embeddings)
            centroid_blob = centroid.astype(np.float32).tobytes()

            # Compute purity score
            purity = float(_compute_purity_score(cluster_embeddings))

            # Check if this cluster is linked to a person via the clusters table
            person_row = conn.execute(
                "SELECT person_id FROM clusters WHERE id = ?", (cluster_id,)
            ).fetchone()

            if person_row and person_row[0] is not None:
                # Update existing person
                conn.execute(
                    "UPDATE people SET centroid_embedding = ?, purity_score = ? WHERE id = ?",
                    (centroid_blob, purity, int(person_row[0]))
                )
            else:
                # Create a placeholder person for this unnamed cluster
                cur = conn.execute(
                    "INSERT OR IGNORE INTO people (name, centroid_embedding, purity_score, confirmed) "
                    "VALUES (?, ?, ?, 0)",
                    (f"Cluster_{cluster_id}", centroid_blob, purity),
                )
                if cur.lastrowid:
                    person_id = int(cur.lastrowid)
                    conn.execute(
                        "UPDATE clusters SET person_id = ? WHERE id = ?",
                        (person_id, cluster_id),
                    )

        conn.commit()

        print(f"[PixelRAG] ---- Clustering Complete (HDBSCAN) ----")
        print(f"[PixelRAG] Clusters created     : {new_clusters_created}")
        print(f"[PixelRAG] Faces assigned        : {faces_assigned}")
        print(f"[PixelRAG] Noise faces           : {n_noise}")
        print(f"[PixelRAG] --------------------------------------------------")

        return {
            "clusters_created": new_clusters_created,
            "faces_assigned": faces_assigned,
            "noise_faces": n_noise,
        }
    finally:
        conn.close()
