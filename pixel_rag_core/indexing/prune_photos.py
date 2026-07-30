# pixel_rag_core/indexing/prune_photos.py

import sqlite3
import os
from pathlib import Path
from typing import List

def prune_missing_photos(library_path: str, db_path: str) -> int:
    """
    Remove photo records that no longer exist on disk or are outside the library root.
    Returns the number of records pruned.
    """
    lib_root = Path(library_path).resolve()
    db_path = Path(db_path).resolve()

    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.cursor()

        # 1. Fetch all photo IDs and paths
        rows = cur.execute("SELECT id, path FROM photos").fetchall()
        
        to_delete = []
        for photo_id, photo_path in rows:
            p = Path(photo_path).resolve()
            
            # Check if exists
            if not p.exists():
                to_delete.append(photo_id)
                continue
                
            # Check if within library root (Professional isolation check)
            try:
                p.relative_to(lib_root)
            except ValueError:
                # Path is not under lib_root
                to_delete.append(photo_id)

        # 2. Batch delete
        if to_delete:
            # We must also delete associated faces, etc. (ON DELETE CASCADE is assumed, but let's be safe)
            # if the schema has proper FKs, this is enough.
            # In our schema (init_db.py), faces.photo_id has NO explicit CASCADE in some versions.
            # Let's check init_db.py later. For now, manual cleanup.
            
            # Placeholders for batch delete
            placeholders = ",".join(["?"] * len(to_delete))
            
            cur.execute(f"DELETE FROM faces WHERE photo_id IN ({placeholders})", to_delete)
            cur.execute(f"DELETE FROM photos WHERE id IN ({placeholders})", to_delete)
            
            conn.commit()
            return len(to_delete)
            
        return 0
    finally:
        conn.close()
