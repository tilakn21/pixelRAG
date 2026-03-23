# pixel_rag_core/library/pipeline.py
"""
Orchestrates the full ingestion pipeline for a new library folder:
  scan → metadata → reverse geocode → face indexing → scene classification → clustering

All functions are thin wrappers around existing logic - nothing new is created here.
Yields (step_name, status) tuples for UI live-progress display.
"""

import sys
from pathlib import Path
from typing import Generator, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_full_pipeline(
    folder_path: str, db_path: str
) -> Generator[Tuple[str, str], None, None]:
    """
    Run the complete ingestion pipeline for a folder.
    Yields (step_name, message) so the UI can display live progress.
    """
    from pixel_rag_core.indexing.scan_photos import scan_and_index_photos
    from pixel_rag_core.indexing.metadata_extractor import enrich_photos_metadata
    from pixel_rag_core.indexing.reverse_geocode import enrich_photos_with_location
    from pixel_rag_core.faces.face_indexer import index_faces_for_photos
    from pixel_rag_core.faces.cluster_faces import cluster_all_faces
    from pixel_rag_core.indexing.scene_classifier import classify_untagged_photos

    # Step 1: Scan
    yield ("scan", "Scanning folder for photos...")
    try:
        count = scan_and_index_photos(folder_path, db_path)
        yield ("scan", f"✅ Found and indexed {count} photos.")
    except Exception as e:
        yield ("scan", f"❌ Scan failed: {e}")
        return

    # Step 2: Metadata (EXIF + filename date parsing)
    yield ("metadata", "Extracting EXIF metadata...")
    try:
        updated = enrich_photos_metadata(db_path)
        yield ("metadata", f"✅ Extracted metadata for {updated} photos.")
    except Exception as e:
        yield ("metadata", f"❌ Metadata extraction failed: {e}")

    # Step 3: Reverse geocoding (only if GPS data found — otherwise instant)
    yield ("geocode", "Checking for GPS coordinates to reverse geocode...")
    try:
        geocoded = enrich_photos_with_location(db_path)
        if geocoded > 0:
            yield ("geocode", f"✅ Reverse geocoded {geocoded} photos.")
        else:
            yield ("geocode", "ℹ️ No GPS data found — skipping reverse geocoding.")
    except Exception as e:
        yield ("geocode", f"⚠️ Geocoding skipped: {e}")

    # Step 4: Face indexing (with quality gates + pHash dedup)
    yield ("faces", "Detecting and embedding faces (with quality filters)...")
    try:
        indexed = index_faces_for_photos(db_path)
        yield ("faces", f"✅ Indexed {indexed} faces.")
    except Exception as e:
        yield ("faces", f"❌ Face indexing failed: {e}")
        return

    # Step 5: Scene classification (CLIP for non-face photos)
    yield ("scenes", "Classifying non-face photos with CLIP...")
    try:
        classified = classify_untagged_photos(db_path)
        yield ("scenes", f"✅ Classified {classified} photos into categories.")
    except Exception as e:
        yield ("scenes", f"⚠️ Scene classification skipped: {e}")

    # Step 6: Clustering (HDBSCAN + purity scoring)
    yield ("cluster", "Clustering faces into identities (HDBSCAN)...")
    try:
        result = cluster_all_faces(db_path)
        n_clusters = result.get("clusters_created", 0)
        yield ("cluster", f"✅ Created {n_clusters} identity clusters.")
    except Exception as e:
        yield ("cluster", f"❌ Clustering failed: {e}")
        return

    yield ("done", "🎉 Library is ready! Go name the clusters and start searching.")
