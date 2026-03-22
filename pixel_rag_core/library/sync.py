# pixel_rag_core/library/sync.py
"""
Incremental sync for already-indexed libraries.
On subsequent opens, only new/modified/deleted files are re-processed.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".bmp"}


def _ensure_sync_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            path          TEXT PRIMARY KEY,
            last_modified REAL NOT NULL,
            indexed_at    TEXT NOT NULL
        )
    """)
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
    Returns (new_files, modified_files, deleted_files).
    """
    conn = sqlite3.connect(db_path)
    _ensure_sync_table(conn)

    # Get what's in the DB
    indexed = {
        row[0]: row[1]
        for row in conn.execute("SELECT path, last_modified FROM indexed_files")
    }

    # Get what's on disk
    on_disk = dict(get_folder_files(folder_path))

    new_files = []
    modified_files = []
    deleted_files = []

    for path, mtime in on_disk.items():
        if path not in indexed:
            new_files.append(path)
        elif abs(mtime - indexed[path]) > 1.0:  # 1 second tolerance
            modified_files.append(path)

    for path in indexed:
        if path not in on_disk:
            deleted_files.append(path)

    conn.close()
    return new_files, modified_files, deleted_files


def mark_files_indexed(db_path: str, file_paths: List[str], folder_path: str):
    """Record that a set of files have been successfully indexed."""
    conn = sqlite3.connect(db_path)
    _ensure_sync_table(conn)
    now = datetime.utcnow().isoformat()

    on_disk = dict(get_folder_files(folder_path))

    for path in file_paths:
        mtime = on_disk.get(path, 0.0)
        conn.execute(
            "INSERT OR REPLACE INTO indexed_files (path, last_modified, indexed_at) VALUES (?, ?, ?)",
            (path, mtime, now),
        )

    conn.commit()
    conn.close()


def remove_deleted_files(db_path: str, deleted_paths: List[str]):
    """Remove deleted files from both the photos table and indexed_files."""
    conn = sqlite3.connect(db_path)
    _ensure_sync_table(conn)

    for path in deleted_paths:
        conn.execute("DELETE FROM photos WHERE path = ?", (path,))
        conn.execute("DELETE FROM indexed_files WHERE path = ?", (path,))

    conn.commit()
    conn.close()


def needs_full_index(folder_path: str, db_path: str) -> bool:
    """Returns True if this folder has never been indexed before."""
    if not Path(db_path).exists():
        return True
    conn = sqlite3.connect(db_path)
    _ensure_sync_table(conn)
    count = conn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    conn.close()
    return count == 0
