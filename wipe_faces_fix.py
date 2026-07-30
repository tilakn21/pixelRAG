"""
PixelRAG Face Data Cleanup Script
Wipes corrupted face metadata from all libraries and clears cached face crops.
Run this before re-syncing after schema/format changes.
"""
import sqlite3
import json
import os
import shutil
from pathlib import Path

# 1. Get current active libraries from config
config_path = Path(__file__).parent / ".pixelrag_config.json"
if not config_path.exists():
    print("Config file not found.")
    exit(1)

with open(config_path, "r") as f:
    config = json.load(f)

for lib_path in config.get("libraries", []):
    pixelrag_dir = Path(lib_path) / ".pixelrag"
    db_path = pixelrag_dir / "db.sqlite"
    
    if not db_path.exists():
        print(f"Skipping (no DB): {lib_path}")
        continue
        
    print(f"\n{'='*60}")
    print(f"Cleaning: {lib_path}")
    print(f"{'='*60}")
    
    conn = sqlite3.connect(db_path)
    try:
        # Clear all face/cluster/people data
        conn.execute("DELETE FROM face_embeddings")
        conn.execute("DELETE FROM faces")
        conn.execute("DELETE FROM clusters")
        conn.execute("DELETE FROM people")
        # Reset photos to 'unprocessed' for faces AND scene classification
        conn.execute("UPDATE photos SET has_faces = NULL, scene_category = NULL, scene_confidence = NULL")
        conn.commit()
        print("  ✅ Database tables cleaned (faces, clusters, people)")
        print("  ✅ Photo metadata reset (has_faces, scene_category)")
    except Exception as e:
        print(f"  ❌ Database error: {e}")
    finally:
        conn.close()
    
    # Clear cached face crops and thumbnails
    thumbs_dir = pixelrag_dir / "thumbs"
    if thumbs_dir.exists():
        # Only clear face crops, preserve photo thumbnails
        faces_cache = thumbs_dir / "faces"
        if faces_cache.exists():
            shutil.rmtree(faces_cache)
            print("  ✅ Face crop cache cleared")
        else:
            print("  ℹ️  No face crop cache found")
    
    print(f"  Done for: {lib_path}")

print(f"\n{'='*60}")
print("All libraries cleaned. You can now SYNC from the PixelRAG UI.")
print(f"{'='*60}")
