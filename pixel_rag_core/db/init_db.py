# pixelrag_core/db/init_db.py

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS photos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL UNIQUE,
    created_at   TEXT,
    latitude     REAL,
    longitude    REAL,
    camera_make  TEXT,
    camera_model TEXT,
    has_faces    INTEGER DEFAULT 0,
    city         TEXT,
    state        TEXT,
    country      TEXT,
    category     TEXT,
    description  TEXT,
    phash                TEXT,
    scene_category       TEXT,
    scene_confidence     REAL,
    scene_tags           TEXT,
    scene_low_confidence INTEGER DEFAULT 0,
    file_hash            TEXT
);

CREATE TABLE IF NOT EXISTS faces (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id       INTEGER NOT NULL,
    bbox_x1        REAL NOT NULL,
    bbox_y1        REAL NOT NULL,
    bbox_x2        REAL NOT NULL,
    bbox_y2        REAL NOT NULL,
    embedding_idx  INTEGER,
    cluster_id     INTEGER,
    person_id      INTEGER,
    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS people (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL UNIQUE,
    centroid_embedding  BLOB,
    purity_score        REAL,
    confirmed           INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clusters (
    id         INTEGER PRIMARY KEY,
    person_id  INTEGER,
    label      TEXT,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    face_id   INTEGER PRIMARY KEY,
    dim       INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    FOREIGN KEY(face_id) REFERENCES faces(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS geocache (
    lat_rounded  REAL NOT NULL,
    lon_rounded  REAL NOT NULL,
    city         TEXT,
    state        TEXT,
    country      TEXT,
    resolved_at  INTEGER,
    PRIMARY KEY (lat_rounded, lon_rounded)
);

"""

# Indexes to create (safe with IF NOT EXISTS)
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_photos_scene_category ON photos(scene_category)",
    "CREATE INDEX IF NOT EXISTS idx_photos_phash ON photos(phash)",
    "CREATE INDEX IF NOT EXISTS idx_faces_person_id ON faces(person_id)",
    "CREATE INDEX IF NOT EXISTS idx_faces_cluster_id ON faces(cluster_id)",
]


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str, default=None):
    """Add a column to a table if it doesn't already exist."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cur.fetchall()]
    if column not in cols:
        default_clause = f" DEFAULT {default}" if default is not None else ""
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")


def run_migrations(conn: sqlite3.Connection):
    """
    Run all additive migrations. Safe to call on existing databases —
    each operation checks before modifying.
    """
    # ── photos table additions ────────────────────────────────────────
    _safe_add_column(conn, "photos", "phash", "TEXT")
    _safe_add_column(conn, "photos", "scene_category", "TEXT")
    _safe_add_column(conn, "photos", "scene_confidence", "REAL")
    _safe_add_column(conn, "photos", "scene_tags", "TEXT")
    _safe_add_column(conn, "photos", "scene_low_confidence", "INTEGER", default=0)
    _safe_add_column(conn, "photos", "file_hash", "TEXT")

    # ── people table additions ────────────────────────────────────────
    _safe_add_column(conn, "people", "centroid_embedding", "BLOB")
    _safe_add_column(conn, "people", "purity_score", "REAL")
    _safe_add_column(conn, "people", "confirmed", "INTEGER", default=0)

    # ── geocache table ────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocache (
            lat_rounded  REAL NOT NULL,
            lon_rounded  REAL NOT NULL,
            city         TEXT,
            state        TEXT,
            country      TEXT,
            resolved_at  INTEGER,
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
    """)

    # ── indexes ───────────────────────────────────────────────────────
    for idx_sql in INDEXES:
        conn.execute(idx_sql)

    # Enable WAL mode for concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()


def init_db(db_path: str):
    """
    Create the SQLite database and all required tables.
    Also runs migrations to ensure all columns exist on upgrade.

    :param db_path: Path to the SQLite file (it will be created if not exists)
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    # Run migrations for existing DBs that may be missing new columns
    run_migrations(conn)

    conn.commit()
    conn.close()
    print(f"[PixelRAG] Initialized DB at: {db_path}")


def get_db_connection(db_path: str, timeout: int = 30) -> sqlite3.Connection:
    """Helper to get a connection with WAL mode and increased timeout."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
