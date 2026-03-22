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
    description  TEXT
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
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
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

"""

def init_db(db_path: str):
    """
    Create the SQLite database and all required tables.

    :param db_path: Path to the SQLite file (it will be created if not exists)
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[PixelRAG] Initialized DB at: {db_path}")
