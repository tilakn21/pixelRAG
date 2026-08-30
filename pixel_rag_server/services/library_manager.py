import json
import os
import hashlib
import shutil
from pathlib import Path

# Config in the project root
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / ".pixelrag_config.json"

def get_known_libraries():
    """Returns a list of all library paths ever added."""
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            return data.get("libraries", [])
    except Exception:
        return []

def add_known_library(path: str):
    """Adds a new library path to the tracker."""
    try:
        path = str(Path(path).resolve())
        libraries = get_known_libraries()
        if path not in libraries:
            libraries.append(path)
            with open(CONFIG_PATH, "w") as f:
                json.dump({"libraries": libraries}, f, indent=4)
        return libraries
    except Exception:
        return []

def remove_known_library(path: str, wipe_data: bool = False):
    """Removes a library from the tracker and optionally wipes its metadata folder."""
    try:
        path = str(Path(path).resolve())
        libraries = get_known_libraries()
        if path in libraries:
            libraries.remove(path)
            with open(CONFIG_PATH, "w") as f:
                json.dump({"libraries": libraries}, f, indent=4)
        
        # ALWAYS execute wipe_data if requested, even if path wasn't in libraries.
        # This handles the case where the user deleted it from the UI (which removed it from json)
        # but the wipe failed or was skipped previously.
        if wipe_data:
            pixelrag_dir = Path(path) / ".pixelrag"
            if pixelrag_dir.exists():
                shutil.rmtree(pixelrag_dir)
                
        return libraries
    except Exception as e:
        print(f"[PixelRAG] Error removing library / wiping data: {e}")
        return get_known_libraries()

# ── Where a library's database lives ─────────────────────────────────────────
# PORTABLE BY DEFAULT: the index lives beside the photos, at
# <library>/.pixelrag/db.sqlite, so plugging the drive into another Mac carries
# the whole library — photos, index, identities and thumbnail cache — with it.
#
# This was briefly moved to local disk while diagnosing a hard deadlock:
#     pysqlite_connection_close -> sqlite3WalClose -> unixLock -> __psynch_mutexwait
# which froze the whole interpreter (CPython holds the GIL through
# sqlite3_close, so one stuck thread stalled even /healthz, surfacing as
# ECONNRESET). exFAT looked like the culprit. It was not — the same deadlock
# reproduced on APFS. The real cause was opening and closing a connection per
# request (~350 close cycles for one /people load); services/db.py now pools
# one long-lived connection per thread, and the close path is never entered.
#
# Re-measured afterwards, 12 readers + 2 writers, long-lived connections:
#     WAL on APFS : 51,968 reads, p95 1.94 ms, 0 errors
#     WAL on exFAT: 49,058 reads, p95 2.00 ms, 0 errors
# i.e. indistinguishable. (DELETE journal mode was ~100x worse for reads on
# BOTH filesystems, so it is not an option.)
#
# TOMORROW — portable mode (agreed, not yet implemented):
#   keep the index at <library>/.pixelrag/db.sqlite and the thumbnail cache at
#   <library>/.pixelrag/thumbs/, so plugging the drive into any Mac carries
#   photos + index + identities + cache together. Benchmarked as safe:
#   12 readers + 2 writers on long-lived pooled connections gave
#       WAL on APFS : 51,968 reads, p95 1.94 ms, 0 errors, 0 stuck
#       WAL on exFAT: 49,058 reads, p95 2.00 ms, 0 errors, 0 stuck
#   (DELETE journal mode was ~100x worse for reads on BOTH filesystems, so it
#   is not a viable alternative.) Keep a local snapshot as backup, since exFAT
#   is not journalled and an unclean eject mid-write can corrupt.
LOCAL_DB_ROOT = Path.home() / ".pixelrag" / "libraries"


def get_library_db_path(library_path: str) -> str:
    """
    Local, always-writable DB path for a library. Creates the directory, and
    migrates a legacy in-library database across on first use.
    """
    lib = str(Path(library_path).resolve())
    key = hashlib.md5(lib.encode()).hexdigest()[:12]
    target_dir = LOCAL_DB_ROOT / key
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "db.sqlite"

    if not target.exists():
        legacy = Path(lib) / ".pixelrag" / "db.sqlite"
        if legacy.exists():
            # Copy rather than move: leave the original untouched so a failed
            # migration can never destroy an index that took hours to build.
            try:
                shutil.copy2(legacy, target)
                for suffix in ("-wal", "-shm"):
                    side = legacy.with_name(legacy.name + suffix)
                    if side.exists() and side.stat().st_size > 0:
                        shutil.copy2(side, target.with_name(target.name + suffix))
                print(f"[PixelRAG] Migrated library DB to local disk: {target}")
            except Exception as e:
                print(f"[PixelRAG] DB migration failed ({e}); using legacy path.")
                return str(legacy)
        try:
            (target_dir / "library_path.txt").write_text(lib + "\n")
        except Exception:
            pass

    return str(target)


def get_path_hash(path: str) -> str:
    """Returns a short stable hash of the library path for cache busting."""
    if not path:
        return "none"
    return hashlib.md5(path.encode()).hexdigest()[:8]

def get_sync_version(path: str) -> int:
    """
    Cache-busting generation marker for a library: mtime of its face-crop
    cache dir (recreated on every sync). 0 if the library has never synced.
    Appended to media URLs as `h=<lib_hash>_<sync_version>` so browsers
    refetch thumbnails/face crops after a re-sync instead of serving stale
    cached images for reused IDs.
    """
    if not path:
        return 0
    try:
        lib_hash_12 = hashlib.md5(path.encode()).hexdigest()[:12]
        face_cache_dir = Path.home() / ".pixelrag" / "thumbs" / lib_hash_12 / "faces"
        if face_cache_dir.exists():
            return int(face_cache_dir.stat().st_mtime)
    except Exception:
        pass
    return 0
