# pixel_rag_core/ui/pages/name_clusters.py
"""
In-app cluster naming gallery.
Shows face samples per cluster, lets user type a name or skip.
"""

import sqlite3
import sys
from pathlib import Path

import streamlit as st
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _get_unnamed_clusters(db_path: str) -> list:
    """Return clusters that have no person assigned."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT c.id, COUNT(f.id) as face_count
        FROM clusters c
        JOIN faces f ON f.cluster_id = c.id
        WHERE c.person_id IS NULL
        GROUP BY c.id
        ORDER BY face_count DESC
    """).fetchall()
    conn.close()
    return rows  # [(cluster_id, face_count), ...]


def _get_sample_face_images(db_path: str, cluster_id: int, limit: int = 5) -> list:
    """Return up to N photo paths for a given cluster."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT DISTINCT p.path
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
        WHERE f.cluster_id = ?
        LIMIT ?
    """, (cluster_id, limit)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _assign_name_to_cluster(db_path: str, cluster_id: int, name: str):
    """Create/find a Person with this name and assign the cluster to them."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Get or create person
    existing = conn.execute("SELECT id FROM people WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        person_id = existing[0]
    else:
        cur = conn.execute("INSERT INTO people (name) VALUES (?)", (name,))
        person_id = cur.lastrowid

    # Link cluster to person and update all faces in this cluster
    conn.execute("UPDATE clusters SET person_id = ? WHERE id = ?", (person_id, cluster_id))
    conn.execute("UPDATE faces SET person_id = ? WHERE cluster_id = ?", (person_id, cluster_id))

    conn.commit()
    conn.close()


def render(library: dict):
    from pixel_rag_core.library.library_manager import get_library_db
    db_path = str(get_library_db(library["path"]))

    st.title("🏷️ Name Your People")
    st.caption(f"Library: **{library['name']}**")
    st.markdown("Label each face cluster so PixelRAG can find them in your searches.")

    clusters = _get_unnamed_clusters(db_path)

    if not clusters:
        st.success("🎉 All clusters are named! Head to Search to explore your library.")
        if st.button("→ Go to Search", type="primary"):
            st.session_state["page"] = "search"
            st.rerun()
        return

    # Progress
    conn = sqlite3.connect(db_path)
    total_clusters = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
    conn.close()
    named_count = total_clusters - len(clusters)

    st.progress(named_count / total_clusters if total_clusters > 0 else 0)
    st.caption(f"**{named_count} / {total_clusters}** clusters named")
    st.markdown("---")

    # Show the first unnamed cluster
    cluster_id, face_count = clusters[0]

    st.subheader(f"Who is this? ({face_count} photos)")

    sample_paths = _get_sample_face_images(db_path, cluster_id)
    cols = st.columns(len(sample_paths) if sample_paths else 1)
    for i, path in enumerate(sample_paths):
        with cols[i]:
            img_path = Path(path)
            if img_path.exists():
                try:
                    img = Image.open(img_path)
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.thumbnail((300, 300))
                    st.image(img, use_container_width=True)
                except Exception:
                    st.error("⚠️ Load error")

    st.markdown("---")
    name_key = f"name_input_{cluster_id}"
    name = st.text_input(
        "Enter the person's name:",
        key=name_key,
        placeholder="e.g. Tilak, Shriyash, Mom...",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Save Name", type="primary", use_container_width=True, disabled=not name.strip()):
            _assign_name_to_cluster(db_path, cluster_id, name.strip())
            st.success(f"Saved as '{name.strip()}'!")
            st.rerun()
    with col2:
        if st.button("⏭️ Skip (Unknown)", use_container_width=True):
            # Assign to a generic "Unknown" bucket, handled separately
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE clusters SET person_id = NULL, label = 'Unknown' WHERE id = ?", (cluster_id,))
            conn.commit()
            conn.close()
            _assign_name_to_cluster(db_path, cluster_id, "Unknown")
            st.rerun()
