import io
import sqlite3
from typing import Dict, Any

import cv2
import numpy as np
from PIL import Image, ImageOps

# Lazy-loaded InsightFace model for face search (separate from indexer)
_search_app = None

def _get_search_app():
    global _search_app
    if _search_app is None:
        from insightface.app import FaceAnalysis
        _search_app = FaceAnalysis(
            name='buffalo_l',
            providers=['CPUExecutionProvider']
        )
        _search_app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=0.5)
    return _search_app

def find_person_by_image(db_path: str, folder_root: str, image_bytes: bytes) -> Dict[str, Any]:
    """
    Extracts face from uploaded image bytes, compares it against the local gallery
    scoped to the current library, and returns the best matching person_id.
    """
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        return {"error": f"Invalid image format: {e}"}

    app = _get_search_app()
    faces = app.get(img)
    
    if not faces:
        return {"error": "No faces detected in the uploaded image."}
        
    # Pick the largest face in the image to search
    largest_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
    emb = largest_face.normed_embedding
    if emb is None:
        return {"error": "Could not extract deep embedding from the face."}
        
    emb_norm = emb / (np.linalg.norm(emb) + 1e-10)

    # ── Load Identity Gallery from DB (Scoped to Library) ──
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    
    gallery_rows = conn.execute(
        """
        SELECT f.person_id, fe.embedding, p.name
        FROM faces f
        JOIN face_embeddings fe ON f.id = fe.face_id
        JOIN people p ON f.person_id = p.id
        WHERE f.is_representative = 1 AND p.confirmed = 1 AND p.folder_root = ?
        """,
        (folder_root,)
    ).fetchall()
    conn.close()
    
    if not gallery_rows:
        return {"error": "No confirmed people in your PixelRAG library to search against."}
        
    max_sim = 0.0
    best_person_id = None
    best_person_name = None
    
    # ── 1:N Gallery Matching ──
    for pid, emb_blob, pname in gallery_rows:
        ref_arr = np.frombuffer(emb_blob, dtype=np.float32)
        ref_norm = ref_arr / (np.linalg.norm(ref_arr) + 1e-10)
        sim = float(np.dot(ref_norm, emb_norm))
        
        if sim > max_sim:
            max_sim = sim
            best_person_id = pid
            best_person_name = pname
            
    # ArcFace cosine similarity threshold: 0.50 is generous but reliable for manual search.
    # Allows slightly more tolerance for different lighting/angles in uploaded images.
    if max_sim > 0.50:
        return {
            "match": True,
            "person_id": best_person_id,
            "name": best_person_name,
            "similarity": max_sim
        }
    else:
        return {
            "match": False,
            "error": "No known person in your library securely matched the uploaded face."
        }
