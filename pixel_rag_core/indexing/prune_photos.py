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

    # ── Unmounted-volume guard ───────────────────────────────────────────────
    # Prune deletes every photo whose file is missing. If the library lives on
    # a removable drive that happens to be unplugged, EVERY path fails
    # .exists() and the entire library would be wiped — 28,512 photos plus
    # cascading faces and identities, all from a drive simply not being
    # connected. Since the DB now lives on local disk, that is a very reachable
    # accident. Refuse to prune unless the root is present and non-empty.
    if not lib_root.is_dir():
        print(f"[PixelRAG] ⚠️  Prune SKIPPED — library root not available: {lib_root}\n"
              f"[PixelRAG]    (drive unmounted? refusing to delete records for files "
              f"we simply cannot see)")
        return 0

    try:
        next(lib_root.iterdir())
    except StopIteration:
        print(f"[PixelRAG] ⚠️  Prune SKIPPED — library root is empty: {lib_root}")
        return 0
    except OSError as e:
        print(f"[PixelRAG] ⚠️  Prune SKIPPED — library root unreadable ({e}): {lib_root}")
        return 0

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

        # 2. Batch delete (chunked to stay under SQLite's bound-variable limit)
        if to_delete:
            conn.execute("PRAGMA foreign_keys = ON")
            CHUNK = 500
            for i in range(0, len(to_delete), CHUNK):
                chunk = to_delete[i:i + CHUNK]
                placeholders = ",".join(["?"] * len(chunk))
                # face_embeddings/photo_embeddings declare ON DELETE CASCADE, but
                # SQLite enforces FKs per-connection (off by default) — delete
                # explicitly so no orphan embedding rows survive a prune.
                cur.execute(
                    f"DELETE FROM face_embeddings WHERE face_id IN "
                    f"(SELECT id FROM faces WHERE photo_id IN ({placeholders}))",
                    chunk,
                )
                cur.execute(f"DELETE FROM faces WHERE photo_id IN ({placeholders})", chunk)
                cur.execute(f"DELETE FROM photo_embeddings WHERE photo_id IN ({placeholders})", chunk)
                cur.execute(f"DELETE FROM photos WHERE id IN ({placeholders})", chunk)

            conn.commit()
            return len(to_delete)
            
        return 0
    finally:
        conn.close()
