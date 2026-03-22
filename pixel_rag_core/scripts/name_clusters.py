import sqlite3
import argparse
import sys
from pathlib import Path
import cv2
import matplotlib.pyplot as plt
import numpy as np

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pixel_rag_core.config import DB_PATH

def get_unnamed_clusters(conn):
    cur = conn.cursor()
    cur.execute('''
        SELECT c.id, COUNT(f.id) as face_count
        FROM clusters c
        JOIN faces f ON c.id = f.cluster_id
        WHERE c.person_id IS NULL
        GROUP BY c.id
        ORDER BY face_count DESC
    ''')
    return cur.fetchall()

def get_random_face_for_cluster(conn, cluster_id):
    cur = conn.cursor()
    cur.execute('''
        SELECT f.id, p.path, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
        WHERE f.cluster_id = ?
        ORDER BY RANDOM()
        LIMIT 1
    ''', (cluster_id,))
    return cur.fetchone()

def ensure_person_exists(conn, name: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM people WHERE name = ? COLLATE NOCASE", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    cur.execute("INSERT INTO people (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid

def update_cluster_person(conn, cluster_id: int, person_id: int):
    cur = conn.cursor()
    cur.execute("UPDATE clusters SET person_id = ? WHERE id = ?", (person_id, cluster_id))
    cur.execute("UPDATE faces SET person_id = ? WHERE cluster_id = ?", (person_id, cluster_id))
    conn.commit()

def show_face_crop(img_path: str, bbox_bytes: bytes) -> bool:
    try:
        # Load image via cv2.imdecode for robustness
        import os
        if not os.path.exists(img_path):
            print(f"File does not exist: {img_path}")
            return False
            
        with open(img_path, 'rb') as f:
            chunk = f.read()
        chunk_arr = np.frombuffer(chunk, dtype=np.uint8)
        img = cv2.imdecode(chunk_arr, cv2.IMREAD_COLOR)
        
        if img is None:
            print(f"Could not load image: {img_path}")
            return False
            
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Decode bbox
        bbox = np.frombuffer(bbox_bytes, dtype=np.float64)
        if len(bbox) >= 4:
            x1, y1, x2, y2 = map(int, bbox[:4])
            
            # Add some padding to the crop
            h, w = img_rgb.shape[:2]
            pw = int((x2 - x1) * 0.5)
            ph = int((y2 - y1) * 0.5)
            
            crop_x1 = max(0, x1 - pw)
            crop_y1 = max(0, y1 - ph)
            crop_x2 = min(w, x2 + pw)
            crop_y2 = min(h, y2 + ph)
            
            face_crop = img_rgb[crop_y1:crop_y2, crop_x1:crop_x2]
            
            plt.figure(figsize=(4, 4))
            plt.imshow(face_crop)
            plt.title("Who is this?")
            plt.axis("off")
            plt.show(block=False)
            plt.pause(0.1) # brief pause to render
            return True
        else:
            print(f"Invalid bbox in db for {img_path}")
            return False
    except Exception as e:
        print(f"Error displaying face: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Interactively name discovered face clusters.")
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    
    clusters = get_unnamed_clusters(conn)
    if not clusters:
        print("No unnamed clusters found! All faces might be named or no clustered faces exist.")
        return
        
    print(f"Found {len(clusters)} unnamed clusters.")
    print("For each cluster, a random face will be shown.")
    print("Type the person's name, press Enter to skip, or type 'quit' to exit.\\n")
    
    for cluster_id, face_count in clusters:
        print(f"--- Cluster {cluster_id} ({face_count} faces) ---")
        face_record = get_random_face_for_cluster(conn, cluster_id)
        
        if not face_record:
            print(f"Could not find a valid photo for cluster {cluster_id}.")
            continue
            
        face_id, photo_path, x1, y1, x2, y2 = face_record
        bbox = np.array([x1, y1, x2, y2], dtype=np.float64)
        
        # Close any previous plot
        plt.close('all')
        
        success = show_face_crop(photo_path, bbox.tobytes())
        
        if not success:
            print(f"Skipping cluster {cluster_id} due to rendering error.\\n")
            continue
            
        name = input("Enter name (or 'quit' / Enter to skip): ").strip()
        
        if name.lower() == 'quit':
            print("Exiting...")
            break
            
        if name:
            person_id = ensure_person_exists(conn, name)
            update_cluster_person(conn, cluster_id, person_id)
            print(f"-> Assigned {face_count} faces to '{name}'!\\n")
        else:
            print("-> Skipped.\\n")
            
    plt.close('all')
    conn.close()
    print("Done naming clusters.")

if __name__ == "__main__":
    main()
