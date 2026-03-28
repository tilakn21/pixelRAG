# pixel_rag_server/routers/config.py
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["config"])

class LibrarySetupRequest(BaseModel):
    path: str

@router.post("/config/library")
async def set_library_path(request: Request, body: LibrarySetupRequest):
    """Set the library path, write to .env, and initialize the database."""
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
    
    # Update app state
    request.app.state.library_path = lib_path
    db_path = str(Path(lib_path) / ".pixelrag" / "db.sqlite")
    request.app.state.db_path = db_path
    
    # Initialize DB
    from pixel_rag_core.db.init_db import init_db
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    if not Path(db_path).exists():
        init_db(db_path)
        
    request.app.state.setup_required = False
    
    return {"status": "ok", "library_path": lib_path, "db_path": db_path}
