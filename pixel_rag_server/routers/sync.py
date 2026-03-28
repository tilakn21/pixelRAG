# pixel_rag_server/routers/sync.py
"""Sync router — triggers the indexing pipeline as a background task."""

import threading
import time

from fastapi import APIRouter, HTTPException, Request

from pixel_rag_server.models.schemas import SyncStatus

router = APIRouter(tags=["sync"])

# In-memory sync state (does not survive server restarts)
_sync_state = SyncStatus()
_sync_lock = threading.Lock()


def _run_sync_pipeline(library_path: str, db_path: str):
    """Run the full indexing pipeline in a background thread."""
    global _sync_state

    try:
        with _sync_lock:
            _sync_state.status = "running"
            _sync_state.progress = 0
            _sync_state.error_message = None

        from pixel_rag_core.library.pipeline import run_full_pipeline

        # Run the pipeline — this is the heavy operation
        _sync_state.progress = 10
        _sync_state.current_file = "Scanning folder..."

        run_full_pipeline(library_path, db_path)

        with _sync_lock:
            _sync_state.status = "complete"
            _sync_state.progress = 100
            _sync_state.current_file = None

    except Exception as e:
        with _sync_lock:
            _sync_state.status = "error"
            _sync_state.error_message = str(e)
            _sync_state.current_file = None


@router.post("/sync/start", status_code=202)
async def start_sync(request: Request):
    """Trigger the indexing pipeline as a background task."""
    global _sync_state

    if _sync_state.status == "running":
        raise HTTPException(
            status_code=409,
            detail={"error": "A sync is already running. Wait for it to complete."},
        )

    library_path = request.app.state.library_path
    db_path = request.app.state.db_path

    # Reset state
    _sync_state = SyncStatus(status="running", progress=0)

    # Start in a background thread
    thread = threading.Thread(
        target=_run_sync_pipeline,
        args=(library_path, db_path),
        daemon=True,
    )
    thread.start()

    return {"message": "Sync started", "status": "running"}


@router.get("/sync/status", response_model=SyncStatus)
async def get_sync_status():
    """Return the current sync status."""
    return _sync_state
