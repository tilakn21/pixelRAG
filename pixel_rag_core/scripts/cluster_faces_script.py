# pixel_rag_core/scripts/cluster_faces_script.py

import argparse
import sys
from pathlib import Path

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.db.init_db import init_db
from pixel_rag_core.faces.cluster_faces import cluster_all_faces
from pixel_rag_core.config import DB_PATH

def main():
    parser = argparse.ArgumentParser(
        description="Cluster face embeddings using HDBSCAN."
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Path to SQLite DB (default: {DB_PATH})",
    )
    parser.add_argument(
        "--min_cluster_size",
        type=int,
        default=3,
        help="Minimum faces to form a cluster (default: 3).",
    )
    parser.add_argument(
        "--min_samples",
        type=int,
        default=2,
        help="HDBSCAN min_samples parameter (default: 2).",
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"[PixelRAG] DB not found at {db_path}, initializing...")
        init_db(str(db_path))

    summary = cluster_all_faces(
        str(db_path),
        min_cluster_size=args.min_cluster_size,
        min_samples=args.min_samples,
    )

    print(f"[PixelRAG] Clustering finished: {summary}")


if __name__ == "__main__":
    main()
