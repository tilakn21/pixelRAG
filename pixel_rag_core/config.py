# pixelrag_core/config.py

from pathlib import Path

# Root of the project (pixelrag/). Adjust if you keep things differently.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Data directory (on laptop)
DATA_DIR = PROJECT_ROOT / "data"

# Work directory where db + embeddings live
WORK_DIR = DATA_DIR / "work"

# Path to SQLite DB (for dev)
DB_PATH = WORK_DIR / "db.sqlite"
