# pixel_rag_core/ui/pages/browse_categories.py
"""
Scene Category Browser — Browse photos by CLIP-classified categories.
Displays pill buttons for all 13 categories with photo counts.
Composable with search for combined filtering.
"""

import sqlite3
import sys
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Category display config: (key, emoji, display_name)
CATEGORY_CONFIG = [
    ("people", "👤", "People"),
    ("landscape", "🏞️", "Landscape"),
    ("food", "🍽️", "Food"),
    ("architecture", "🏛️", "Architecture"),
    ("document", "📄", "Documents"),
    ("other", "📦", "Other"),
]


def _get_category_counts(db_path: str) -> dict:
    """Get photo count per scene_category."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute("""
        SELECT scene_category, COUNT(*) as cnt
        FROM photos
        WHERE scene_category IS NOT NULL
        GROUP BY scene_category
    """).fetchall()
    counts = {row[0]: row[1] for row in rows}
    
    # People category uses has_faces=1 OR CLIP's 'people' tag
    people_count = conn.execute("SELECT COUNT(*) FROM photos WHERE has_faces = 1 OR scene_category = 'people'").fetchone()[0]
    counts["people"] = people_count
    
    conn.close()
    return counts


def _get_photos_by_category(db_path: str, category: str,
                            search_term: str = "",
                            limit: int = 60) -> list:
    """Get photo paths filtered by category and optional search text."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    if category == "people":
        query = "SELECT path FROM photos WHERE has_faces = 1 OR scene_category = 'people'"
        params = []
    else:
        query = "SELECT path FROM photos WHERE scene_category = ?"
        params = [category]

    if search_term:
        query += " AND (city LIKE ? OR state LIKE ? OR country LIKE ? OR created_at LIKE ?)"
        search_param = f"%{search_term}%"
        params.extend([search_param, search_param, search_param, search_param])

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _render_gallery(paths: list):
    """Render a responsive photo grid."""
    cols_per_row = 4
    for i in range(0, len(paths), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(paths):
                break
            path = paths[idx]
            img_path = Path(path)
            with col:
                if img_path.exists():
                    try:
                        img = Image.open(img_path)
                        img = ImageOps.exif_transpose(img)
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.thumbnail((512, 512))
                        st.image(img, use_container_width=True)
                        st.caption(f"📄 {img_path.name}")
                    except Exception:
                        st.error(f"⚠️ {img_path.name}")
                else:
                    st.warning(f"Missing: {img_path.name}")


def render(library: dict):
    from pixel_rag_core.library.library_manager import ensure_library_db

    db_path = str(ensure_library_db(library["path"]))

    st.title("📷 Browse by Category")
    st.caption(f"Library: **{library['name']}**")

    # Get counts
    counts = _get_category_counts(db_path)
    total = sum(counts.values())

    if total == 0:
        st.info("No photos have been classified yet. Run the indexing pipeline first.")
        return

    # ── Category pill buttons ──────────────────────────────────────────────
    st.markdown("### Select a category")

    # Initialize selected category in session state
    if "browse_category" not in st.session_state:
        st.session_state["browse_category"] = None

    # Create pill-style buttons in a row
    num_cols = 5
    for row_start in range(0, len(CATEGORY_CONFIG), num_cols):
        cols = st.columns(num_cols)
        for j, col in enumerate(cols):
            idx = row_start + j
            if idx >= len(CATEGORY_CONFIG):
                break
            key, emoji, display = CATEGORY_CONFIG[idx]
            count = counts.get(key, 0)

            with col:
                is_active = st.session_state.get("browse_category") == key
                btn_type = "primary" if is_active else "secondary"
                if st.button(
                    f"{emoji} {display}\n({count})",
                    key=f"cat_{key}",
                    type=btn_type,
                    use_container_width=True,
                ):
                    if is_active:
                        st.session_state["browse_category"] = None
                    else:
                        st.session_state["browse_category"] = key
                    st.rerun()

    # ── Search filter (composable with category) ───────────────────────────
    st.markdown("---")
    search_term = st.text_input(
        "🔎 Filter within category...",
        placeholder="e.g. Shimla, 2023, Mumbai",
        key="browse_search",
    )

    # ── Photo grid ────────────────────────────────────────────────────────
    selected = st.session_state.get("browse_category")

    if selected:
        cat_display = next(
            (f"{e} {d}" for k, e, d in CATEGORY_CONFIG if k == selected),
            selected
        )
        count = counts.get(selected, 0)
        st.subheader(f"{cat_display} — {count} photos")

        paths = _get_photos_by_category(db_path, selected, search_term)
        if paths:
            _render_gallery(paths)
        else:
            st.info(f"No {selected} photos found{' matching your filter' if search_term else ''}.")
    else:
        # Show all categories as overview cards
        st.subheader(f"📊 All Categories ({total} photos)")
        for key, emoji, display in CATEGORY_CONFIG:
            count = counts.get(key, 0)
            if count > 0:
                st.markdown(f"**{emoji} {display}**: {count} photos")
