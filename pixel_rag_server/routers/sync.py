# pixel_rag_server/routers/sync.py
"""Sync router — triggers the indexing pipeline as a background task.

Hardened:
  - _sync_lock removed from sync_callback to prevent deadlock with ProcessPoolExecutor
  - Daemon thread replaced with managed thread + SHUTDOWN_EVENT
  - SQLite queries moved outside lock scope
  - try/finally guarantees terminal state on thread exit
"""

import sqlite3
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Depends
from pixel_rag_server.models.schemas import SyncStatus
from pixel_rag_server.dependencies import get_db_path, LibraryContext
from pixel_rag_server.process_guard import (
    SHUTDOWN_EVENT,
    set_sync_thread,
)

router = APIRouter(tags=["sync"])

# In-memory sync state (does not survive server restarts)
_sync_state = SyncStatus()
_sync_lock = threading.Lock()

# Reference to the running sync thread for lifecycle management
_active_thread: threading.Thread | None = None


def _run_sync_pipeline(library_path: str, db_path: str):
    """Run the full indexing pipeline in a background thread and track progress."""
    global _sync_state

    def sync_callback(step_name, sub_prog, step_idx, total_steps, msg):
        """Callback for granular updates within a step.
        
        CRITICAL FIX (Issue 4): No lock is acquired here. This callback
        is invoked from within run_full_pipeline, which calls
        executor.submit() and future.result(). Holding a lock across
        Future resolution is a deadlock vector.
        
        CPython's GIL makes simple attribute writes thread-safe.
        """
        _sync_state.step_name = step_name.upper()
        _sync_state.step_index = step_idx
        _sync_state.total_steps = total_steps
        _sync_state.sub_progress = sub_prog
        _sync_state.sub_message = msg

        # Map granular step + sub_progress to overall progress 0-100
        base_prog = ((step_idx - 1) / total_steps) * 100
        step_contribution = (sub_prog / 100) * (100 / total_steps)
        _sync_state.progress = min(int(base_prog + step_contribution), 99)


    try:
        from pixel_rag_core.library.pipeline import run_full_pipeline

        # Use the generator for high-level step transitions
        for step_name, sub_prog, step_idx, total_steps, msg in run_full_pipeline(
            library_path, db_path, callback=sync_callback,
            shutdown_event=SHUTDOWN_EVENT,
        ):
            # Update state without holding lock (atomic attr writes under GIL)
            _sync_state.step_name = step_name.upper()
            _sync_state.step_index = step_idx
            _sync_state.total_steps = total_steps
            _sync_state.sub_progress = sub_prog
            _sync_state.sub_message = msg
            _sync_state.logs.append(msg)

            # Update overall progress
            base_prog = ((step_idx - 1) / total_steps) * 100
            step_contribution = (sub_prog / 100) * (100 / total_steps)
            _sync_state.progress = int(base_prog + step_contribution)



            # Update photo counts — OUTSIDE any lock
            try:
                conn = sqlite3.connect(db_path, timeout=10)
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    _sync_state.photos_total = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
                    _sync_state.photos_processed = conn.execute(
                        "SELECT COUNT(*) FROM photos WHERE has_faces IS NOT NULL"
                    ).fetchone()[0]
                finally:
                    conn.close()
            except Exception:
                pass

            if step_name == "done":
                with _sync_lock:
                    _sync_state.status = "complete"
                    _sync_state.progress = 100

            if step_name == "shutdown":
                with _sync_lock:
                    _sync_state.status = "complete"
                    _sync_state.progress = _sync_state.progress
                    _sync_state.logs.append("⚠️ Sync interrupted by shutdown — progress saved.")

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        with _sync_lock:
            _sync_state.status = "error"
            _sync_state.error_message = f"{e}\n{tb_str}"
            _sync_state.logs.append(f"❌ CRITICAL ERROR: {e}")
            _sync_state.current_file = None

    finally:
        # GUARANTEE: status is always set to a terminal state on thread exit
        with _sync_lock:
            if _sync_state.status == "running":
                _sync_state.status = "complete"
        set_sync_thread(None)


@router.post("/sync/start", status_code=202)
async def start_sync(request: Request, lib_ctx: LibraryContext = Depends(get_db_path)):
    """Trigger the indexing pipeline as a background task."""
    global _sync_state, _active_thread
 
    if _sync_state.status == "running":
        raise HTTPException(
            status_code=409,
            detail={"error": "A sync is already running. Wait for it to complete."},
        )
 
    library_path = lib_ctx.library_path
    db_path = lib_ctx.db_path
    if not library_path:
         raise HTTPException(status_code=400, detail={"error": "Library path not configured."})

    # Clear shutdown event so next sync doesn't instantly die
    SHUTDOWN_EVENT.clear()
    

    # Reset state
    _sync_state = SyncStatus(
        status="running",
        progress=0,
        step_index=1,
        total_steps=7,
        step_name="PRUNE"
    )

    # Start as a NON-daemon thread — managed by SHUTDOWN_EVENT + signal handlers
    thread = threading.Thread(
        target=_run_sync_pipeline,
        args=(library_path, db_path),
        daemon=False,
        name="sync-pipeline",
    )
    _active_thread = thread
    set_sync_thread(thread)
    thread.start()

    return {"message": "Sync started", "status": "running"}


@router.get("/sync/status", response_model=SyncStatus)
async def get_sync_status():
    """Return the current sync status."""
    return _sync_state
