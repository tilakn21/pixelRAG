from dataclasses import dataclass
from pathlib import Path
from fastapi import Request, HTTPException
from pixel_rag_server.services.library_manager import (
    get_known_libraries,
    get_library_db_path,
    get_path_hash,
)

@dataclass
class LibraryContext:
    library_path: str
    db_path: str
    lib_hash: str

import threading

# Cache initialized databases to prevent concurrent init_db deadlocks
_initialized_dbs = set()
_db_init_lock = threading.Lock()

def get_db_path(request: Request) -> LibraryContext:
    """
    Dependency to get the current library's full context (DB and folder paths).
    Supports multitenancy via 'h' (hash) query parameter.
    """
    # 1. High Priority: Explicit hash in query string
    lib_hash_raw = request.query_params.get("h")
    if lib_hash_raw:
        # Strip cache-busting suffix (e.g. hash_timestamp)
        lib_hash = lib_hash_raw.split("_")[0]
        from pixel_rag_core.db.init_db import init_db
        known_libs = get_known_libraries()
        for lib_path in known_libs:
            if get_path_hash(lib_path) == lib_hash:
                db_path = get_library_db_path(lib_path)
                
                # Ensure the database is initialized before any router uses it (only once per process)
                if db_path not in _initialized_dbs:
                    with _db_init_lock:
                        if db_path not in _initialized_dbs:
                            init_db(db_path)
                            _initialized_dbs.add(db_path)
                    
                return LibraryContext(
                    library_path=lib_path,
                    db_path=db_path,
                    lib_hash=lib_hash
                )

    # 2. Low Priority: Fallback to global active library
    lib_path = getattr(request.app.state, "library_path", None)
    db_path = getattr(request.app.state, "db_path", None)
    
    if not db_path or not lib_path:
        raise HTTPException(
            status_code=400, 
            detail={"error": "No active library selected. Please mount a folder first."}
        )
        
    return LibraryContext(
        library_path=lib_path,
        db_path=db_path,
        lib_hash=get_path_hash(lib_path)
    )
