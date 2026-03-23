# pixel_rag_core/faces/face_indexer.py
#
# Parallel face indexing using ThreadPoolExecutor.
# InsightFace's ONNX runtime releases the GIL during inference,
# so threads genuinely run concurrently on CPU. DB writes stay
# in the main thread to keep SQLite safe.
#
# Upgraded: buffalo_l model, quality gates (det_score, blur, pose), pHash dedup.

import math
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

# ── Quality gate thresholds ──────────────────────────────────────────────────
MIN_DET_SCORE = 0.75       # Minimum detection confidence
MIN_LAPLACIAN_VAR = 80.0   # Minimum sharpness (Laplacian variance)
MAX_ROLL_DEGREES = 35.0    # Maximum head tilt
PHASH_HAMMING_THRESHOLD = 2  # Max Hamming distance for near-duplicate detection

# Single global InsightFace app — safe to call from multiple threads
# (ONNX runtime is thread-safe for read-only inference)
# UPGRADED: buffalo_l (ResNet50) for significantly better accuracy
_app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
_app.prepare(ctx_id=-1, det_size=(640, 640))


FaceResult = List[Tuple[float, float, float, float, np.ndarray]]


def _compute_laplacian_variance(img_bgr: np.ndarray, bbox) -> float:
    """Compute sharpness of a face crop using Laplacian variance."""
    h, w = img_bgr.shape[:2]
    x1 = max(0, int(bbox[0]))
    y1 = max(0, int(bbox[1]))
    x2 = min(w, int(bbox[2]))
    y2 = min(h, int(bbox[3]))

    if x2 <= x1 or y2 <= y1:
        return 0.0

    crop = img_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _compute_roll_angle(kps: np.ndarray) -> float:
    """
    Compute face roll angle from 5-point keypoints.
    kps[0] = left eye, kps[1] = right eye.
    Returns absolute roll angle in degrees.
    """
    if kps is None or len(kps) < 2:
        return 0.0
    left_eye = kps[0]
    right_eye = kps[1]
    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    angle = math.degrees(math.atan2(dy, dx))
    return abs(angle)


def _compute_phash(image_path: Path) -> Optional[str]:
    """Compute perceptual hash of an image using imagehash library."""
    try:
        import imagehash
        from PIL import Image, ImageOps
        pil_img = Image.open(str(image_path))
        pil_img = ImageOps.exif_transpose(pil_img)
        h = imagehash.phash(pil_img)
        return str(h)
    except Exception:
        return None


def _check_phash_duplicate(conn: sqlite3.Connection, phash_str: str, current_photo_id: int) -> bool:
    """Check if a near-duplicate image exists in the DB by pHash Hamming distance."""
    if not phash_str:
        return False
    try:
        import imagehash
        new_hash = imagehash.hex_to_hash(phash_str)
        rows = conn.execute("SELECT id, phash FROM photos WHERE phash IS NOT NULL AND id != ?", (current_photo_id,)).fetchall()
        for _, existing_phash in rows:
            if existing_phash:
                try:
                    existing_hash = imagehash.hex_to_hash(existing_phash)
                    if new_hash - existing_hash <= PHASH_HAMMING_THRESHOLD:
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def _process_photo_faces(photo_path: Path) -> FaceResult:
    """
    Detect and embed all faces in a single image.
    Applies quality gates: det_score, blur, pose.
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
            # ── Quality Gate 1: Detection Score ──
            det_score = getattr(face, 'det_score', 1.0)
            if det_score < MIN_DET_SCORE:
                continue

            bbox = face.bbox.astype(float)

            # ── Quality Gate 2: Blur Filter (Laplacian Variance) ──
            lap_var = _compute_laplacian_variance(img, bbox)
            if lap_var < MIN_LAPLACIAN_VAR:
                continue

            # ── Quality Gate 3: Pose Quality (Roll Angle) ──
            kps = getattr(face, 'kps', None)
            roll = _compute_roll_angle(kps)
            if roll > MAX_ROLL_DEGREES:
                continue

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

    Includes pHash deduplication: near-duplicate photos are skipped.

    :param num_workers: Number of parallel threads for InsightFace inference.
    :return: Total number of face records inserted.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")

    query = "SELECT id, path FROM photos WHERE has_faces = 0 OR has_faces IS NULL"
    if limit is not None:
        query += f" LIMIT {limit}"
    photos = conn.execute(query).fetchall()
    conn.close()

    if not photos:
        print("[PixelRAG] No unindexed photos found.")
        return 0

    print(f"[PixelRAG] Indexing faces for {len(photos)} photos with {num_workers} workers...")

    # ── pHash deduplication phase ────────────────────────────────────────
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    photos_to_process = []
    duplicates_skipped = 0

    for photo_id, path in photos:
        photo_path = Path(path)
        phash_str = _compute_phash(photo_path)

        # Store phash regardless
        if phash_str:
            conn.execute("UPDATE photos SET phash = ? WHERE id = ?", (phash_str, photo_id))

        # Check for near-duplicates
        if phash_str and _check_phash_duplicate(conn, phash_str, photo_id):
            # Mark as processed but with no faces (skip indexing)
            conn.execute("UPDATE photos SET has_faces = 0 WHERE id = ?", (photo_id,))
            duplicates_skipped += 1
            print(f"[PixelRAG] Skipping near-duplicate: {photo_path.name}")
        else:
            photos_to_process.append((photo_id, path))

    conn.commit()
    conn.close()

    if duplicates_skipped > 0:
        print(f"[PixelRAG] Skipped {duplicates_skipped} near-duplicate photos.")

    if not photos_to_process:
        print("[PixelRAG] No unique photos to process after deduplication.")
        return 0

    # ── Parallel inference phase ──────────────────────────────────────────
    # Map: photo_id → face_results
    future_to_photo = {}
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        for photo_id, path in photos_to_process:
            future = executor.submit(_process_photo_faces, Path(path))
            future_to_photo[future] = (photo_id, path)

        results: dict[int, FaceResult] = {}
        completed = 0
        for future in as_completed(future_to_photo):
            photo_id, path = future_to_photo[future]
            completed += 1
            if completed % 50 == 0:
                print(f"[PixelRAG]   Analyzed {completed}/{len(photos_to_process)} photos...")
            try:
                results[photo_id] = future.result()
            except Exception as e:
                print(f"[PixelRAG] Worker error for {path}: {e}")
                results[photo_id] = []

    # ── Single-threaded DB write phase ────────────────────────────────────
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    total_faces = 0

    for photo_id, path in photos_to_process:
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

        # Tag photo with scene_category = "people" since valid faces were found
        conn.execute(
            "UPDATE photos SET has_faces = 1, scene_category = 'people', scene_confidence = 1.0 WHERE id = ?",
            (photo_id,),
        )
        conn.commit()

    conn.close()
    print(f"[PixelRAG] Done. Total faces indexed: {total_faces}")
    return total_faces
