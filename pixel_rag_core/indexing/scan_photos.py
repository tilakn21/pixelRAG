# pixel_rag_core/indexing/scan_photos.py

import sqlite3
from pathlib import Path
from typing import Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp"}


def iter_image_files(root_dir: Path) -> Iterable[Path]:
    """
    Recursively yield all image files under root_dir, skipping hidden folders (starting with .).
    """
    try:
        items = root_dir.iterdir()
    except OSError:
        return

    for path in items:
        try:
            if path.name.startswith("."):
                continue
            if path.is_dir():
                yield from iter_image_files(path)
            elif path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                yield path
        except OSError:
            continue


def scan_and_index_photos(root_dir: str, db_path: str) -> int:
    """
    Scan root_dir for images and insert them into the photos table.

    :param root_dir: Directory to scan (string path)
    :param db_path: Path to SQLite database
    :return: Number of photos inserted (new rows)
    """
    root = Path(root_dir).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Root directory does not exist: {root}")

    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    inserted = 0

    for img_path in iter_image_files(root):
        abs_path = str(img_path.resolve())

        # Use INSERT OR IGNORE to avoid crashing on duplicates
        cur.execute(
            """
            INSERT OR IGNORE INTO photos(path)
            VALUES (?)
            """,
            (abs_path,),
        )

        # rowcount will be 1 only if a new row was inserted
        if cur.rowcount == 1:
            inserted += 1

    conn.commit()
    conn.close()

    return inserted
