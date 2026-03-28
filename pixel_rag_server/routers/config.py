# pixel_rag_server/routers/config.py
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["config"])

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
    from pixel_rag_core.db.init_db import init_db
    init_db(db_path)
        
    request.app.state.setup_required = False
    
    return {"status": "ok", "library_path": lib_path, "db_path": db_path}
