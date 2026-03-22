# pixel_rag_core/scripts/scan_photos_script.py

import argparse
import sys
from pathlib import Path

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.db.init_db import init_db
from pixel_rag_core.indexing.scan_photos import scan_and_index_photos
from pixel_rag_core.config import DB_PATH

def main():
    parser = argparse.ArgumentParser(
        description="Scan a directory for images and index them into PixelRAG DB."
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Root directory containing photos to scan",
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Path to SQLite DB (default: {DB_PATH})",
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    # Ensure DB exists (init if missing)
    if not db_path.exists():
        print(f"[PixelRAG] DB not found at {db_path}, initializing...")
        init_db(str(db_path))

    print(f"[PixelRAG] Scanning photos under: {args.root}")
    inserted = scan_and_index_photos(args.root, str(db_path))
    print(f"[PixelRAG] Done. New photos inserted: {inserted}")


if __name__ == "__main__":
    main()
