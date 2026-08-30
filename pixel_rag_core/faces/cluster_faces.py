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

# ── Clustering configuration ─────────────────────────────────────────────────
# These are MEASURED defaults, not guesses. Every candidate was graded against
# 567 human-confirmed faces across 7 identities in the real library
# (scratch/eval_clustering.py). Pairwise precision was 1.000 for all of them —
# the differentiator was RECALL, i.e. how badly each fragments one person:
#
#   config                          ARI     clusters(true=7)  clusters/person
#   average, t=0.38  (old default)  0.672        39                5.6
#   median,  t=0.42                 0.992         9                1.29
#   median,  t=0.42, core>=3        1.000         7                1.00   <-- chosen
#
# The old average-linkage default split each person into ~5.6 clusters, which
# is precisely why naming felt manual: 7 people meant naming 39 clusters.
#
# Why median linkage: Apple reports it gives single-linkage runtime with
# average-linkage-or-better accuracy for faces; measured here it lifts recall
# 0.561 -> 0.960 with precision unchanged at 1.000.
#
# Why t=0.42: results are identical from 0.42 through 0.55 (the merge structure
# saturates), so the LOWEST value on that plateau is chosen — it is the most
# conservative against over-merging on a larger library with more people, where
# precision pressure is far higher than in this 7-identity sample.
#
# Why core>=3 (Immich's default): a face may join a cluster but may only extend
# one if it has >=3 similar neighbours, which stops an ambiguous face from
# chaining two people together. It costs ~2% coverage, but those faces are
# recovered by _attempt_orphan_reentry() on the next pass once identities are
# confirmed — so the cost is temporary and the 1:1 cluster/person mapping is not.
CLUSTER_LINKAGE = os.environ.get("PIXELRAG_CLUSTER_LINKAGE", "median")
CLUSTER_DISTANCE_THRESHOLD = float(os.environ.get("PIXELRAG_CLUSTER_THRESHOLD", "0.42"))
CLUSTER_MIN_CORE = int(os.environ.get("PIXELRAG_CLUSTER_MIN_CORE", "3"))

# Margin required between the best and second-best IDENTITY before an
# assignment is accepted. Same rationale as face_indexer.AUTOTAG_MARGIN: a
# fixed similarity bar is only safe while the impostor distribution stays below
# it, and impostor_max grows with identity count (~0.128*ln(n)+0.086 measured
# here), projecting the 0.55 re-entry bar breached near ~38 identities.
# See scratch/measure_impostor_margins.py and CONTEXT.md §15.
REENTRY_MARGIN = float(os.environ.get("PIXELRAG_REENTRY_MARGIN", "0.05"))


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
    margin_rejects = 0
    for i, face_id in enumerate(face_ids):
        # Only rescue if it has no person_id
        if person_ids[i] is not None:
            continue

        row = sims[i]
        best_p_idx = int(np.argmax(row))
        best_sim = float(row[best_p_idx])
        # Runner-up across a DIFFERENT identity (rows are already one column per
        # person, so a plain second-max is the right comparison here).
        second_sim = float(np.partition(row, -2)[-2]) if len(row) > 1 else -1.0

        if best_sim >= threshold and (best_sim - second_sim) >= REENTRY_MARGIN:
            target_person_id = p_ids[best_p_idx]
            conn.execute("UPDATE faces SET person_id = ?, cluster_id = NULL WHERE id = ?", (target_person_id, int(face_id)))
            # Update our local copy for the rest of this clustering cycle
            person_ids[i] = target_person_id
            rescued += 1
        elif best_sim >= threshold:
            # Near-tie between two identities: leave it orphaned so clustering
            # (or the user) decides, rather than silently picking one.
            margin_rejects += 1

    if margin_rejects:
        print(f"[PixelRAG] Orphan re-entry: {margin_rejects} faces cleared the "
              f"{threshold} bar but failed the {REENTRY_MARGIN} margin — left orphaned.")
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

    # Threshold invariant, derived rather than hard-coded so it cannot silently
    # break when the clustering threshold is retuned:
    #   SCRUBBER_EJECT_SIM  <  1 - CLUSTER_DISTANCE_THRESHOLD
    # If violated, the scrubber would eject faces that clustering had just
    # legitimately accepted, fighting its own clusterer. Kept a safe margin
    # below the boundary (currently 1 - 0.42 = 0.58).
    SCRUBBER_EJECT_SIM = min(0.45, (1.0 - CLUSTER_DISTANCE_THRESHOLD) - 0.10)

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


def _knn_edges(
    X_norm: np.ndarray,
    k: int = 64,
    threshold: float = 0.55,
    chunk: int = 2048,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Build the edge list of an approximate kNN similarity graph WITHOUT ever
    materializing the full n x n matrix.

    Rows are processed in chunks: each chunk allocates only (chunk x n) floats,
    so peak memory is bounded by `chunk`, not by n. At n=40k and chunk=2048
    that is ~320 MB instead of the ~12.8 GB a full float64 distance matrix
    would need.

    Returns (rows, cols) of edges with cosine similarity >= threshold.
    """
    n = X_norm.shape[0]
    k = min(k, max(1, n - 1))
    rows_out, cols_out = [], []

    # Guard: a non-finite embedding poisons an entire chunk's matmul and would
    # silently drop every edge for those rows.
    if not np.isfinite(X_norm).all():
        X_norm = np.nan_to_num(X_norm, nan=0.0, posinf=0.0, neginf=0.0)
        print("[PixelRAG] ⚠️  Non-finite values in embeddings — zeroed before kNN.")

    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        sims = X_norm[start:stop] @ X_norm.T          # (b, n) — only big alloc

        # Never let a face be its own neighbour
        for i in range(stop - start):
            sims[i, start + i] = -1.0

        # Top-k per row, then filter by threshold
        part = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        block_rows = np.repeat(np.arange(start, stop), k)
        block_cols = part.reshape(-1)
        block_vals = sims[np.repeat(np.arange(stop - start), k), block_cols]

        keep = block_vals >= threshold
        rows_out.append(block_rows[keep])
        cols_out.append(block_cols[keep])

        del sims, part, block_vals

    if not rows_out:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    return np.concatenate(rows_out), np.concatenate(cols_out)


def _cluster_component(
    X_sub: np.ndarray,
    distance_threshold: float,
    linkage_method: str,
) -> np.ndarray:
    """
    Exact hierarchical clustering of one component.

    'average' uses cosine distance directly. 'median' (and other centroid-type
    methods) are only mathematically valid under Euclidean geometry, so they run
    on the unit-normalized vectors with the threshold converted:
        ||a-b||^2 = 2(1 - cos(a,b))   =>   d_euclid = sqrt(2 * d_cosine)
    which preserves the exact same ordering of pairs.

    Median linkage is offered because Apple reports it gives single-linkage
    runtime with average-linkage-or-better accuracy for face clustering.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    if len(X_sub) < 2:
        return np.zeros(len(X_sub), dtype=np.int64)

    if linkage_method in ("median", "centroid", "ward"):
        Z = linkage(X_sub, method=linkage_method, metric="euclidean")
        t = float(np.sqrt(2.0 * distance_threshold))
    else:
        Z = linkage(pdist(X_sub, metric="cosine"), method=linkage_method)
        t = distance_threshold

    return fcluster(Z, t=t, criterion="distance").astype(np.int64)


def _scalable_agglomerative(
    X_norm: np.ndarray,
    distance_threshold: float,
    min_cluster_size: int,
    max_exact: int = 6000,
    edge_threshold: float = 0.55,
    k: int = 64,
    linkage_method: str = "average",
    min_core_neighbors: int = 0,
    _depth: int = 0,
    _stats: Optional[Dict] = None,
) -> np.ndarray:
    """
    Memory-bounded replacement for a single global AgglomerativeClustering call.

    Why this is equivalent, not an approximation:
      average linkage merges two clusters only when their MEAN pairwise
      distance <= distance_threshold, which implies at least one pair is
      <= distance_threshold (similarity >= 1 - distance_threshold = 0.62).
      So any merge the global algorithm would perform has a qualifying edge.
      Building the graph at a LOOSER similarity (0.55 < 0.62) therefore cannot
      separate faces that global clustering would have joined — it only bounds
      how much has to be compared at once.

    Pipeline: kNN edges -> connected components -> exact average-linkage inside
    each component. Components above `max_exact` are re-split at a stricter
    edge threshold (recursively) purely to cap memory.

    Returns integer labels, -1 for noise, contiguous from 0.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from sklearn.cluster import AgglomerativeClustering

    n = X_norm.shape[0]
    labels = np.full(n, -1, dtype=np.int64)
    if n == 0:
        return labels

    rows, cols = _knn_edges(X_norm, k=k, threshold=edge_threshold)

    # ── Core-point rule (DBSCAN semantics, as used by Immich) ────────────────
    # A face may JOIN a cluster but may only EXTEND one if it has at least
    # `min_core_neighbors` similar neighbours. This stops a single ambiguous
    # face (motion-blurred, half-lit, partially occluded) from chaining two
    # different people into one identity — the classic contamination mode.
    if min_core_neighbors > 0 and len(rows):
        degree = np.bincount(rows, minlength=n)
        is_core = degree >= min_core_neighbors
        core_edge = is_core[rows] & is_core[cols]
        rows_core, cols_core = rows[core_edge], cols[core_edge]
        print(f"[PixelRAG] core-point rule: {int(is_core.sum())}/{n} faces are core "
              f"(>= {min_core_neighbors} neighbours); "
              f"{len(rows) - len(rows_core)} non-core edges suppressed")
    else:
        is_core = np.ones(n, dtype=bool)
        rows_core, cols_core = rows, cols

    graph = coo_matrix(
        (np.ones(len(rows_core), dtype=np.int8), (rows_core, cols_core)), shape=(n, n)
    )
    n_comp, comp_labels = connected_components(graph, directed=False)

    # ── Instrumentation (no behaviour change) ────────────────────────────────
    # The exactness guarantee only holds while components stay under max_exact:
    # above that we re-split at a stricter edge threshold, which IS an
    # approximation. Quality gates are loose (MIN_DET_SCORE 0.50,
    # MIN_LAPLACIAN_VAR 10.0), so blurry faces get embedded, and blurry
    # embeddings drift toward the centre of the space where they can bridge two
    # identities into one giant component. Surface that rather than hide it.
    if _stats is None:
        _stats = {"max_depth": 0, "oversized_faces": 0, "total_faces": n, "recursions": 0}
    _stats["max_depth"] = max(_stats["max_depth"], _depth)

    comp_sizes = np.bincount(comp_labels, minlength=n_comp)
    top5 = np.sort(comp_sizes)[::-1][:5]
    n_over = int(comp_sizes[comp_sizes > max_exact].sum())
    pad = "  " * _depth
    print(f"[PixelRAG] {pad}kNN graph: {len(rows_core)} edges -> {n_comp} components "
          f"(edge_sim>={edge_threshold}, k={k}, linkage={linkage_method}, depth={_depth})")
    print(f"[PixelRAG] {pad}  component sizes: largest5={top5.tolist()} "
          f"| >max_exact({max_exact}): {n_over} faces = {100.0*n_over/max(n,1):.1f}%")
    if _depth == 0:
        largest_frac = 100.0 * (int(top5[0]) if len(top5) else 0) / max(n, 1)
        if largest_frac > 5.0:
            print(f"[PixelRAG]   ⚠️  LARGEST COMPONENT HOLDS {largest_frac:.1f}% OF ALL FACES. "
                  f"If it exceeds max_exact the exactness guarantee no longer applies "
                  f"to most of the library — suspect blurry-face bridging.")

    next_label = 0
    oversized = 0

    for comp_id in range(n_comp):
        idx = np.flatnonzero(comp_labels == comp_id)
        m = len(idx)

        if m < min_cluster_size:
            continue  # too small to be an identity — stays noise

        if m > max_exact:
            # Cap memory: re-split this component with a stricter edge rule.
            # NOTE: this branch is the ONLY place the result stops being exactly
            # equivalent to global clustering, which is why it is counted.
            oversized += 1
            _stats["oversized_faces"] += m
            _stats["recursions"] += 1
            stricter = min(edge_threshold + 0.05, 0.90)
            sub = _scalable_agglomerative(
                X_norm[idx], distance_threshold, min_cluster_size,
                max_exact=max_exact, edge_threshold=stricter, k=k,
                linkage_method=linkage_method, min_core_neighbors=min_core_neighbors,
                _depth=_depth + 1, _stats=_stats,
            )
            valid = sub >= 0
            labels[idx[valid]] = sub[valid] + next_label
            if valid.any():
                next_label += int(sub[valid].max()) + 1
            continue

        if m == min_cluster_size == 1:
            labels[idx] = next_label
            next_label += 1
            continue

        sub_labels = _cluster_component(X_norm[idx], distance_threshold, linkage_method)

        uniq, counts = np.unique(sub_labels, return_counts=True)
        for lbl, cnt in zip(uniq, counts):
            if cnt < min_cluster_size:
                continue  # singleton/small -> noise
            labels[idx[sub_labels == lbl]] = next_label
            next_label += 1

    if oversized:
        print(f"[PixelRAG] {pad}{oversized} component(s) exceeded {max_exact} and "
              f"were re-split at a stricter threshold to bound memory.")
    print(f"[PixelRAG] {pad}Scalable clustering produced {next_label} clusters, "
          f"{int((labels == -1).sum())} noise faces.")

    if _depth == 0:
        approx_pct = 100.0 * _stats["oversized_faces"] / max(_stats["total_faces"], 1)
        print(f"[PixelRAG] === clustering structure summary ===")
        print(f"[PixelRAG]   recursion levels used : {_stats['max_depth']}")
        print(f"[PixelRAG]   re-split events       : {_stats['recursions']}")
        print(f"[PixelRAG]   faces via approx path : {_stats['oversized_faces']} "
              f"({approx_pct:.1f}%)  <- exactness guarantee does NOT hold for these")
    return labels


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
    # Each round merges ALL non-conflicting pairs above threshold, not just the
    # single best one. The old one-merge-per-round loop capped at 50 rounds,
    # which silently left thousands of mergeable fragments unmerged on a large
    # library — a correctness ceiling, not just a speed limit.
    max_rounds = 25

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

        n = len(people_ids)
        # Face counts once per round, so we can always fold smaller into larger
        counts = {
            pid: cnt for pid, cnt in conn.execute(
                "SELECT person_id, COUNT(*) FROM faces WHERE person_id IS NOT NULL "
                "GROUP BY person_id"
            )
        }

        # Upper-triangle pairs above threshold, strongest first
        sim_matrix = X_norm @ X_norm.T
        iu, ju = np.triu_indices(n, k=1)
        sims = sim_matrix[iu, ju]
        above = sims >= similarity_threshold
        if not above.any():
            break

        order = np.argsort(-sims[above])
        cand_i, cand_j = iu[above][order], ju[above][order]

        # Greedily accept non-conflicting pairs: an identity may take part in at
        # most one merge per round, so every accepted merge is independent and
        # centroids stay valid until the next round recomputes them.
        used: set = set()
        merged_this_round = 0

        for a, b in zip(cand_i, cand_j):
            pa, pb = people_ids[int(a)], people_ids[int(b)]
            if pa in used or pb in used:
                continue

            target_id, source_id = pa, pb
            if counts.get(source_id, 0) > counts.get(target_id, 0):
                target_id, source_id = source_id, target_id

            conn.execute("UPDATE faces SET person_id = ? WHERE person_id = ?",
                         (target_id, source_id))
            conn.execute("UPDATE clusters SET person_id = ? WHERE person_id = ?",
                         (target_id, source_id))
            conn.execute("DELETE FROM people WHERE id = ?", (source_id,))

            emb_rows = conn.execute(
                "SELECT fe.embedding FROM face_embeddings fe "
                "JOIN faces f ON fe.face_id = f.id WHERE f.person_id = ?",
                (target_id,)
            ).fetchall()
            if emb_rows:
                merged = np.array([np.frombuffer(r[0], dtype=np.float32) for r in emb_rows])
                merged = merged / (np.linalg.norm(merged, axis=1, keepdims=True) + 1e-10)
                centroid = merged.mean(axis=0)
                centroid = centroid / (np.linalg.norm(centroid) + 1e-10)
                conn.execute("UPDATE people SET centroid_embedding = ? WHERE id = ?",
                             (centroid.astype(np.float32).tobytes(), target_id))

            used.add(pa)
            used.add(pb)
            merged_this_round += 1

        total_merges += merged_this_round
        if merged_this_round == 0:
            break
        conn.commit()

    return total_merges


def cluster_all_faces(
    db_path: str,
    folder_root: str,
    min_cluster_size: int = 2,
    distance_threshold: float = CLUSTER_DISTANCE_THRESHOLD,
    linkage_method: str = CLUSTER_LINKAGE,
    min_core_neighbors: int = CLUSTER_MIN_CORE,
) -> Dict[str, int]:
    """
    Cluster ORPHAN face embeddings into identities.

    Confirmed faces are excluded from the clustering input so they don't
    distort cluster boundaries for unassigned faces.

    Defaults are not guesses — they were selected by grading every candidate
    against 567 human-confirmed faces across 7 identities in a real library
    (`scratch/eval_clustering.py`). See CLUSTER_* constants for the numbers.

    :param min_cluster_size: Minimum faces to form a cluster
    :param distance_threshold: Max cosine distance for the linkage criterion
    :param linkage_method: 'median' (default) or 'average'/'complete'
    :param min_core_neighbors: DBSCAN-style core-point rule; 0 disables
    """
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

    # Cluster orphan faces. A single global AgglomerativeClustering call
    # materializes the full n^2 distance matrix — at ~40k faces that is ~12.8 GB
    # and dies on a 16 GB machine. _scalable_agglomerative computes the same
    # result via kNN graph -> connected components -> exact clustering per
    # component, with peak memory bounded by chunk size, not by n.
    labels = _scalable_agglomerative(
        X_orphan,
        distance_threshold=distance_threshold,
        min_cluster_size=min_cluster_size,
        linkage_method=linkage_method,
        min_core_neighbors=min_core_neighbors,
    )
    unique_labels = set(labels.tolist())

    n_clusters = int(labels.max()) + 1 if (labels >= 0).any() else 0
    n_noise = int(np.sum(labels == -1))
    print(f"[PixelRAG] Clustering found {n_clusters} clusters, {n_noise} noise faces (threshold={distance_threshold}).")

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

        # ── Heal dangling cluster_ids before allocating new ones ─────────────
        # scrub_cross_library_contamination() does `DELETE FROM clusters` but
        # leaves faces.cluster_id populated. New ids restart at MAX(id)+1 = 1,
        # so they COLLIDE with those stale values. Measured on the real library:
        # 28 confirmed faces silently jumped to the wrong person because
        # `UPDATE faces SET person_id=? WHERE cluster_id=?` swept up strangers
        # carrying a recycled id. Null them out so no id is ambiguous.
        healed = conn.execute(
            "UPDATE faces SET cluster_id = NULL "
            "WHERE cluster_id IS NOT NULL AND cluster_id NOT IN (SELECT id FROM clusters)"
        ).rowcount
        if healed:
            print(f"[PixelRAG] Cleared {healed} dangling cluster_id references.")
        conn.commit()

        # Assign orphan faces to clusters (all faces in labels are orphans by design)
        # Track the exact face ids per cluster from THIS run — person assignment
        # below uses these lists rather than a `WHERE cluster_id = ?` lookup, so
        # a recycled id can never pull in unrelated faces again.
        from collections import defaultdict as _dd
        cluster_face_ids: Dict[int, List[int]] = _dd(list)

        faces_assigned = 0
        for i, (face_id, lbl) in enumerate(zip(orphan_face_ids, labels)):
            if lbl == -1:
                # Noise: cluster_id stays NULL
                conn.execute("UPDATE faces SET cluster_id = NULL WHERE id = ?", (int(face_id),))
            else:
                cluster_id = label_to_cluster_id[lbl]
                conn.execute("UPDATE faces SET cluster_id = ? WHERE id = ?", (cluster_id, int(face_id)))
                cluster_face_ids[cluster_id].append(int(face_id))
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
                # Assign by the explicit face ids produced by THIS run. Using
                # `WHERE cluster_id = ?` here was the bug that moved 28 confirmed
                # faces to the wrong person when an id got recycled.
                fids = cluster_face_ids.get(cluster_id, [])
                if fids:
                    ph = ",".join("?" for _ in fids)
                    conn.execute(
                        f"UPDATE faces SET person_id = ? WHERE id IN ({ph})",
                        [person_id, *fids],
                    )
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
