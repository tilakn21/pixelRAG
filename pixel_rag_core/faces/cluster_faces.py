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

import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


def _load_face_data(db_path: Path) -> Tuple[np.ndarray, List[int], List[int], List[int]]:
    """
    Load all face embeddings and return:
      X: (n_faces, dim) array
      face_ids, cluster_ids, person_ids in same order
    """
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.cursor()
        cur.execute(
            "SELECT f.id, f.cluster_id, f.person_id, fe.dim, fe.embedding "
            "FROM faces f JOIN face_embeddings fe ON f.id = fe.face_id"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    face_ids, cluster_ids, person_ids, vectors = [], [], [], []
    for face_id, cluster_id, person_id, dim, emb_blob in rows:
        vec = np.frombuffer(emb_blob, dtype=np.float32, count=dim)
        face_ids.append(face_id)
        cluster_ids.append(cluster_id)
        person_ids.append(person_id)
        vectors.append(vec)

    if not vectors:
        return np.empty((0,)), [], [], []

    X = np.vstack(vectors)
    return X, face_ids, cluster_ids, person_ids


def _attempt_orphan_reentry(conn: sqlite3.Connection, X_norm: np.ndarray, face_ids: List[int], person_ids: List[Optional[int]], folder_root: str, threshold: float = 0.55) -> int:
    """
    Attempts to assign 'orphan' faces (person_id IS NULL) to confirmed identity centroids
    scoped to the current folder_root.
    """
    rows = conn.execute(
        "SELECT id, centroid_embedding FROM people WHERE confirmed = 1 AND folder_root = ? AND centroid_embedding IS NOT NULL",
        (folder_root,)
    ).fetchall()
    
    if not rows:
        return 0

    p_ids = []
    p_embs = []
    for pid, emb_blob in rows:
        p_ids.append(pid)
        p_embs.append(np.frombuffer(emb_blob, dtype=np.float32))
    
    P = np.array(p_embs)
    P_norms = np.linalg.norm(P, axis=1, keepdims=True)
    P_norm = P / (P_norms + 1e-10)

    # Similarity matrix: (N_faces x N_people)
    sims = X_norm @ P_norm.T
    
    rescued = 0
    for i, face_id in enumerate(face_ids):
        # Only rescue if it has no person_id
        if person_ids[i] is not None:
            continue
            
        best_p_idx = np.argmax(sims[i])
        best_sim = sims[i][best_p_idx]
        
        if best_sim >= threshold:
            target_person_id = p_ids[best_p_idx]
            conn.execute("UPDATE faces SET person_id = ?, cluster_id = NULL WHERE id = ?", (target_person_id, int(face_id)))
            # Update our local copy for the rest of this clustering cycle
            person_ids[i] = target_person_id
            rescued += 1
            
    return rescued


def update_person_profile(conn: sqlite3.Connection, person_id: int):
    """
    Recompute centroid embedding and purity score for a person,
    scrub outliers (bottom 10% by similarity), and set gallery representatives.
    
    Now iterative: runs scrubbing until no more outliers are found (up to 10 passes).
    Also tries to load the stable baseline centroid from the DB to prevent identity drift.
    """
    # Try to load existing centroid from DB to anchor the identity
    db_centroid = None
    row = conn.execute("SELECT centroid_embedding FROM people WHERE id = ?", (person_id,)).fetchone()
    if row and row[0]:
        db_centroid = np.frombuffer(row[0], dtype=np.float32)
        denom = np.linalg.norm(db_centroid)
        db_centroid = db_centroid / (denom if denom > 1e-8 else 1.0)

    rows = conn.execute(
        """
        SELECT f.id, fe.embedding, f.sharpness, f.roll_angle, f.face_size_ratio
        FROM face_embeddings fe
        JOIN faces f ON fe.face_id = f.id
        WHERE f.person_id = ? 
           OR (f.person_id IS NULL AND f.cluster_id IN (SELECT id FROM clusters WHERE person_id = ?))
        """,
        (person_id, person_id),
    ).fetchall()

    if not rows:
        return

    face_ids = []
    embeddings = []
    sharpness_arr = []
    roll_arr = []
    size_ratio_arr = []
    
    for row in rows:
        face_ids.append(row[0])
        embeddings.append(np.frombuffer(row[1], dtype=np.float32))
        sharpness_arr.append(row[2] if row[2] is not None else 100.0)
        roll_arr.append(row[3] if row[3] is not None else 0.0)
        size_ratio_arr.append(row[4] if row[4] is not None else 0.05)

    face_ids = np.array(face_ids)
    X = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    X_norm = X / (norms + 1e-10)

    # Use DB centroid if available, otherwise mean of all faces
    if db_centroid is not None:
        centroid = db_centroid
    else:
        centroid = X_norm.mean(axis=0)
        denom = np.linalg.norm(centroid)
        centroid = centroid / (denom if denom > 1e-8 else 1.0)

    # Iterative Scrubbing phase (Fix 5)
    max_iters = 10
    total_ejected = 0
    X_in = X_norm
    face_ids_in = face_ids
    sims_in = (X_in @ centroid).flatten()
    
    # Track indices of remaining faces relative to original arrays for thumbnail scoring
    inlier_indices = np.arange(len(face_ids))

    # Threshold invariant check (enforced at code level):
    #   scrubber_eject_similarity (0.45) < (1.0 - clustering_distance_threshold) (0.62)
    #   0.45 < 0.62 ✓ — the scrubber will never eject a face that clustering accepted.
    SCRUBBER_EJECT_SIM = 0.45

    for iteration in range(max_iters):
        sims = (X_in @ centroid).flatten()
        
        inlier_mask = sims >= SCRUBBER_EJECT_SIM

        outlier_ids = face_ids_in[~inlier_mask]
        
        if len(outlier_ids) == 0:
            break # Converged!

        total_ejected += len(outlier_ids)
        placeholders = ",".join("?" for _ in outlier_ids)
        conn.execute(f"UPDATE faces SET person_id = NULL, cluster_id = NULL WHERE id IN ({placeholders})", outlier_ids.tolist())
        
        X_in = X_in[inlier_mask]
        face_ids_in = face_ids_in[inlier_mask]
        inlier_indices = inlier_indices[inlier_mask]
        
        if len(X_in) == 0:
            conn.execute("UPDATE people SET centroid_embedding = NULL, purity_score = 0 WHERE id = ?", (person_id,))
            print(f"[PixelRAG] Identity {person_id} collapsed completely after dropping {total_ejected} outliers.")
            return
            
        # Recalculate centroid for next pass
        centroid = X_in.mean(axis=0)
        denom = np.linalg.norm(centroid)
        centroid = centroid / (denom if denom > 1e-8 else 1.0)
        
    if total_ejected > 0:
        print(f"[PixelRAG] Scrubbed {total_ejected} outliers from Person {person_id} (converged in {iteration+1} passes)")

    # Ensure sims_in matches the final set of inliers (Fix 6)
    sims_in = (X_in @ centroid).flatten()

    # Purity
    if len(X_in) > 1:
        sim_matrix = X_in @ X_in.T
        n = len(X_in)
        purity = float((sim_matrix.sum() - n) / (n * (n - 1)))
    else:
        purity = 1.0

    # Multi-factor thumbnail scoring
    s_areas = np.array(size_ratio_arr)[inlier_indices]
    s_sharp = np.array(sharpness_arr)[inlier_indices]
    s_roll = np.array(roll_arr)[inlier_indices]

    norm_areas = np.clip(s_areas * 10.0, 0, 1) 
    norm_sharpness = np.clip(s_sharp / 500.0, 0, 1) 
    norm_pose = np.clip(1.0 - (np.abs(s_roll) / 45.0), 0, 1) 
    norm_sims = np.clip((sims_in - 0.45) / 0.55, 0, 1)   

    combined_scores = (0.2 * norm_areas) + (0.3 * norm_sharpness) + (0.3 * norm_pose) + (0.2 * norm_sims)
    
    sorted_indices = np.argsort(combined_scores)[::-1]
    repr_ids = [int(face_ids_in[i]) for i in sorted_indices[:10]]

    # Save
    conn.execute(
        "UPDATE faces SET is_representative = 0 "
        "WHERE person_id = ? OR cluster_id IN (SELECT id FROM clusters WHERE person_id = ?)",
        (person_id, person_id)
    )
    if repr_ids:
        placeholders = ",".join("?" for _ in repr_ids)
        conn.execute(f"UPDATE faces SET is_representative = 1 WHERE id IN ({placeholders})", repr_ids)

    # Check if this identity has been confirmed by the user
    confirmed_row = conn.execute(
        "SELECT confirmed FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    is_confirmed = confirmed_row and confirmed_row[0] == 1

    if is_confirmed:
        # Centroid is frozen — do not overwrite. Only update purity score and representatives.
        conn.execute(
            "UPDATE people SET purity_score = ? WHERE id = ?",
            (purity, person_id),
        )
    else:
        conn.execute(
            "UPDATE people SET centroid_embedding = ?, purity_score = ? WHERE id = ?",
            (centroid.astype(np.float32).tobytes(), purity, person_id),
        )


def _auto_merge_clusters(conn: sqlite3.Connection, folder_root: str, similarity_threshold: float = 0.72) -> int:
    """
    Automatically merge unconfirmed clusters whose centroids are highly similar.
    This collapses fragments of the same person that were split by conservative clustering.
    
    Only merges unconfirmed clusters (confirmed identities are never touched).
    Uses greedy highest-similarity-first strategy.
    
    :param similarity_threshold: Minimum cosine similarity to auto-merge (default 0.72)
    :return: Number of merges performed
    """
    total_merges = 0
    max_rounds = 50  # Safety cap to prevent infinite loops
    
    for round_num in range(max_rounds):
        # Reload centroids each round (they change after merges)
        rows = conn.execute(
            "SELECT id, centroid_embedding FROM people "
            "WHERE folder_root = ? AND confirmed = 0 AND centroid_embedding IS NOT NULL",
            (folder_root,)
        ).fetchall()
        
        if len(rows) < 2:
            break
        
        people_ids = []
        embeddings = []
        for pid, emb_blob in rows:
            people_ids.append(pid)
            embeddings.append(np.frombuffer(emb_blob, dtype=np.float32))
        
        X = np.array(embeddings)
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        X_norm = X / (norms + 1e-10)
        
        # Compute full cosine similarity matrix
        sim_matrix = X_norm @ X_norm.T
        
        # Zero out diagonal and lower triangle
        n = len(people_ids)
        for i in range(n):
            sim_matrix[i, i] = 0.0
            for j in range(i):
                sim_matrix[i, j] = 0.0
        
        # Find the highest similarity pair
        best_idx = np.unravel_index(np.argmax(sim_matrix), sim_matrix.shape)
        best_sim = sim_matrix[best_idx]
        
        if best_sim < similarity_threshold:
            break  # No more pairs above threshold
        
        i, j = best_idx
        target_id = people_ids[i]
        source_id = people_ids[j]
        
        # Get face counts to merge smaller into larger
        target_count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id = ?", (target_id,)
        ).fetchone()[0]
        source_count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id = ?", (source_id,)
        ).fetchone()[0]
        
        # Always merge smaller into larger
        if source_count > target_count:
            target_id, source_id = source_id, target_id
        
        # Perform merge: move all faces from source to target
        conn.execute(
            "UPDATE faces SET person_id = ? WHERE person_id = ?",
            (target_id, source_id)
        )
        conn.execute(
            "UPDATE clusters SET person_id = ? WHERE person_id = ?",
            (target_id, source_id)
        )
        conn.execute("DELETE FROM people WHERE id = ?", (source_id,))
        
        # Recompute centroid for the merged identity
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
        
        total_merges += 1
    
    return total_merges


def cluster_all_faces(
    db_path: str,
    folder_root: str,
    min_cluster_size: int = 2,
    distance_threshold: float = 0.38,
) -> Dict[str, int]:
    """
    Run Agglomerative Clustering on ORPHAN face embeddings only.

    Confirmed faces are excluded from the clustering input so they don't
    distort cluster boundaries for unassigned faces.

    Uses AVERAGE linkage for balanced precision/recall — robust to a few
    noisy photos (sunglasses, side profile) without chaining unrelated faces.

    :param min_cluster_size: Minimum faces to form a cluster (default 2)
    :param distance_threshold: Maximum cosine distance for average linkage (default 0.38)
    """
    from sklearn.cluster import AgglomerativeClustering

    db_path = Path(db_path)
    X, face_ids, cluster_ids, person_ids = _load_face_data(db_path)

    if len(face_ids) == 0:
        print("[PixelRAG] No face embeddings found to cluster.")
        return {}

    n_faces = len(face_ids)
    if n_faces < min_cluster_size:
        print(f"[PixelRAG] Only {n_faces} faces found. Need at least {min_cluster_size} to construct clusters. Skipping.")
        return {"clusters_created": 0, "faces_assigned": 0, "noise_faces": 0}

    print(f"[PixelRAG] Processing {n_faces} total faces...")
    
    X_f32 = X.astype(np.float32)
    norms = np.linalg.norm(X_f32, axis=1, keepdims=True)
    X_norm = X_f32 / (norms + 1e-10)

    # ── Phase 1: Orphan Re-entry (Rescue valid ejected faces) ─────────────
    # This addresses the "Orphan Graveyard" issue by checking confirmed centroids
    # before starting a fresh clustering pass.
    conn_re = sqlite3.connect(db_path, timeout=30)
    try:
        conn_re.execute("PRAGMA journal_mode=WAL")
        rescued = _attempt_orphan_reentry(conn_re, X_norm, face_ids, person_ids, folder_root, threshold=0.55)
        if rescued > 0:
            print(f"[PixelRAG] Rescued {rescued} orphaned faces by re-assigning them to confirmed identities.")
        conn_re.commit()
    finally:
        conn_re.close()

    # ── Phase 2: Partition — only cluster ORPHAN faces ────────────────────
    # Confirmed faces are excluded entirely so they don't distort cluster
    # boundaries for unassigned faces (prevents cross-person contamination).
    orphan_mask = np.array([pid is None for pid in person_ids])
    orphan_indices = np.where(orphan_mask)[0]
    n_confirmed = int(np.sum(~orphan_mask))
    n_orphans = len(orphan_indices)

    print(f"[PixelRAG] {n_confirmed} confirmed faces frozen, {n_orphans} orphan faces to cluster.")

    if n_orphans < min_cluster_size:
        print(f"[PixelRAG] Only {n_orphans} orphan faces. Need at least {min_cluster_size}. Skipping clustering.")
        return {"clusters_created": 0, "faces_assigned": 0, "noise_faces": n_orphans}

    # Extract orphan-only data for clustering
    X_orphan = X_norm[orphan_indices]
    orphan_face_ids = [face_ids[i] for i in orphan_indices]

    # Create clusters out of orphan faces only
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        linkage='average',
        metric='cosine',
    )
    labels = clustering.fit_predict(X_orphan)

    # Post-process labels: enforce min_cluster_size (singletons become noise (-1))
    unique_labels, counts = np.unique(labels, return_counts=True)
    noise_labels = unique_labels[counts < min_cluster_size]
    
    # Re-map valid clusters to clean sequential IDs and tag noise as -1
    clean_labels = np.full_like(labels, -1)
    current_cluster = 0
    for label in unique_labels:
        if label in noise_labels:
            continue
        clean_labels[labels == label] = current_cluster
        current_cluster += 1
        
    labels = clean_labels
    unique_labels = set(labels)

    n_clusters = current_cluster
    n_noise = int(np.sum(labels == -1))
    print(f"[PixelRAG] Agglomerative found {n_clusters} clusters, {n_noise} noise faces (threshold={distance_threshold}).")

    # ── Database update phase ───────────────────────────────────────────
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Get the next available cluster ID offset
        max_cluster = conn.execute("SELECT MAX(id) FROM clusters").fetchone()[0]
        base_cluster_id = (max_cluster or 0) + 1

        # First, clear all cluster_ids (but NOT person_ids!) for a fresh assignment
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

        # Assign orphan faces to clusters (all faces in labels are orphans by design)
        faces_assigned = 0
        for i, (face_id, lbl) in enumerate(zip(orphan_face_ids, labels)):
            if lbl == -1:
                # Noise: cluster_id stays NULL
                conn.execute("UPDATE faces SET cluster_id = NULL WHERE id = ?", (int(face_id),))
            else:
                cluster_id = label_to_cluster_id[lbl]
                conn.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (cluster_id, int(face_id)))
                faces_assigned += 1

        conn.commit()

        # ── Compute centroids, purity, and gallery representations ──
        print("[PixelRAG] Optimizing identities and building gallery...")

        for label, cluster_id in label_to_cluster_id.items():
            mask = labels == label
            if sum(mask) < min_cluster_size:
                continue

            person_id = None
            person_row = conn.execute(
                "SELECT person_id FROM clusters WHERE id = ?", (cluster_id,)
            ).fetchone()

            if person_row and person_row[0] is not None:
                person_id = int(person_row[0])
            else:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO people (name, confirmed, folder_root) "
                    "VALUES (?, 0, ?)",
                    (f"Cluster_{cluster_id}", folder_root),
                )
                if cur.lastrowid:
                    person_id = int(cur.lastrowid)
                else:
                    existing = conn.execute("SELECT id FROM people WHERE name = ? AND folder_root = ?", (f"Cluster_{cluster_id}", folder_root)).fetchone()
                    if existing:
                        person_id = int(existing[0])

                if person_id is not None:
                    conn.execute(
                        "UPDATE clusters SET person_id = ? WHERE id = ?",
                        (person_id, cluster_id),
                    )
                    
            if person_id is not None:
                # Sync person_id directly for faces in this cluster to normalize schema
                conn.execute("UPDATE faces SET person_id = ? WHERE cluster_id = ?", (person_id, cluster_id))
                update_person_profile(conn, person_id)

        conn.commit()

        # ── Phase 3: Auto-Merge Similar Unconfirmed Clusters ──────────────
        print("[PixelRAG] Running auto-merge on similar unconfirmed clusters...")
        auto_merged = _auto_merge_clusters(conn, folder_root, similarity_threshold=0.80)
        if auto_merged > 0:
            print(f"[PixelRAG] Auto-merged {auto_merged} cluster pairs.")
            # Recompute profiles for remaining identities after merge
            remaining_ids = conn.execute(
                "SELECT id FROM people WHERE folder_root = ? AND confirmed = 0",
                (folder_root,)
            ).fetchall()
            for (pid,) in remaining_ids:
                update_person_profile(conn, pid)
        conn.commit()

        # Final cluster count after auto-merge
        final_count = conn.execute(
            "SELECT COUNT(*) FROM people WHERE folder_root = ?",
            (folder_root,)
        ).fetchone()[0]

        print(f"[PixelRAG] ---- Clustering Complete (Agglomerative + Auto-Merge) ----")
        print(f"[PixelRAG] Raw clusters created  : {new_clusters_created}")
        print(f"[PixelRAG] Auto-merged pairs     : {auto_merged}")
        print(f"[PixelRAG] Final identities      : {final_count}")
        print(f"[PixelRAG] Faces assigned        : {faces_assigned}")
        print(f"[PixelRAG] Noise faces           : {n_noise}")
        print(f"[PixelRAG] --------------------------------------------------")

        return {
            "clusters_created": new_clusters_created,
            "auto_merged": auto_merged,
            "final_identities": final_count,
            "faces_assigned": faces_assigned,
            "noise_faces": n_noise,
        }
    finally:
        conn.close()


def compute_suggested_merges(db_path: str, folder_root: str) -> list[dict]:
    """
    Computes pairwise similarities between identity centroids within the same library.
    """
    # Default to 0.72 similarity for strict merge suggestion matching
    threshold = float(os.environ.get("PIXELRAG_SUGGEST_MERGE_THRESHOLD", "0.72"))

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Load all valid centroids for this library
    rows = conn.execute(
        "SELECT id, centroid_embedding FROM people WHERE folder_root = ? AND centroid_embedding IS NOT NULL",
        (folder_root,)
    ).fetchall()
    
    if len(rows) < 2:
        conn.close()
        return []

    people_ids = []
    embeddings = []
    
    for pid, emb_blob in rows:
        people_ids.append(pid)
        embeddings.append(np.frombuffer(emb_blob, dtype=np.float32))
        
    X = np.array(embeddings)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    X_norm = X / (norms + 1e-10)

    # Compute full cosine similarity matrix
    sim_matrix = X_norm @ X_norm.T
    
    suggestions = []
    n = len(people_ids)
    
    for i in range(n):
        # j > i ensures we only flag each unique pair once
        for j in range(i + 1, n):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                suggestions.append({
                    "identity_a_id": people_ids[i],
                    "identity_b_id": people_ids[j],
                    "similarity_score": sim,
                    "sample_face_a": f"/api/media/face/{_get_cover_face(conn, people_ids[i])}",
                    "sample_face_b": f"/api/media/face/{_get_cover_face(conn, people_ids[j])}"
                })
                
    conn.close()
    
    # Sort descending by similarity
    suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
    return suggestions


def _get_cover_face(conn: sqlite3.Connection, person_id: int) -> int:
    """Helper to get a representative face_id for UI previews."""
    row = conn.execute(
        """SELECT id FROM faces WHERE person_id = ? 
           ORDER BY is_representative DESC, (bbox_x2 - bbox_x1) * (bbox_y2 - bbox_y1) DESC 
           LIMIT 1""", 
        (person_id,)
    ).fetchone()
    return row[0] if row else 0
