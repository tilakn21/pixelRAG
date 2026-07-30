# pixel_rag_core/library/pipeline.py
"""
Orchestrates the full ingestion pipeline for a new library folder:
  scan → metadata → reverse geocode → face indexing → scene classification → clustering

All functions are thin wrappers around existing logic - nothing new is created here.
Yields (step_name, status) tuples for UI live-progress display.

Hardened:
  - shutdown_event parameter for graceful interruption at stage boundaries
  - Each stage boundary is a natural checkpoint (SQLite commits after each stage)
"""

import sys
import threading
from pathlib import Path
from typing import Generator, Tuple, Optional, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_full_pipeline(
    folder_path: str, 
    db_path: str,
    callback: Optional[Callable[[str, int, int, int, str], None]] = None,
    shutdown_event: Optional[threading.Event] = None,
) -> Generator[Tuple[str, int, int, int, str], None, None]:
    """
    Run the complete ingestion pipeline for a folder.
    Yields (step_name, sub_progress, step_index, total_steps, message) 
    so the UI can display granular live progress.
    The callback can be used for even more granular updates during long-running sub-tasks.
    
    If shutdown_event is set, the pipeline will stop at the next stage boundary
    and yield a "shutdown" status — allowing the next worker to resume from that point.
    """
    from pixel_rag_core.indexing.prune_photos import prune_missing_photos
    from pixel_rag_core.indexing.scan_photos import scan_and_index_photos
    from pixel_rag_core.indexing.metadata_extractor import enrich_photos_metadata
    from pixel_rag_core.indexing.reverse_geocode import enrich_photos_with_location
    from pixel_rag_core.faces.face_indexer import index_faces_for_photos
    from pixel_rag_core.faces.cluster_faces import cluster_all_faces
    from pixel_rag_core.indexing.scene_classifier import classify_untagged_photos

    TOTAL_STEPS = 7

    def _check_shutdown(after_step: str) -> bool:
        """Check if shutdown was requested. Returns True if we should stop."""
        if shutdown_event is not None and shutdown_event.is_set():
            return True
        return False

    # ── Step 0: Prune ────────────────────────────────────────────────────────
    yield ("prune", 0, 1, TOTAL_STEPS, "Pruning missing files from database...")
    try:
        pruned = prune_missing_photos(folder_path, db_path)
        yield ("prune", 100, 1, TOTAL_STEPS, f"✅ Pruned {pruned} stale records.")
    except Exception as e:
        yield ("prune", 0, 1, TOTAL_STEPS, f"⚠️ Pruning skipped: {e}")

    if _check_shutdown("prune"):
        yield ("shutdown", 100, 1, TOTAL_STEPS, "⚠️ Shutdown requested after prune — progress saved.")
        return

    # ── Step 1: Scan ─────────────────────────────────────────────────────────
    yield ("scan", 0, 2, TOTAL_STEPS, "Scanning folder structure...")
    try:
        count = scan_and_index_photos(folder_path, db_path)
        yield ("scan", 100, 2, TOTAL_STEPS, f"✅ Indexed {count} new photos.")
    except Exception as e:
        yield ("scan", 0, 2, TOTAL_STEPS, f"❌ Scan failed: {e}")
        return

    if _check_shutdown("scan"):
        yield ("shutdown", 100, 2, TOTAL_STEPS, "⚠️ Shutdown requested after scan — progress saved.")
        return

    # ── Step 2: Metadata ──────────────────────────────────────────────────────
    yield ("metadata", 0, 3, TOTAL_STEPS, "Extracting EXIF metadata...")
    try:
        updated = enrich_photos_metadata(db_path)
        yield ("metadata", 100, 3, TOTAL_STEPS, f"✅ Metadata enriched for {updated} photos.")
    except Exception as e:
        yield ("metadata", 0, 3, TOTAL_STEPS, f"❌ Metadata failed: {e}")

    if _check_shutdown("metadata"):
        yield ("shutdown", 100, 3, TOTAL_STEPS, "⚠️ Shutdown requested after metadata — progress saved.")
        return

    # ── Step 3: Geocode ───────────────────────────────────────────────────────
    yield ("geocode", 0, 4, TOTAL_STEPS, "Reverse geocoding GPS coordinates...")
    try:
        geocoded = enrich_photos_with_location(db_path)
        msg = f"✅ Geocoded {geocoded} photos." if geocoded > 0 else "ℹ️ No GPS data found."
        yield ("geocode", 100, 4, TOTAL_STEPS, msg)
    except Exception as e:
        yield ("geocode", 0, 4, TOTAL_STEPS, f"⚠️ Geocoding skipped: {e}")

    if _check_shutdown("geocode"):
        yield ("shutdown", 100, 4, TOTAL_STEPS, "⚠️ Shutdown requested after geocode — progress saved.")
        return

    # ── Step 4: Faces ─────────────────────────────────────────────────────────
    yield ("faces", 0, 5, TOTAL_STEPS, "Detecting and embedding faces (InsightFace)...")

    # Clear stale face crop cache to prevent wrong thumbnails after re-indexing.
    # Face crops are cached by face_id, so after a DB reset the same ID may map
    # to a different face.
    try:
        import hashlib
        _lib_hash = hashlib.md5(folder_path.encode()).hexdigest()[:12]
        _face_cache = Path.home() / ".pixelrag" / "thumbs" / _lib_hash / "faces"
        if _face_cache.exists():
            import shutil
            shutil.rmtree(_face_cache)
            print(f"[PixelRAG] Cleared stale face crop cache: {_face_cache}")
    except Exception:
        pass  # Cache clearing must never block the pipeline
    try:
        def face_cb(current, total, msg):
            if callback:
                prog = int((current / total) * 100) if total > 0 else 0
                callback("faces", prog, 5, TOTAL_STEPS, msg)

        indexed = index_faces_for_photos(
            db_path, progress_callback=face_cb,
            shutdown_event=shutdown_event,
        )
        yield ("faces", 100, 5, TOTAL_STEPS, f"✅ Indexed {indexed} faces.")
    except Exception as e:
        yield ("faces", 0, 5, TOTAL_STEPS, f"❌ Face indexing failed: {e}")
        return

    if _check_shutdown("faces"):
        yield ("shutdown", 100, 5, TOTAL_STEPS, "⚠️ Shutdown requested after face indexing — progress saved.")
        return

    # ── Step 5: Scenes ────────────────────────────────────────────────────────
    yield ("scenes", 0, 6, TOTAL_STEPS, "Classifying non-face photos (CLIP)...")
    try:
        def scene_cb(current, total, msg):
            if callback:
                prog = int((current / total) * 100) if total > 0 else 0
                callback("scenes", prog, 6, TOTAL_STEPS, msg)

        classified = classify_untagged_photos(
            db_path, progress_callback=scene_cb,
            shutdown_event=shutdown_event,
        )
        yield ("scenes", 100, 6, TOTAL_STEPS, f"✅ Classified {classified} photos.")
    except Exception as e:
        yield ("scenes", 0, 6, TOTAL_STEPS, f"⚠️ Scene classification skipped: {e}")

    if _check_shutdown("scenes"):
        yield ("shutdown", 100, 6, TOTAL_STEPS, "⚠️ Shutdown requested after scene classification — progress saved.")
        return

    # ── Step 6: Clustering ────────────────────────────────────────────────────
    yield ("cluster", 0, 7, TOTAL_STEPS, "Clustering identities...")
    try:
        result = cluster_all_faces(db_path, folder_path)
        n_clusters = result.get("clusters_created", 0)
        yield ("cluster", 100, 7, TOTAL_STEPS, f"✅ Created {n_clusters} clusters.")
    except Exception as e:
        yield ("cluster", 0, 7, TOTAL_STEPS, f"❌ Clustering failed: {e}")
        return

    yield ("done", 100, 7, TOTAL_STEPS, "🎉 Sync complete!")
