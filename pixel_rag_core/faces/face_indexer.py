# pixel_rag_core/faces/face_indexer.py
#
# Parallel face indexing using ThreadPoolExecutor.
# InsightFace's ONNX runtime releases the GIL during inference,
# so threads genuinely run concurrently on CPU. DB writes stay
# in the main thread to keep SQLite safe.

import sqlite3
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis

warnings.filterwarnings("ignore", category=UserWarning, module="face_recognition_models")
warnings.filterwarnings("ignore", category=FutureWarning, module="insightface.utils.face_align")

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# Single global InsightFace app — safe to call from multiple threads
# (ONNX runtime is thread-safe for read-only inference)
_app = FaceAnalysis(name='buffalo_s', providers=['CPUExecutionProvider'])
_app.prepare(ctx_id=-1, det_size=(640, 640))


FaceResult = List[Tuple[float, float, float, float, np.ndarray]]


def _process_photo_faces(photo_path: Path) -> FaceResult:
    """
    Detect and embed all faces in a single image.
    Returns list of (x1, y1, x2, y2, embedding).
    This function is called from worker threads.
    """
    try:
        import os
        from PIL import Image, ImageOps

        img_path_str = str(photo_path)
        if not os.path.exists(img_path_str):
            return []

        try:
            pil_img = Image.open(img_path_str)
            pil_img = ImageOps.exif_transpose(pil_img)   # correct rotation
            if pil_img.mode != 'RGB':
                pil_img = pil_img.convert('RGB')
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as read_err:
            print(f"[PixelRAG] Could not parse image: {photo_path} - {read_err}")
            return []

        faces = _app.get(img)
        results: FaceResult = []
        for face in faces:
            bbox = face.bbox.astype(float)
            emb = face.normed_embedding
            if emb is not None:
                results.append((bbox[0], bbox[1], bbox[2], bbox[3], np.asarray(emb)))
        return results

    except Exception as e:
        print(f"[PixelRAG] Error processing faces for {photo_path}: {e}")
        return []


def index_faces_for_photos(
    db_path: str,
    limit: Optional[int] = None,
    num_workers: int = 4,
) -> int:
    """
    For photos where has_faces = 0 or NULL, detect and embed faces in parallel,
    then write results to the DB single-threaded.

    :param num_workers: Number of parallel threads for InsightFace inference.
    :return: Total number of face records inserted.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)

    query = "SELECT id, path FROM photos WHERE has_faces = 0 OR has_faces IS NULL"
    if limit is not None:
        query += f" LIMIT {limit}"
    photos = conn.execute(query).fetchall()
    conn.close()

    if not photos:
        print("[PixelRAG] No unindexed photos found.")
        return 0

    print(f"[PixelRAG] Indexing faces for {len(photos)} photos with {num_workers} workers...")

    # ── Parallel inference phase ──────────────────────────────────────────
    # Map: photo_id → face_results
    future_to_photo = {}
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        for photo_id, path in photos:
            future = executor.submit(_process_photo_faces, Path(path))
            future_to_photo[future] = (photo_id, path)

        results: dict[int, FaceResult] = {}
        completed = 0
        for future in as_completed(future_to_photo):
            photo_id, path = future_to_photo[future]
            completed += 1
            if completed % 50 == 0:
                print(f"[PixelRAG]   Analyzed {completed}/{len(photos)} photos...")
            try:
                results[photo_id] = future.result()
            except Exception as e:
                print(f"[PixelRAG] Worker error for {path}: {e}")
                results[photo_id] = []

    # ── Single-threaded DB write phase ────────────────────────────────────
    conn = sqlite3.connect(db_path)
    total_faces = 0

    for photo_id, path in photos:
        faces = results.get(photo_id, [])

        if not faces:
            conn.execute("UPDATE photos SET has_faces = 0 WHERE id = ?", (photo_id,))
            continue

        for bbox_x1, bbox_y1, bbox_x2, bbox_y2, emb in faces:
            conn.execute(
                "INSERT INTO faces (photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2) "
                "VALUES (?, ?, ?, ?, ?)",
                (photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2),
            )
            face_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            emb_bytes = emb.astype(np.float64).tobytes()
            conn.execute(
                "INSERT INTO face_embeddings (face_id, dim, embedding) VALUES (?, ?, ?)",
                (face_id, emb.shape[0], emb_bytes),
            )
            total_faces += 1

        conn.execute("UPDATE photos SET has_faces = 1 WHERE id = ?", (photo_id,))
        conn.commit()

    conn.close()
    print(f"[PixelRAG] Done. Total faces indexed: {total_faces}")
    return total_faces
