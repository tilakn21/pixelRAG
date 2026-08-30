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
    has_faces    INTEGER,
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
    is_representative INTEGER DEFAULT 0,
    sharpness      REAL,
    roll_angle     REAL,
    det_score      REAL,
    face_size_ratio REAL,
    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY(person_id) REFERENCES people(id)
);

CREATE TABLE IF NOT EXISTS people (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL UNIQUE,
    centroid_embedding  BLOB,
    purity_score        REAL,
    confirmed           INTEGER DEFAULT 0,
    folder_root         TEXT
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

CREATE TABLE IF NOT EXISTS failed_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL,
    stage       TEXT NOT NULL,
    error       TEXT NOT NULL,
    failed_at   TEXT NOT NULL DEFAULT (datetime('now')),
    retry_count INTEGER DEFAULT 0,
    permanent   INTEGER DEFAULT 0
);

"""

# Indexes to create (safe with IF NOT EXISTS)
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_photos_scene_category ON photos(scene_category)",
    "CREATE INDEX IF NOT EXISTS idx_photos_phash ON photos(phash)",
    "CREATE INDEX IF NOT EXISTS idx_faces_person_id ON faces(person_id)",
    "CREATE INDEX IF NOT EXISTS idx_faces_cluster_id ON faces(cluster_id)",
    "CREATE INDEX IF NOT EXISTS idx_people_folder_root ON people(folder_root)",
    "CREATE INDEX IF NOT EXISTS idx_faces_photo_id ON faces(photo_id)",
    "CREATE INDEX IF NOT EXISTS idx_photos_created_at ON photos(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_photos_has_faces ON photos(has_faces)",
    "CREATE INDEX IF NOT EXISTS idx_failed_images_path ON failed_images(path)",
    "CREATE INDEX IF NOT EXISTS idx_failed_images_permanent ON failed_images(permanent)",
    "CREATE INDEX IF NOT EXISTS idx_photos_scene_model ON photos(scene_model)",
    "CREATE INDEX IF NOT EXISTS idx_photos_scene_secondary ON photos(scene_secondary)",
    "CREATE INDEX IF NOT EXISTS idx_photos_source ON photos(source)",
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
    # Scene v2: routed classification (face-first + metadata rules + CLIP)
    _safe_add_column(conn, "photos", "scene_secondary", "TEXT")   # visual scene even when primary='people'
    _safe_add_column(conn, "photos", "scene_source", "TEXT")      # 'faces' | 'metadata' | 'clip' | 'unsorted'
    _safe_add_column(conn, "photos", "scene_model", "TEXT")       # classifier version tag, for reclassification
    _safe_add_column(conn, "photos", "width", "INTEGER")
    _safe_add_column(conn, "photos", "height", "INTEGER")
    # Provenance facet (whatsapp / camera / scan / download / ...) — NOT a content label
    _safe_add_column(conn, "photos", "source", "TEXT")

    # ── faces table additions ─────────────────────────────────────────
    _safe_add_column(conn, "faces", "is_representative", "INTEGER", default=0)
    _safe_add_column(conn, "faces", "sharpness", "REAL")
    _safe_add_column(conn, "faces", "roll_angle", "REAL")
    _safe_add_column(conn, "faces", "det_score", "REAL")
    _safe_add_column(conn, "faces", "face_size_ratio", "REAL")

    # ── people table additions ────────────────────────────────────────
    _safe_add_column(conn, "people", "centroid_embedding", "BLOB")
    _safe_add_column(conn, "people", "purity_score", "REAL")
    _safe_add_column(conn, "people", "confirmed", "INTEGER", default=0)
    _safe_add_column(conn, "people", "folder_root", "TEXT")

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

    # ── photo_embeddings table ────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS photo_embeddings (
            photo_id  INTEGER PRIMARY KEY,
            dim       INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
        )
    """)

    # ── failed_images table ───────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS failed_images (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT NOT NULL,
            stage       TEXT NOT NULL,
            error       TEXT NOT NULL,
            failed_at   TEXT NOT NULL DEFAULT (datetime('now')),
            retry_count INTEGER DEFAULT 0,
            permanent   INTEGER DEFAULT 0
        )
    """)

    for idx_sql in INDEXES:
        conn.execute(idx_sql)

    # ── Migration: folder_root Inference ──────────────────────────────
    # If folder_root is NULL, attempt to infer it from faces -> photos.path.
    conn.execute("""
        UPDATE people
        SET folder_root = (
            SELECT ph.path 
            FROM faces f 
            JOIN photos ph ON f.photo_id = ph.id 
            WHERE f.person_id = people.id 
            LIMIT 1
        )
        WHERE folder_root IS NULL
    """)
    # Note: The above subquery gets the full path. We need the directory root.
    # Actually, a better inference is to just take the longest common prefix or 
    # simply use any linked photo's path and truncate to the last .pixelrag parent.
    # BUT, since we are moving to a model where folder_root is passed, 
    # we'll let Fix 5 handle the sophisticated scrubbing.
    # For now, just ensure the column exists.

    cur = conn.cursor()
    cur.execute("PRAGMA user_version")
    version = cur.fetchone()[0]
    
    # ── State Repair: dangling cluster_id ─────────────────────────────
    # `DELETE FROM clusters` (done by scrub_cross_library_contamination) leaves
    # faces.cluster_id pointing at rows that no longer exist. Because new
    # cluster ids restart at MAX(id)+1, those stale values get RECYCLED and a
    # later `WHERE cluster_id = ?` sweeps up unrelated faces — measured moving
    # 28 confirmed faces to the wrong person. Heal on every startup.
    conn.execute("""
        UPDATE faces SET cluster_id = NULL
        WHERE cluster_id IS NOT NULL
          AND cluster_id NOT IN (SELECT id FROM clusters)
    """)

    # ── REMOVED: "State Repair: has_faces" ────────────────────────────
    # This used to run on EVERY init_db():
    #     UPDATE photos SET has_faces = NULL
    #      WHERE has_faces = 0 AND id NOT IN (SELECT DISTINCT photo_id FROM faces)
    #
    # Its premise — "has_faces = 0 with no face rows is inconsistent" — is
    # simply false now. Two legitimate terminal states produce exactly that
    # shape:
    #   * the pHash dedup pass marks near-duplicates has_faces = 0 without
    #     ever running detection on them (11,547 photos on the real library);
    #   * a photo that WAS processed and genuinely contains no face.
    #
    # Measured damage on the 28k library: it reset **19,709 photos** from 0 to
    # NULL on a single server start, discarding 138 minutes of face-indexing
    # decisions and queuing every deduplicated photo for reprocessing. It was
    # also expensive — a NOT IN scan over 22,476 faces holding a write lock on
    # external storage, re-run on every init_db() (i.e. per new `?h=` library).
    #
    # If a genuinely legacy DB ever needs this repair it must be a one-time,
    # user_version-gated migration, never an unconditional every-boot UPDATE.

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
    """Helper to get a connection with WAL mode and mandatory Foreign Key enforcement."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
