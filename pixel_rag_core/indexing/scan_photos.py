# pixel_rag_core/indexing/scan_photos.py

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

# .heif and .dng were previously missing — silently dropped 212 images on the
# real library. .dng needs pillow-heif/rawpy to decode; it is indexed either way
# so it is visible and can be handled downstream.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".dng"}

# ── Source facet ─────────────────────────────────────────────────────────────
# Derived from the file's path. This is a PROVENANCE label ("where did this come
# from"), NOT a content category. Folder names are demonstrably unreliable as
# content labels — e.g. this library's `Pictures/Screenshots` actually contains
# edited camera photos — so folder never decides scene_category, only `source`.
# Order matters: first match wins.
_SOURCE_RULES = [
    ("whatsapp",   ("com.whatsapp", "/whatsapp images", "/whatsapp/")),
    ("screenshot_folder", ("/screenshots",)),
    ("scan",       ("adobe scan",)),
    ("instagram",  ("/instagram",)),
    ("snapchat",   ("/snapchat",)),
    ("telegram",   ("/telegram",)),
    ("chatgpt",    ("/chatgpt",)),
    ("lightroom",  ("adobelightroom", "/lightroom")),
    ("download",   ("/download",)),
    ("camera",     ("/dcim", "/camera")),
]


def derive_source(path: str) -> Optional[str]:
    """Classify a photo's provenance from its path. Returns None if unknown."""
    low = path.lower()
    for label, needles in _SOURCE_RULES:
        if any(n in low for n in needles):
            return label
    return None


# Directories never scanned. "PixelRAG Albums" holds user-created folder exports,
# which are copies of photos already in the library — indexing them would create
# near-duplicates of every exported photo on the next sync.
SKIP_DIR_NAMES = {"PixelRAG Albums"}


def iter_image_files(root_dir: Path) -> Iterable[Path]:
    """
    Recursively yield all image files under root_dir, skipping hidden folders
    (starting with .) and the album-export directory.
    """
    try:
        items = root_dir.iterdir()
    except OSError:
        return

    for path in items:
        try:
            if path.name.startswith(".") or path.name in SKIP_DIR_NAMES:
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
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        cur = conn.cursor()

        inserted = 0

        for img_path in iter_image_files(root):
            abs_path = str(img_path.resolve())
            source = derive_source(abs_path)

            # Use INSERT OR IGNORE to avoid crashing on duplicates
            cur.execute(
                """
                INSERT OR IGNORE INTO photos(path, has_faces, source)
                VALUES (?, NULL, ?)
                """,
                (abs_path, source),
            )

            # rowcount will be 1 only if a new row was inserted
            if cur.rowcount == 1:
                inserted += 1
            elif source is not None:
                # Backfill source on rows indexed before this facet existed
                cur.execute(
                    "UPDATE photos SET source = ? WHERE path = ? AND source IS NULL",
                    (source, abs_path),
                )

        conn.commit()
    finally:
        conn.close()

    return inserted
