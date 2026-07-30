# pixel_rag_core/db/db_migrations.py
import sqlite3

def scrub_cross_library_contamination(conn, active_library_path: str):
    """
    Removes all people, faces, and photos from the DB that do not belong
    to the currently active library. Run once at startup after migration.
    
    This is the definitive 'One-Time Scrub' requested to clean up 
    existing legacy contamination.
    """
    if not active_library_path:
        return

    # Ensure trailing slash for LIKE matching
    if not active_library_path.endswith('/'):
        active_library_path += '/'

    print(f"[PixelRAG] Startup: Scrubbing contamination for root: {active_library_path}...")

    # Step 0: Delete FACE EMBEDDINGS for photos NOT in the active library
    conn.execute("""
        DELETE FROM face_embeddings 
        WHERE face_id IN (
            SELECT f.id FROM faces f
            JOIN photos ph ON f.photo_id = ph.id
            WHERE ph.path NOT LIKE ?
        )
    """, (active_library_path + '%',))

    # Step 1: Delete FACES for photos NOT in the active library
    conn.execute("""
        DELETE FROM faces 
        WHERE photo_id IN (
            SELECT id FROM photos 
            WHERE path NOT LIKE ?
        )
    """, (active_library_path + '%',))

    # Step 2: Clear CLUSTERS (legacy/temporary mapping)
    conn.execute("DELETE FROM clusters")

    # Step 3: Delete PEOPLE who no longer have any faces (orphans or foreign)
    cur = conn.execute("""
        DELETE FROM people 
        WHERE id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)
    """)
    n_people_purged = cur.rowcount

    # Step 4: Delete PHOTOS NOT in the active library
    cur = conn.execute("""
        DELETE FROM photos 
        WHERE path NOT LIKE ?
    """, (active_library_path + '%',))
    n_photos_purged = cur.rowcount
    
    # Step 5: Assign folder_root to any remaining people rows still NULL
    cur = conn.execute("""
        UPDATE people SET folder_root = ?
        WHERE folder_root IS NULL
    """, (active_library_path.rstrip('/'),))
    n_assigned = cur.rowcount
    
    conn.commit()
    print(f"[PixelRAG] Cleanup: Purged {n_people_purged} identities and {n_photos_purged} foreign photos. Scoped {n_assigned} identities.")
