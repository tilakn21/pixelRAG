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
    """Run the full indexing pipeline in a background thread and track progress."""
    global _sync_state

    # Step progress mapping for better UX
    step_ranges = {
        "scan": 15,
        "metadata": 30,
        "geocode": 40,
        "faces": 70,
        "scenes": 85,
        "cluster": 95,
        "done": 100,
    }

    try:
        from pixel_rag_core.library.pipeline import run_full_pipeline

        # Use the generator to track each stage of the AI pipeline
        for step_name, msg in run_full_pipeline(library_path, db_path):
            with _sync_lock:
                # Add to log history for frontend "console"
                _sync_state.logs.append(msg)
                
                # Update current status text
                _sync_state.current_file = msg
                
                # Update progress percentage
                if step_name in step_ranges:
                    _sync_state.progress = step_ranges[step_name]
                    
                if step_name == "done":
                    _sync_state.status = "complete"

    except Exception as e:
        with _sync_lock:
            _sync_state.status = "error"
            _sync_state.error_message = str(e)
            _sync_state.logs.append(f"❌ CRITICAL ERROR: {e}")
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
