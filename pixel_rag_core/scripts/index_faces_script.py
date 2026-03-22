# pixel_rag_core/scripts/index_faces_script.py

import argparse
import sys
from pathlib import Path

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.db.init_db import init_db
from pixel_rag_core.faces.face_indexer import index_faces_for_photos
from pixel_rag_core.config import DB_PATH

def main():
    parser = argparse.ArgumentParser(
        description="Detect faces and store embeddings into PixelRAG DB."
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
        help="Optional limit on number of photos to process.",
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"[PixelRAG] DB not found at {db_path}, initializing...")
        init_db(str(db_path))

    print(f"[PixelRAG] Indexing faces in photos (db={db_path}) ...")
    inserted = index_faces_for_photos(str(db_path), limit=args.limit)
    print(f"[PixelRAG] Done. Faces inserted: {inserted}")


if __name__ == "__main__":
    main()
