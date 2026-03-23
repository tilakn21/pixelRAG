# pixel_rag_core/ui/pages/home.py
"""
First-open page: runs the full ingestion pipeline and shows live progress.
Also handles incremental sync for already-indexed libraries.
"""

import sys
import time
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.library.pipeline import run_full_pipeline
from pixel_rag_core.library.sync import needs_full_index, get_sync_diff, mark_files_indexed, remove_deleted_files
from pixel_rag_core.library.library_manager import ensure_library_db


PIPELINE_STEPS = {
    "scan": "🔍 Scanning Photos",
    "metadata": "📅 Extracting Metadata",
    "geocode": "📍 Reverse Geocoding",
    "faces": "👤 Detecting Faces (with quality gates)",
    "scenes": "🏷️ Classifying Scenes (CLIP)",
    "cluster": "🧬 Clustering Identities (HDBSCAN)",
    "done": "✅ Complete",
}


def render(library: dict):
    folder_path = library["path"]
    db_path = str(ensure_library_db(folder_path))

    st.title(f"📁 {library['name']}")

    if needs_full_index(folder_path, db_path):
        _run_first_open(folder_path, db_path)
    else:
        _run_incremental_sync(folder_path, db_path)


def _run_first_open(folder_path: str, db_path: str):
    st.subheader("🚀 First Time Setup")
    st.info("This folder hasn't been indexed yet. Running the full pipeline now...")

    progress_bar = st.progress(0)
    status_area = st.empty()
    log_area = st.container()

    steps = list(PIPELINE_STEPS.keys())
    messages = []

    for step, message in run_full_pipeline(folder_path, db_path):
        idx = steps.index(step) if step in steps else len(steps) - 1
        progress = int(((idx + 1) / len(steps)) * 100)
        progress_bar.progress(progress)
        status_area.markdown(f"**{PIPELINE_STEPS.get(step, step)}**: {message}")
        messages.append(f"{PIPELINE_STEPS.get(step, step)}: {message}")
        with log_area:
            st.caption(message)

    # Wait a moment for any final DB locks from the pipeline to clear
    time.sleep(2)

    # Mark all files as indexed for future sync
    from pixel_rag_core.library.sync import get_folder_files
    all_files = [p for p, _ in get_folder_files(folder_path)]
    mark_files_indexed(db_path, all_files, folder_path)

    progress_bar.progress(100)
    status_area.success("🎉 Library indexed successfully!")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🏷️ Name Faces →", use_container_width=True, type="primary"):
            st.session_state["page"] = "name_clusters"
            st.rerun()
    with col2:
        if st.button("📷 Browse Categories →", use_container_width=True):
            st.session_state["page"] = "browse"
            st.rerun()


def _run_incremental_sync(folder_path: str, db_path: str):
    new_files, modified_files, deleted_files = get_sync_diff(folder_path, db_path)
    total_changes = len(new_files) + len(modified_files) + len(deleted_files)

    if total_changes == 0:
        st.success(f"✅ Library is up to date. No changes detected.")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🔍 Search Photos", use_container_width=True):
                st.session_state["page"] = "search"
                st.rerun()
        with col2:
            if st.button("📷 Browse", use_container_width=True):
                st.session_state["page"] = "browse"
                st.rerun()
        with col3:
            if st.button("🏷️ Identity Manager", use_container_width=True):
                st.session_state["page"] = "name_clusters"
                st.rerun()
        _render_advanced_settings(folder_path, db_path)
        return

    st.subheader("🔄 Sync Required")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("New Photos", len(new_files))
    with col2:
        st.metric("Modified", len(modified_files))
    with col3:
        st.metric("Deleted", len(deleted_files))

    if st.button("Sync Now →", type="primary", use_container_width=True):
        with st.spinner("Syncing..."):
            from pixel_rag_core.indexing.scan_photos import scan_and_index_photos
            from pixel_rag_core.indexing.metadata_extractor import enrich_photos_metadata
            from pixel_rag_core.faces.face_indexer import index_faces_for_photos
            from pixel_rag_core.faces.cluster_faces import cluster_all_faces
            from pixel_rag_core.indexing.scene_classifier import classify_untagged_photos

            # Handle deletions
            if deleted_files:
                remove_deleted_files(db_path, deleted_files)
                st.info(f"Removed {len(deleted_files)} deleted photos.")

            # Re-scan to pick up new/modified
            if new_files or modified_files:
                scan_and_index_photos(folder_path, db_path)
                enrich_photos_metadata(db_path)
                index_faces_for_photos(db_path)
                classify_untagged_photos(db_path)
                cluster_all_faces(db_path)
                mark_files_indexed(db_path, new_files + modified_files, folder_path)

        st.success("✅ Sync complete!")
        if st.button("Go to Search →", use_container_width=True):
            st.session_state["page"] = "search"
            st.rerun()

    _render_advanced_settings(folder_path, db_path)


def _render_advanced_settings(folder_path: str, db_path: str):
    st.markdown("---")
    with st.expander("⚙️ Advanced Settings / Testing"):
        st.warning("These actions are destructive and intended for testing/debugging.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Reset Entire Library Index", use_container_width=True, help="Wipes all indexed data. The next run will index everything from scratch."):
                from pixel_rag_core.scripts.reset_db import reset_db
                import time
                with st.spinner("Wiping library database..."):
                    reset_db(Path(db_path), full_reset=True)
                    time.sleep(1)
                st.success("Library has been reset.")
                st.rerun()
                
        with col2:
            if st.button("🔄 Reset Face Clusters Only", use_container_width=True, help="Removes clusters and identities, but keeps photos and faces indexed."):
                from pixel_rag_core.scripts.reset_db import reset_db
                import time
                with st.spinner("Deleting face clusters..."):
                    reset_db(Path(db_path), full_reset=False)
                    time.sleep(1)
                st.success("Face clusters have been reset. Re-run sync to cluster again.")
                st.rerun()
