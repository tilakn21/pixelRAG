import sqlite3
import os
from pathlib import Path
import sys

def sanitize_db(db_path: str, library_path: str):
    db_path = str(Path(db_path).resolve())
    library_path = str(Path(library_path).resolve())
    
    print(f"--- Purging Contamination from {db_path} ---")
    print(f"--- Target Library Root: {library_path} ---")
    
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        
        # 1. Identify and Delete "Foreign" Photos (Paths from other folders)
        # We use a LIKE check to ensure only files within the library_path remain.
        # Note: We use || '/' to ensure we match the directory boundary.
        safe_prefix = library_path if library_path.endswith('/') else library_path + '/'
        
        cur = conn.execute("SELECT COUNT(*) FROM photos WHERE path NOT LIKE ?", (safe_prefix + "%",))
        foreign_count = cur.fetchone()[0]
        
        if foreign_count > 0:
            print(f"Found {foreign_count} foreign photo records. Deleting...")
            conn.execute("DELETE FROM photos WHERE path NOT LIKE ?", (safe_prefix + "%",))
        else:
            print("No foreign photo records found.")
            
        # 2. Reset All Processing Status
        print("Resetting all photo processing statuses (has_faces = NULL)...")
        conn.execute("UPDATE photos SET has_faces = NULL")
        
        # 3. Wipe Identities and Clusters
        print("Wiping corrupted identities and clusters...")
        conn.execute("DELETE FROM faces")
        conn.execute("DELETE FROM clusters")
        conn.execute("DELETE FROM people")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('faces', 'clusters', 'people')")
        
        conn.commit()
        print("--- Sanitization Complete! ---")
        print("You can now trigger a 'Sync' in the UI for a 100% clean, high-precision indexing.")
        
    except Exception as e:
        print(f"Critical Error during sanitization: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python wipe_and_resync.py <db_path> <library_path>")
        sys.exit(1)
        
    sanitize_db(sys.argv[1], sys.argv[2])
