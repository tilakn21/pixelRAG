# pixel_rag_server/main.py
"""FastAPI entry point for PixelRAG backend."""

import os
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
    from pixel_rag_core.db.init_db import init_db

    if not SETUP_REQUIRED:
        # Initialize or upgrade the database schema
        init_db(DB_PATH)
        print(f"[PixelRAG Server] Library: {LIBRARY_PATH}")
        print(f"[PixelRAG Server] Database: {DB_PATH}")

    # Store shared state
    app.state.library_path = LIBRARY_PATH
    app.state.db_path = DB_PATH
    app.state.setup_required = SETUP_REQUIRED

    yield  # Application runs here

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
    allow_origins=["*"],  # Allow any origin for local network phone access
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
async def health_check(request: Request):
    """Return server status, photo count, and person count."""
    from pixel_rag_server.models.schemas import HealthResponse
    from fastapi import Request

    status = "ok"
    photo_count = 0
    person_count = 0
    lib_hash = ""
    known_libs = []

    if getattr(request.app.state, "setup_required", False) or not request.app.state.db_path:
        status = "setup_required"
    else:
        from pixel_rag_server.services.library_manager import (
            get_known_libraries,
            get_path_hash,
        )

        lib_path = request.app.state.library_path
        lib_hash = get_path_hash(lib_path)
        known_libs = get_known_libraries()
        try:
            conn = sqlite3.connect(request.app.state.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            photo_count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
            person_count = conn.execute(
                "SELECT COUNT(*) FROM people WHERE confirmed = 1"
            ).fetchone()[0]
            conn.close()
        except Exception:
            pass

    return HealthResponse(
        status=status,
        photo_count=photo_count,
        person_count=person_count,
        library_path=lib_path,
        known_libraries=known_libs,
        lib_hash=lib_hash,
    )
