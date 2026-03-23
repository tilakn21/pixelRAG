# pixel_rag_core/ui/app.py
"""
PixelRAG — Main Streamlit App Shell
Multi-page app with sidebar library switcher.
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.library.library_manager import (
    list_libraries,
    add_library,
    remove_library,
    get_library_db,
)

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PixelRAG",
    page_icon="🖼️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark sidebar */
    section[data-testid="stSidebar"] { background-color: #111318; }
    /* Full dark background */
    .main { background-color: #0e1117; }
    /* Library card hover */
    div[data-testid="column"] button { border-radius: 10px !important; }
    /* Search bar */
    .stTextInput > div > div > input {
        background-color: #1e2130;
        border-radius: 10px;
        border: 1px solid #3a3d52;
        padding: 14px;
        font-size: 1.1rem;
        color: white;
    }
    /* Progress bar */
    .stProgress > div > div { background-color: #6c63ff; }
</style>
""", unsafe_allow_html=True)

# ─── Session State Init ────────────────────────────────────────────────────────
if "active_library" not in st.session_state:
    st.session_state["active_library"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "home"

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🖼️ PixelRAG")
    st.markdown("*Your AI Photo Library*")
    st.markdown("---")

    libraries = list_libraries()
    active = st.session_state["active_library"]

    if libraries:
        st.markdown("### 📚 Libraries")
        for lib in libraries:
            icon = "✅" if lib["is_indexed"] else "📁"
            label = f"{icon} {lib['name']}"
            is_active = active and active["path"] == lib["path"]

            if st.button(
                label,
                key=f"lib_{lib['path']}",
                type="primary" if is_active else "secondary",
                use_container_width=True,
            ):
                st.session_state["active_library"] = lib
                st.session_state["page"] = "home"
                st.rerun()
    else:
        st.info("No libraries yet.\nAdd a folder below to get started.")

    st.markdown("---")
    st.markdown("### ➕ Add Library")
    new_folder = st.text_input("Folder path:", placeholder="/Users/you/Photos/2024", key="new_folder_input")
    if st.button("Add Library", use_container_width=True, type="primary"):
        if new_folder.strip():
            try:
                lib = add_library(new_folder.strip())
                st.session_state["active_library"] = lib
                st.session_state["page"] = "home"
                st.success(f"Added: {lib['name']}")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        else:
            st.warning("Please enter a folder path.")

    # Navigation for active library
    if active:
        st.markdown("---")
        st.markdown("### 🗺️ Navigate")
        nav_pages = {
            "🏠 Home / Sync": "home",
            "🔍 Search": "search",
            "📷 Browse": "browse",
            "🏷️ Identity Manager": "name_clusters",
        }
        for label, page_key in nav_pages.items():
            if st.button(label, use_container_width=True, key=f"nav_{page_key}"):
                st.session_state["page"] = page_key
                st.rerun()

        st.markdown("---")
        if st.button("🗑️ Remove Library", use_container_width=True):
            remove_library(active["path"])
            st.session_state["active_library"] = None
            st.session_state["page"] = "home"
            st.rerun()

# ─── Main Content ─────────────────────────────────────────────────────────────
active = st.session_state["active_library"]

if not active:
    # Landing page — no library selected
    st.markdown("<br>" * 3, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("# 🖼️ Welcome to PixelRAG")
        st.markdown("### Your self-hosted AI photo library")
        st.markdown("""
        **PixelRAG** lets you search your personal photos using natural language — just like Google Photos, 
        but running entirely on your own machine with no data leaving your device.
        
        **To get started**, add a photo folder in the sidebar →
        
        ---
        
        #### ✨ Features
        - 🔍 **Natural Language Search** — "Photos of Tilak in 2023"
        - 👤 **Face Recognition** — Automatically groups people together
        - 📍 **Location Awareness** — GPS reverse geocoding + vision AI
        - 🔄 **Incremental Sync** — Only re-processes new/changed photos
        - 📚 **Multi-Library** — Switch between different photo folders
        """)
else:
    # Render the active page
    page = st.session_state["page"]

    if page == "home":
        from pixel_rag_core.ui.views import home
        home.render(active)

    elif page == "search":
        from pixel_rag_core.ui.views import search
        search.render(active)

    elif page == "browse":
        from pixel_rag_core.ui.views import browse_categories
        browse_categories.render(active)

    elif page == "name_clusters":
        from pixel_rag_core.ui.views import name_clusters
        name_clusters.render(active)

    else:
        st.error(f"Unknown page: {page}")
