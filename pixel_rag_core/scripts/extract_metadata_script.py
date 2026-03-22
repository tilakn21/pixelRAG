# pixel_rag_core/scripts/extract_metadata_script.py

import argparse
import sys
from pathlib import Path

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.db.init_db import init_db
from pixel_rag_core.indexing.metadata_extractor import enrich_photos_metadata
from pixel_rag_core.indexing.reverse_geocode import enrich_photos_with_location
from pixel_rag_core.config import DB_PATH

def main():
    parser = argparse.ArgumentParser(
        description="Extract EXIF metadata for photos and update PixelRAG DB."
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Path to SQLite DB (default: {DB_PATH})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of photos to process in one run.",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip reverse geocoding step (useful for speed or offline use).",
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"[PixelRAG] DB not found at {db_path}, initializing...")
        init_db(str(db_path))

    print(f"[PixelRAG] Extracting metadata into DB: {db_path}")
    updated = enrich_photos_metadata(str(db_path), limit=args.limit)
    print(f"[PixelRAG] Done. Photos updated with metadata: {updated}")

    if not args.skip_geocode:
        print(f"[PixelRAG] Running reverse geocoding for photos with GPS coordinates...")
        geocoded = enrich_photos_with_location(str(db_path))
        if geocoded > 0:
            print(f"[PixelRAG] Geocoded {geocoded} photos with city/state/country.")
        else:
            print(f"[PixelRAG] No new photos needed geocoding (no GPS data or already done).")


if __name__ == "__main__":
    main()
