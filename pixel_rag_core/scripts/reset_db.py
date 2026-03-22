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
            cur.executescript("""
                DELETE FROM face_embeddings;
                DELETE FROM faces;
                DELETE FROM photos;
                DELETE FROM clusters;
                DELETE FROM people;
            """)
        else:
            print("Performing CLUSTER reset (unassigning all faces, deleting clusters and people)...")
            cur.executescript("""
                UPDATE faces SET cluster_id = NULL, person_id = NULL;
                DELETE FROM clusters;
                DELETE FROM people;
            """)
        
        cur.execute("VACUUM")
        conn.commit()
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
