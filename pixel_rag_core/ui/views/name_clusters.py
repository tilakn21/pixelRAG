# pixel_rag_core/ui/pages/name_clusters.py
"""
Identity Manager — cluster naming, purity indicators, merge/split.
Shows face samples per cluster with quality badges and management tools.
"""

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _get_purity_badge(purity_score):
    """Return colored badge HTML and label based on purity score."""
    if purity_score is None:
        return "⚪", "N/A"
    if purity_score >= 0.72:
        return "🟢", f"{purity_score:.2f}"
    elif purity_score >= 0.60:
        return "🟡", f"{purity_score:.2f}"
    else:
        return "🔴", f"{purity_score:.2f}"


def _get_clusters(db_path: str, named_only: bool = False) -> list:
    """Return clusters sorted by purity (worst first for unnamed)."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    if named_only:
        rows = conn.execute("""
            SELECT c.id, ppl.name, ppl.purity_score, ppl.confirmed,
                   COUNT(f.id) as face_count, ppl.id as person_id
            FROM clusters c
            JOIN people ppl ON c.person_id = ppl.id
            JOIN faces f ON f.cluster_id = c.id
            WHERE ppl.name NOT LIKE 'Cluster_%'
              AND ppl.name != 'Unknown'
            GROUP BY c.id
            ORDER BY face_count DESC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT c.id, ppl.name, ppl.purity_score, ppl.confirmed,
                   COUNT(f.id) as face_count, ppl.id as person_id
            FROM clusters c
            LEFT JOIN people ppl ON c.person_id = ppl.id
            JOIN faces f ON f.cluster_id = c.id
            WHERE ppl.name IS NULL OR ppl.name LIKE 'Cluster_%'
            GROUP BY c.id
            ORDER BY COALESCE(ppl.purity_score, 1.0) ASC
        """).fetchall()

    conn.close()
    return rows  # [(cluster_id, name, purity_score, confirmed, face_count, person_id), ...]


def _get_face_crop_thumbnails(db_path: str, cluster_id: int, limit: int = 8) -> list:
    """Return up to N face crop images from different source photos."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute("""
        SELECT DISTINCT p.path, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
        WHERE f.cluster_id = ?
        GROUP BY p.id
        LIMIT ?
    """, (cluster_id, limit)).fetchall()
    conn.close()

    crops = []
    for path, x1, y1, x2, y2 in rows:
        try:
            img_path = Path(path)
            if not img_path.exists():
                continue

            pil_img = Image.open(img_path)
            pil_img = ImageOps.exif_transpose(pil_img)
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')

            w, h = pil_img.size
            # Add padding around the face crop
            fw = x2 - x1
            fh = y2 - y1
            pad_x = int(fw * 0.3)
            pad_y = int(fh * 0.3)

            crop_x1 = max(0, int(x1) - pad_x)
            crop_y1 = max(0, int(y1) - pad_y)
            crop_x2 = min(w, int(x2) + pad_x)
            crop_y2 = min(h, int(y2) + pad_y)

            face_crop = pil_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            face_crop.thumbnail((150, 150))
            
            import io
            b = io.BytesIO()
            face_crop.save(b, format='JPEG')
            crops.append(b.getvalue())
        except Exception:
            continue

    return crops


def _get_similar_clusters(db_path: str, cluster_id: int, top_n: int = 5) -> list:
    """Find the most similar clusters by centroid cosine similarity."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    # Get the centroid of the target cluster
    target_row = conn.execute("""
        SELECT ppl.centroid_embedding
        FROM clusters c
        JOIN people ppl ON c.person_id = ppl.id
        WHERE c.id = ?
    """, (cluster_id,)).fetchone()

    if not target_row or not target_row[0]:
        conn.close()
        return []

    target_centroid = np.frombuffer(target_row[0], dtype=np.float32)

    # Get all other clusters with centroids
    others = conn.execute("""
        SELECT c.id, ppl.name, ppl.centroid_embedding, COUNT(f.id) as face_count
        FROM clusters c
        JOIN people ppl ON c.person_id = ppl.id
        JOIN faces f ON f.cluster_id = c.id
        WHERE c.id != ? AND ppl.centroid_embedding IS NOT NULL
        GROUP BY c.id
    """, (cluster_id,)).fetchall()
    conn.close()

    similarities = []
    for cid, name, centroid_blob, fcount in others:
        other_centroid = np.frombuffer(centroid_blob, dtype=np.float32)
        # Cosine similarity
        sim = float(np.dot(target_centroid, other_centroid) / (
            np.linalg.norm(target_centroid) * np.linalg.norm(other_centroid) + 1e-10
        ))
        similarities.append((cid, name or f"Cluster_{cid}", sim, fcount))

    similarities.sort(key=lambda x: x[2], reverse=True)
    return similarities[:top_n]


def _assign_name_to_cluster(db_path: str, cluster_id: int, name: str):
    """Create/find a Person with this name and assign the cluster to them."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Get or create person
    existing = conn.execute("SELECT id FROM people WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        person_id = existing[0]
        conn.execute("UPDATE people SET confirmed = 1 WHERE id = ?", (person_id,))
    else:
        cur = conn.execute(
            "INSERT INTO people (name, confirmed) VALUES (?, 1)", (name,)
        )
        person_id = cur.lastrowid

    # Link cluster to person and update all faces in this cluster
    conn.execute("UPDATE clusters SET person_id = ? WHERE id = ?", (person_id, cluster_id))
    conn.execute("UPDATE faces SET person_id = ? WHERE cluster_id = ?", (person_id, cluster_id))

    # Get the old placeholder person and clean up if orphaned
    old_person = conn.execute(
        "SELECT person_id FROM clusters WHERE id = ?", (cluster_id,)
    ).fetchone()
    if old_person and old_person[0] and old_person[0] != person_id:
        # Check if old person has other clusters
        other_clusters = conn.execute(
            "SELECT COUNT(*) FROM clusters WHERE person_id = ?", (old_person[0],)
        ).fetchone()[0]
        if other_clusters == 0:
            conn.execute("DELETE FROM people WHERE id = ? AND name LIKE 'Cluster_%'", (old_person[0],))

    conn.commit()
    conn.close()


def _merge_clusters(db_path: str, surviving_id: int, dissolving_id: int):
    """Merge dissolving cluster into surviving cluster."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Move all faces from dissolving to surviving
    conn.execute(
        "UPDATE faces SET cluster_id = ? WHERE cluster_id = ?",
        (surviving_id, dissolving_id)
    )

    # Get dissolving person to clean up
    dissolving_person = conn.execute(
        "SELECT person_id FROM clusters WHERE id = ?", (dissolving_id,)
    ).fetchone()

    # Delete the dissolved cluster
    conn.execute("DELETE FROM clusters WHERE id = ?", (dissolving_id,))

    # Clean up orphaned placeholder person
    if dissolving_person and dissolving_person[0]:
        conn.execute(
            "DELETE FROM people WHERE id = ? AND name LIKE 'Cluster_%'",
            (dissolving_person[0],)
        )

    conn.commit()

    # Recompute centroid and purity for surviving cluster
    _recompute_cluster_stats(conn, surviving_id)

    conn.commit()
    conn.close()


def _split_cluster(db_path: str, source_cluster_id: int, face_ids_to_split: list):
    """Split selected faces out of a cluster into a new cluster."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Create new cluster
    max_id = conn.execute("SELECT MAX(id) FROM clusters").fetchone()[0] or 0
    new_cluster_id = max_id + 1

    # Create placeholder person for new cluster
    cur = conn.execute(
        "INSERT INTO people (name, confirmed) VALUES (?, 0)",
        (f"Cluster_{new_cluster_id}",)
    )
    new_person_id = cur.lastrowid

    conn.execute(
        "INSERT INTO clusters (id, person_id, label) VALUES (?, ?, NULL)",
        (new_cluster_id, new_person_id)
    )

    # Move selected faces
    for face_id in face_ids_to_split:
        conn.execute(
            "UPDATE faces SET cluster_id = ?, person_id = NULL WHERE id = ?",
            (new_cluster_id, face_id)
        )

    conn.commit()

    # Recompute stats for both clusters
    _recompute_cluster_stats(conn, source_cluster_id)
    _recompute_cluster_stats(conn, new_cluster_id)

    conn.commit()
    conn.close()
    return new_cluster_id


def _recompute_cluster_stats(conn: sqlite3.Connection, cluster_id: int):
    """Recompute centroid and purity for a cluster."""
    # Load embeddings
    rows = conn.execute("""
        SELECT fe.embedding, fe.dim
        FROM faces f
        JOIN face_embeddings fe ON f.id = fe.face_id
        WHERE f.cluster_id = ?
    """, (cluster_id,)).fetchall()

    if len(rows) < 2:
        return

    embeddings = []
    for emb_blob, dim in rows:
        vec = np.frombuffer(emb_blob, dtype=np.float64, count=dim)
        embeddings.append(vec)

    X = np.vstack(embeddings)

    # Compute centroid
    mean = X.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    centroid_blob = mean.astype(np.float32).tobytes()

    # Compute purity
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    normed = X / (norms + 1e-10)
    sim_matrix = normed @ normed.T
    n = len(X)
    purity = float((sim_matrix.sum() - np.trace(sim_matrix)) / (n * (n - 1))) if n > 1 else 1.0

    # Update person
    person_row = conn.execute(
        "SELECT person_id FROM clusters WHERE id = ?", (cluster_id,)
    ).fetchone()
    if person_row and person_row[0]:
        conn.execute(
            "UPDATE people SET centroid_embedding = ?, purity_score = ? WHERE id = ?",
            (centroid_blob, purity, person_row[0])
        )


def _get_all_faces_for_cluster(db_path: str, cluster_id: int) -> list:
    """Get all face details for split interface."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute("""
        SELECT f.id, p.path, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
        WHERE f.cluster_id = ?
    """, (cluster_id,)).fetchall()
    conn.close()
    return rows


def render(library: dict):
    from pixel_rag_core.library.library_manager import ensure_library_db

    db_path = str(ensure_library_db(library["path"]))

    st.title("🏷️ Identity Manager")
    st.caption(f"Library: **{library['name']}**")

    # Tabs for unnamed and named clusters
    tab_unnamed, tab_named = st.tabs(["🔍 Unnamed Clusters", "✅ Named People"])

    with tab_unnamed:
        _render_unnamed_clusters(db_path)

    with tab_named:
        _render_named_clusters(db_path)


def _render_unnamed_clusters(db_path: str):
    clusters = _get_clusters(db_path, named_only=False)

    if not clusters:
        st.success("🎉 All clusters are named! Head to Search to explore your library.")
        if st.button("→ Go to Search", type="primary"):
            st.session_state["page"] = "search"
            st.rerun()
        return

    st.markdown(f"**{len(clusters)} unnamed clusters** — sorted by purity (worst first)")
    st.markdown("---")

    for cluster_id, name, purity_score, confirmed, face_count, person_id in clusters:
        badge, score_str = _get_purity_badge(purity_score)

        with st.expander(
            f"{badge} Cluster #{cluster_id} — {face_count} photos — Purity: {score_str}",
            expanded=True,
        ):
            # ── Face thumbnails ─────────────────────────────────────
            crops = _get_face_crop_thumbnails(db_path, cluster_id, limit=8)
            if crops:
                cols = st.columns(min(len(crops), 4))
                for i, crop in enumerate(crops):
                    with cols[i % len(cols)]:
                        st.image(crop, width="stretch")

            st.markdown("---")

            # ── Inline naming ───────────────────────────────────────
            col_name, col_btn = st.columns([3, 1])
            with col_name:
                name_val = st.text_input(
                    "Name this person:",
                    key=f"name_{cluster_id}",
                    placeholder="e.g. Tilak, Shriyash, Mom...",
                )
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ Save", key=f"save_{cluster_id}", disabled=not name_val):
                    _assign_name_to_cluster(db_path, cluster_id, name_val.strip())
                    st.success(f"Saved as '{name_val.strip()}'!")
                    st.rerun()

            # ── Merge interface ─────────────────────────────────────
            similar = _get_similar_clusters(db_path, cluster_id)
            if similar:
                st.markdown("**🔗 Merge with similar cluster:**")
                for sim_cid, sim_name, sim_score, sim_fcount in similar:
                    sim_label = f"{sim_name} ({sim_fcount} photos, similarity: {sim_score:.2f})"
                    if st.button(
                        f"Merge → {sim_label}",
                        key=f"merge_{cluster_id}_{sim_cid}",
                    ):
                        _merge_clusters(db_path, sim_cid, cluster_id)
                        st.success(f"Merged into {sim_name}!")
                        st.rerun()

            # ── Split interface ─────────────────────────────────────
            if face_count >= 6:
                st.markdown("**✂️ Split cluster:**")
                all_faces = _get_all_faces_for_cluster(db_path, cluster_id)
                selected_faces = []

                split_cols = st.columns(4)
                for j, (fid, fpath, fx1, fy1, fx2, fy2) in enumerate(all_faces):
                    with split_cols[j % 4]:
                        try:
                            pil_img = Image.open(fpath)
                            pil_img = ImageOps.exif_transpose(pil_img)
                            if pil_img.mode != 'RGB':
                                pil_img = pil_img.convert('RGB')
                            w, h = pil_img.size
                            crop = pil_img.crop((
                                max(0, int(fx1)), max(0, int(fy1)),
                                min(w, int(fx2)), min(h, int(fy2))
                            ))
                            crop.thumbnail((100, 100))
                            import io
                            b = io.BytesIO()
                            crop.save(b, format='JPEG')
                            st.image(b.getvalue(), width="stretch")
                        except Exception:
                            st.text(f"Face #{fid}")

                        if st.checkbox("Select", key=f"split_{cluster_id}_{fid}"):
                            selected_faces.append(fid)

                if selected_faces and st.button(
                    f"Split {len(selected_faces)} faces out",
                    key=f"do_split_{cluster_id}",
                    type="primary",
                ):
                    new_cid = _split_cluster(db_path, cluster_id, selected_faces)
                    st.success(f"Split into new Cluster #{new_cid}!")
                    st.rerun()

            # ── Skip button ─────────────────────────────────────────
            if st.button("⏭️ Skip (Unknown)", key=f"skip_{cluster_id}"):
                _assign_name_to_cluster(db_path, cluster_id, "Unknown")
                st.rerun()


def _render_named_clusters(db_path: str):
    clusters = _get_clusters(db_path, named_only=True)

    if not clusters:
        st.info("No named people yet. Name clusters in the 'Unnamed Clusters' tab.")
        return

    st.markdown(f"**{len(clusters)} named people**")
    st.markdown("---")

    for cluster_id, name, purity_score, confirmed, face_count, person_id in clusters:
        badge, score_str = _get_purity_badge(purity_score)

        with st.expander(f"{badge} {name} — {face_count} photos — Purity: {score_str}"):
            crops = _get_face_crop_thumbnails(db_path, cluster_id, limit=8)
            if crops:
                cols = st.columns(min(len(crops), 4))
                for i, crop in enumerate(crops):
                    with cols[i % len(cols)]:
                        st.image(crop, width="stretch")
