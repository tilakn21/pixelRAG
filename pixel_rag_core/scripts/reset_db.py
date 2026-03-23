import sqlite3
import argparse
from pathlib import Path
from pixel_rag_core.config import DB_PATH

def reset_db(db_path: Path, full_reset: bool):
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        if full_reset:
            print("Performing FULL reset (deleting all photos, faces, embeddings, and clusters)...")
            # Use execute instead of executescript for individual deletes so we can catch missing tables
            tables = ['face_embeddings', 'faces', 'photos', 'clusters', 'people', 'indexed_files', 'geocache']
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table}")
                except sqlite3.OperationalError:
                    pass
        else:
            print("Performing CLUSTER reset (unassigning all faces, deleting clusters and people)...")
            cur.executescript("""
                UPDATE faces SET cluster_id = NULL, person_id = NULL;
                DELETE FROM clusters;
                DELETE FROM people;
            """)
        
        conn.commit()
        # VACUUM must be run outside of a transaction
        conn.isolation_level = None
        cur.execute("VACUUM")
        conn.isolation_level = "" # restore default
        print("Database reset successfully.")
    except sqlite3.OperationalError as e:
        print(f"Error: {e}")
        print("Make sure no other scripts (like index_faces_script) are currently running and locking the database.")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset PixelRAG Database.")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to DB")
    parser.add_argument("--full", action="store_true", help="Wipe all photos/faces/embeddings too, not just clusters.")
    args = parser.parse_args()
    
    reset_db(Path(args.db), args.full)
