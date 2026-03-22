# pixel_rag_core/library/library_manager.py
"""
Manages the list of known libraries (indexed folders) across sessions.
Libraries are stored in ~/.pixelrag/libraries.json
Each library's DB lives inside <folder>/.pixelrag/db.sqlite
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Global config dir: ~/.pixelrag/
PIXELRAG_CONFIG_DIR = Path.home() / ".pixelrag"
LIBRARIES_FILE = PIXELRAG_CONFIG_DIR / "libraries.json"

# Per-library hidden dir name
LIBRARY_DIR_NAME = ".pixelrag"
LIBRARY_DB_NAME = "db.sqlite"


def _load_libraries() -> List[dict]:
    if not LIBRARIES_FILE.exists():
        return []
    try:
        return json.loads(LIBRARIES_FILE.read_text())
    except Exception:
        return []


def _save_libraries(libraries: List[dict]):
    PIXELRAG_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARIES_FILE.write_text(json.dumps(libraries, indent=2))


def list_libraries() -> List[dict]:
    """Returns all known library records. Each has: path, name, is_indexed."""
    libs = _load_libraries()
    # Re-validate: check if the folder still exists and DB is present
    valid = []
    for lib in libs:
        p = Path(lib["path"])
        lib["exists"] = p.exists()
        lib["is_indexed"] = get_library_db(lib["path"]).exists()
        valid.append(lib)
    return valid


def add_library(folder_path: str) -> dict:
    """Add a new library. Returns the library record."""
    folder = Path(folder_path).resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Path does not exist or is not a directory: {folder}")

    libs = _load_libraries()
    # Check for duplicates
    for lib in libs:
        if Path(lib["path"]) == folder:
            return lib

    record = {
        "path": str(folder),
        "name": folder.name,
        "is_indexed": get_library_db(str(folder)).exists(),
    }
    libs.append(record)
    _save_libraries(libs)
    return record


def remove_library(folder_path: str):
    """Remove a library from the registry (does NOT delete files)."""
    folder = Path(folder_path).resolve()
    libs = _load_libraries()
    libs = [l for l in libs if Path(l["path"]).resolve() != folder]
    _save_libraries(libs)


def get_library_db(folder_path: str) -> Path:
    """Returns the path to the DB for a given library folder."""
    return Path(folder_path).resolve() / LIBRARY_DIR_NAME / LIBRARY_DB_NAME


def ensure_library_db(folder_path: str) -> Path:
    """Initializes the DB for a library if it doesn't exist. Returns DB path."""
    from pixel_rag_core.db.init_db import init_db

    db_path = get_library_db(folder_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        init_db(str(db_path))
    return db_path
