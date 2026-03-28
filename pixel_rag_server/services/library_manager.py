import json
import os
import hashlib
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

def get_path_hash(path: str) -> str:
    """Returns a short stable hash of the library path for cache busting."""
    if not path:
        return "none"
    return hashlib.md5(path.encode()).hexdigest()[:8]
