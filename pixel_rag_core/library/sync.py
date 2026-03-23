# pixel_rag_core/library/sync.py
"""
Incremental sync for already-indexed libraries.
On subsequent opens, only new/modified/deleted files are re-processed.

Upgraded: Content-hash-based change detection instead of mtime.
"""

import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}

# Read in 64KB chunks for efficient hashing
_HASH_CHUNK_SIZE = 65536


def _compute_file_hash(file_path: str) -> str:
    """Compute MD5 hash of a file's contents."""
    h = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(_HASH_CHUNK_SIZE)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _ensure_sync_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            path          TEXT PRIMARY KEY,
            last_modified REAL NOT NULL,
            indexed_at    TEXT NOT NULL,
            file_hash     TEXT
        )
    """)
    # Add file_hash column if missing (migration for existing DBs)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(indexed_files)")
    cols = [row[1] for row in cur.fetchall()]
    if "file_hash" not in cols:
        conn.execute("ALTER TABLE indexed_files ADD COLUMN file_hash TEXT")
    conn.commit()


def get_folder_files(folder_path: str) -> List[Tuple[str, float]]:
    """Walk a folder and return (path, mtime) for all supported images."""
    folder = Path(folder_path)
    results = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            # Skip the .pixelrag hidden dir
            if ".pixelrag" in f.parts:
                continue
            try:
                mtime = f.stat().st_mtime
                results.append((str(f), mtime))
            except Exception:
                pass
    return results


def get_sync_diff(
    folder_path: str, db_path: str
) -> Tuple[List[str], List[str], List[str]]:
    """
    Compare the folder's current files against what's recorded in indexed_files.
    Uses content hashing for reliable change detection across copy/restore operations.
    Returns (new_files, modified_files, deleted_files).
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_sync_table(conn)

    # Get what's in the DB
    indexed = {}
    for row in conn.execute("SELECT path, last_modified, file_hash FROM indexed_files"):
        indexed[row[0]] = {"mtime": row[1], "hash": row[2]}

    # Get what's on disk
    on_disk = dict(get_folder_files(folder_path))

    new_files = []
    modified_files = []
    deleted_files = []

    for path, mtime in on_disk.items():
        if path not in indexed:
            new_files.append(path)
        else:
            record = indexed[path]
            # First quick check: mtime changed?
            if abs(mtime - record["mtime"]) > 1.0:
                # Verify with content hash to avoid false positives
                if record["hash"]:
                    current_hash = _compute_file_hash(path)
                    if current_hash != record["hash"]:
                        modified_files.append(path)
                    # else: mtime changed but content is the same — skip
                else:
                    # No stored hash, fall back to mtime-based detection
                    modified_files.append(path)

    for path in indexed:
        if path not in on_disk:
            deleted_files.append(path)

    conn.close()
    return new_files, modified_files, deleted_files


def mark_files_indexed(db_path: str, file_paths: List[str], folder_path: str):
    """Record that a set of files have been successfully indexed, with content hash."""
    now = datetime.utcnow().isoformat()
    on_disk = dict(get_folder_files(folder_path))

    # Pre-compute all hashes so we don't hold the DB transaction open for minutes
    records = []
    for path in file_paths:
        mtime = on_disk.get(path, 0.0)
        file_hash = _compute_file_hash(path)
        records.append((path, mtime, now, file_hash))

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_sync_table(conn)

    conn.executemany(
        "INSERT OR REPLACE INTO indexed_files (path, last_modified, indexed_at, file_hash) VALUES (?, ?, ?, ?)",
        records
    )

    conn.commit()
    conn.close()


def remove_deleted_files(db_path: str, deleted_paths: List[str]):
    """
    Remove deleted files from both the photos table and indexed_files.
    Cascade-deletes face_embeddings and cleans up orphaned people rows.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_sync_table(conn)

    for path in deleted_paths:
        # Get photo_id before deleting
        photo_row = conn.execute("SELECT id FROM photos WHERE path = ?", (path,)).fetchone()

        if photo_row:
            photo_id = photo_row[0]

            # Get face_ids associated with this photo
            face_rows = conn.execute("SELECT id FROM faces WHERE photo_id = ?", (photo_id,)).fetchall()

            # Delete face_embeddings (cascade via FK or manually)
            for (face_id,) in face_rows:
                conn.execute("DELETE FROM face_embeddings WHERE face_id = ?", (face_id,))

            # Delete faces
            conn.execute("DELETE FROM faces WHERE photo_id = ?", (photo_id,))

            # Delete the photo
            conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))

        conn.execute("DELETE FROM indexed_files WHERE path = ?", (path,))

    # Clean up orphaned people (placeholder names with no remaining faces)
    conn.execute("""
        DELETE FROM people WHERE id IN (
            SELECT ppl.id FROM people ppl
            LEFT JOIN faces f ON f.person_id = ppl.id
            LEFT JOIN clusters c ON c.person_id = ppl.id
            LEFT JOIN faces f2 ON f2.cluster_id = c.id
            WHERE f.id IS NULL AND f2.id IS NULL
              AND ppl.name LIKE 'Cluster_%'
        )
    """)

    conn.commit()
    conn.close()


def needs_full_index(folder_path: str, db_path: str) -> bool:
    """Returns True if this folder has never been indexed before."""
    if not Path(db_path).exists():
        return True
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_sync_table(conn)
    count = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    conn.close()
    return count == 0
