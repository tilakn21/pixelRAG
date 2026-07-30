import os
import subprocess
import shutil
import hashlib
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["config"])


@router.post("/config/browse")
async def browse_folder():
    """Open a native macOS folder selection dialog and return the path."""
    # This AppleScript opens a folder picker and returns the POSIX path.
    # We use osascript to ensure it runs as a native macOS dialog.
    script = 'POSIX path of (choose folder with prompt "Select PixelRAG Library Folder")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True
        )
        path = proc.stdout.strip()
        return {"path": path}
    except subprocess.CalledProcessError:
        # User likely cancelled the dialog
        return {"path": None}


class LibrarySetupRequest(BaseModel):
    path: str

@router.get("/config/libraries")
async def list_known_libraries():
    """List all previously added library folders."""
    from pixel_rag_server.services.library_manager import get_known_libraries
    return {"libraries": get_known_libraries()}


@router.post("/config/library")
async def set_library_path(request: Request, body: LibrarySetupRequest):
    """Set the library path, write to .env, and initialize the database."""
    from pixel_rag_server.services.library_manager import add_known_library
    
    lib_path = str(Path(body.path).resolve())
    
    if not Path(lib_path).is_dir():
        raise HTTPException(status_code=400, detail={"error": "Directory does not exist."})
        
    env_path = Path(__file__).resolve().parent.parent / ".env"
    
    # Write to .env
    env_content = ""
    if env_path.exists():
        env_content = env_path.read_text()
        lines = env_content.splitlines()
        lines = [line for line in lines if not line.startswith("LIBRARY_PATH=")]
        env_content = "\n".join(lines) + "\n"
    
    env_content += f'LIBRARY_PATH="{lib_path}"\n'
    env_path.write_text(env_content)
    
    # Add to persistent tracker
    add_known_library(lib_path)
    
    # Update app state
    request.app.state.library_path = lib_path
    db_path = str(Path(lib_path) / ".pixelrag" / "db.sqlite")
    request.app.state.db_path = db_path
    
    # Initialize/Migrate DB
    from pixel_rag_core.db.init_db import init_db, get_db_connection
    from pixel_rag_core.db.db_migrations import scrub_cross_library_contamination
    
    init_db(db_path)
    
    # ── One-Time Scrubbing for Newly Added Library ──
    # Ensure any ghosts from other libraries are purged from this DB file if it's shared.
    conn = get_db_connection(db_path)
    try:
        scrub_cross_library_contamination(conn, lib_path)
    finally:
        conn.close()
        
    request.app.state.setup_required = False
    
    return {"status": "ok", "library_path": lib_path, "db_path": db_path}


@router.delete("/config/library")
async def delete_library(request: Request, path: str, wipe_data: bool = False):
    """Remove a library from the system and optionally wipe its metadata."""
    from pixel_rag_server.services.library_manager import remove_known_library
    from pixel_rag_server.routers.sync import _sync_state
    from pixel_rag_server.process_guard import SHUTDOWN_EVENT
    import asyncio
    
    abs_path = str(Path(path).resolve())
    
    # Check for active sync and securely drain it
    if wipe_data and _sync_state.status == "running":
        print("[PixelRAG] WIPE_AI requested during active sync! Initiating shutdown drain...")
        SHUTDOWN_EVENT.set()
        
        # Wait up to 30 seconds for the pipeline to flush WAL and close connections
        for _ in range(30):
            if _sync_state.status != "running":
                print("[PixelRAG] Active sync cleanly exited. Proceeding with WIPE_AI.")
                break
            await asyncio.sleep(1.0)
        else:
            print("[PixelRAG] ⚠️ Timeout waiting for pipeline drain! WIPE_AI forcing folder deletion anyway, may hit locked files.")
            
    if wipe_data:
        try:
            db_file = Path(path) / ".pixelrag" / "db.sqlite"
            # Although the DB file will be deleted, we must first scrub it 
            # if it's currently the target of our shared database logic.
            # And we MUST scrub any people/photos scoped to this root 
            # from wherever they live.
            
            # 1. Clear Scoped Database Records
            conn = sqlite3.connect(db_file, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            
            print(f"[PixelRAG] WIPE_AI: Deep scrubbing scoped data for {abs_path}...")
            
            # Count for logging
            n_people = conn.execute("SELECT COUNT(*) FROM people WHERE folder_root = ?", (abs_path,)).fetchone()[0]
            n_photos = conn.execute("SELECT COUNT(*) FROM photos WHERE path LIKE ?", (abs_path + '%',)).fetchone()[0]
            
            conn.execute("DELETE FROM people WHERE folder_root = ?", (abs_path,))
            conn.execute("DELETE FROM photos WHERE path LIKE ?", (abs_path + '%',))
            # faces and face_embeddings will cascade if DB schema is correct, 
            # but we'll be safe:
            conn.execute("DELETE FROM faces WHERE photo_id NOT IN (SELECT id FROM photos)")
            
            conn.execute("PRAGMA wal_checkpoint(FULL);")
            conn.close()
            
            # 2. Delete Scoped Thumbnail Cache
            lib_hash = hashlib.md5(abs_path.encode()).hexdigest()[:12]
            thumb_cache = Path.home() / ".pixelrag" / "thumbs" / lib_hash
            if thumb_cache.exists():
                print(f"[PixelRAG] WIPE_AI: Deleting thumbnail cache for {abs_path}...")
                shutil.rmtree(thumb_cache)
                
            print(f"WIPE_AI: Deleted {n_people} people and {n_photos} photos for root: {abs_path}")

        except Exception as e:
            print(f"[PixelRAG] WIPE_AI scrub failed: {e}")
            
    # Remove from tracker and disk
    remove_known_library(abs_path, wipe_data=wipe_data)
    
    # If the active library was deleted, clear state
    current_active = getattr(request.app.state, "library_path", None)
    if current_active and str(Path(current_active).resolve()) == abs_path:
        request.app.state.library_path = None
        request.app.state.db_path = None
        request.app.state.setup_required = True
        
    return {"status": "ok", "deleted": abs_path}
