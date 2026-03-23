# pixel_rag_core/ui/pages/search.py
"""
Search page: natural language query → image gallery.
"""

import sys
from pathlib import Path

import streamlit as st
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.query_engine import GraphQueryEngine


@st.cache_resource
def get_engine(db_path: str) -> GraphQueryEngine:
    # Set timeout on engine initialization as well
    return GraphQueryEngine(db_path=db_path)


def render(library: dict):
    from pixel_rag_core.library.library_manager import ensure_library_db

    db_path = str(ensure_library_db(library["path"]))

    st.title("🔍 Search Photos")
    st.caption(f"Library: **{library['name']}** · `{library['path']}`")

    engine = get_engine(db_path)

    prompt = st.text_input(
        "Search your memories...",
        placeholder="e.g. 'Photos of Tilak in 2023', 'Only Shriyash and me', 'Food from Mumbai'",
        key=f"search_{library['path']}",
    )

    if prompt:
        with st.spinner("Analyzing your query with Gemini..."):
            results = engine.run_prompt(prompt)

        paths = results.get("paths", [])
        parsed = results.get("parsed", {})
        error = results.get("error")

        col_info, col_exp = st.columns([3, 1])
        with col_info:
            if error:
                st.warning(f"⚠️ {error}")
            elif paths:
                st.success(f"Found **{len(paths)}** matching photos.")
            else:
                st.warning("No photos found for this query.")

        with col_exp:
            with st.expander("🧠 AI Understanding"):
                st.json(parsed)

        if paths:
            _render_gallery(paths)

    else:
        st.markdown("---")
        _show_recent_photos(db_path)


def _render_gallery(paths: list):
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
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.thumbnail((512, 512))
                        st.image(img, use_container_width=True)
                        st.caption(f"📄 {img_path.name}")
                    except Exception:
                        st.error(f"⚠️ {img_path.name}")
                else:
                    st.warning(f"Missing: {img_path.name}")


def _show_recent_photos(db_path: str):
    """Show recently added photos as a landing state."""
    import sqlite3

    st.subheader("🕐 Recent Photos")
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute(
            "SELECT path FROM photos ORDER BY id DESC LIMIT 12"
        ).fetchall()
        conn.close()
        if rows:
            _render_gallery([r[0] for r in rows])
        else:
            st.info("No photos indexed yet. Go back to Home to index this library.")
    except Exception:
        st.info("Start a search to explore your library.")
