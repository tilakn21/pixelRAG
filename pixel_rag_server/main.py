# pixel_rag_server/main.py
"""FastAPI entry point for PixelRAG backend."""

import os

# ALWAYS set these before importing cv2, numpy, or onnxruntime to prevent thread deadlocks
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Ensure pixel_rag_core is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(Path(__file__).resolve().parent / ".env")

LIBRARY_PATH = os.environ.get("LIBRARY_PATH")
SETUP_REQUIRED = False

if not LIBRARY_PATH or not Path(LIBRARY_PATH).resolve().is_dir():
    SETUP_REQUIRED = True
    LIBRARY_PATH = None
    DB_PATH = None
else:
    LIBRARY_PATH = str(Path(LIBRARY_PATH).resolve())
    DB_PATH = str(Path(LIBRARY_PATH) / ".pixelrag" / "db.sqlite")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and heavy AI models on startup."""
    # FIRST: Activate all process-level hardening before anything else
    from pixel_rag_server.process_guard import init_process_guard
    init_process_guard()

    from pixel_rag_core.db.init_db import init_db, get_db_connection
    from pixel_rag_core.db.db_migrations import scrub_cross_library_contamination
    import shutil

    if not SETUP_REQUIRED:
        # 1. Initialize or upgrade the database schema
        init_db(DB_PATH)
        
        # 2. RUN ONE-TIME SCRUBBING (Fix 5)
        # Purge any legacy 'ghost' identities from before the folder_root fix.
        conn = get_db_connection(DB_PATH)
        try:
            scrub_cross_library_contamination(conn, LIBRARY_PATH)
        finally:
            conn.close()

        # 3. ONE-TIME THUMBNAIL CACHE MIGRATION (Fix 6)
        # Clear legacy unscoped thumbnails (~/.pixelrag/thumbs/*.webp)
        # Gated by a sentinel file to prevent re-runs.
        config_dir = Path.home() / ".pixelrag"
        sentinel = config_dir / ".cache_migrated"
        
        if not sentinel.exists():
            legacy_thumbs = config_dir / "thumbs"
            if legacy_thumbs.exists():
                # We only delete the UNSCOPED files in the top level of thumbs/
                # Scoped subdirectories (hashed) will be preserved (though they shouldn't exist yet)
                count = 0
                for f in legacy_thumbs.glob("*.webp"):
                    if f.is_file():
                        f.unlink()
                        count += 1
                print(f"[PixelRAG] Startup: Cleared {count} stale unscoped thumbnails from legacy cache.")
            
            # Mark as migrated
            config_dir.mkdir(parents=True, exist_ok=True)
            sentinel.touch()

    # Store shared state
    app.state.library_path = LIBRARY_PATH
    app.state.db_path = DB_PATH
    app.state.setup_required = SETUP_REQUIRED

    print(f"[PixelRAG Server] Startup complete. Ready for requests.")

    yield

    print("[PixelRAG Server] Shutting down.")


app = FastAPI(
    title="PixelRAG API",
    description="Local-first photo intelligence backend",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow Next.js dev server and local network access
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex="http://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from pixel_rag_server.routers import identities, media, photos, search, sync, config

app.include_router(photos.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(identities.router, prefix="/api")
app.include_router(config.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health_check(request: Request):
    """Return server status, photo count, and person count."""
    from pixel_rag_server.models.schemas import HealthResponse
    from fastapi import Request

    status = "ok"
    photo_count = 0
    person_count = 0
    lib_path = ""
    lib_hash = ""
    known_libs = []

    from pixel_rag_server.services.library_manager import (
        get_known_libraries,
        get_path_hash,
    )
    from pathlib import Path
    import os
    known_libs = get_known_libraries()

    sync_version = 0

    if getattr(request.app.state, "setup_required", False) or not request.app.state.db_path:
        status = "setup_required"
    else:
        lib_path = request.app.state.library_path
        lib_hash = get_path_hash(lib_path)
        try:
            conn = sqlite3.connect(request.app.state.db_path, timeout=10)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                photo_count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
                person_count = conn.execute(
                    "SELECT COUNT(*) FROM people WHERE confirmed = 1"
                ).fetchone()[0]
            finally:
                conn.close()
        except Exception:
            pass
            
        try:
            import hashlib
            lib_hash_12 = hashlib.md5(lib_path.encode()).hexdigest()[:12]
            face_cache_dir = Path.home() / ".pixelrag" / "thumbs" / lib_hash_12 / "faces"
            if face_cache_dir.exists():
                sync_version = int(face_cache_dir.stat().st_mtime)
        except Exception:
            pass

    return HealthResponse(
        status=status,
        photo_count=photo_count,
        person_count=person_count,
        library_path=lib_path,
        known_libraries=known_libs,
        lib_hash=lib_hash,
        sync_version=sync_version,
    )


@app.get("/healthz", tags=["system"])
async def healthz():
    """Liveness/readiness probe. Returns 200 OK if the web server is up."""
    return {"status": "ok"}
