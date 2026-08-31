# pixel_rag_core/faces/face_indexer.py
#
# High-performance face indexing using ProcessPoolExecutor.
#
# Architecture:
#   - 2 worker processes, each with its own InsightFace model (~400-500MB each)
#   - Workers auto-recycle every 50 tasks (max_tasks_per_child)
#     to prevent ONNX runtime resource exhaustion
#   - CPUExecutionProvider only (CoreML deadlocks in multi-process contexts)
#   - Parent-side timeout (_PARENT_TIMEOUT=90s) — signal.alarm removed (unreliable on macOS spawn)
#   - Pre-scaling to PIXELRAG_MAX_INFERENCE_PX (default 1280px) to minimize memory footprint
#   - Proper zombie reaping via os.waitpid after SIGKILL
#
# Upgraded: buffalo_l model, quality gates (det_score, blur, pose), pHash dedup (exact match).

import gc
import math
import os
import signal
import sqlite3
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from multiprocessing import get_context
from pathlib import Path
from typing import List, Optional, Tuple, Callable

from pixel_rag_core.db.init_db import get_db_connection

import cv2
import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="face_recognition_models")
warnings.filterwarnings("ignore", category=FutureWarning, module="insightface.utils.face_align")

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

# ── Quality gate thresholds ──────────────────────────────────────────────────
# Tuned for high recall on consumer camera photos (5MP+).
# InsightFace det_thresh=0.5 pre-filters junk; these gates catch edge cases.
MIN_DET_SCORE = 0.50       # Lowered from 0.75 — valid faces score 0.35-0.70 on group shots
MIN_LAPLACIAN_VAR = 10.0   # Lowered from 25.0 — softer DSLR/mobile photos need slack
MAX_ROLL_DEGREES = 180.0   # Allow all rotations (landscape/rotated faces)
MIN_FACE_PIXELS = 40       # Lowered from 80 — group shot faces can be 40-60px after scaling

# Concurrency settings
_NUM_WORKERS = 2           # Number of parallel worker processes (M4 Air: ~1GB total for 2 workers)
_TASKS_PER_CHILD = 50      # Recycle workers every N images to flush RAM back to OS
_INFERENCE_TIMEOUT = 60    # Per-image timeout in seconds (parent-side only)

# CPU provider — CoreML deadlocks when multiple workers compile models simultaneously
_PROVIDERS = ['CPUExecutionProvider']

# ── Auto-tag gate ────────────────────────────────────────────────────────────
# Auto-tag writes person_id at INSERT time, before clustering runs. Confirmed
# faces are then excluded from clustering input, the scrubber only ejects below
# 0.45, and confirmed centroids are frozen — so a wrong assignment here is never
# revisited by any later stage. It is the least recoverable of the four
# assignment rules, which is why it gets a margin test on top of the bar.
#
# Measured on the real library (scratch/measure_impostor_margins.py, N=7):
#   genuine vs own centroid : min 0.436, p5 0.619, median 0.806
#   impostor (best OTHER)   : median 0.177, p99 0.310, MAX 0.335
#   top-1 identification errors: 0/599
# So at N=7 every bar has huge headroom. But impostor_max grows with identity
# count, fitted as ~0.128*ln(n)+0.086, which projects the 0.70 bar being
# breached near ~122 identities — inside the 100-200 range this library expects.
#
# DELTA could NOT be derived from genuine/impostor separation: with zero
# impostor top-1 wins there is no impostor margin distribution to separate
# from. It is instead chosen to be free now and still workable later —
# 0.05 is far below the N=7 correct-margin p1 of 0.369, and below the ~0.079
# genuine margin projected at N=150. Re-measure once the 28k library has
# confirmed identities; see CONTEXT.md §15.
AUTOTAG_THRESHOLD = float(os.environ.get("PIXELRAG_AUTOTAG_THRESHOLD", "0.70"))
AUTOTAG_MARGIN = float(os.environ.get("PIXELRAG_AUTOTAG_MARGIN", "0.05"))

FaceResult = List[Tuple[float, float, float, float, float, float, float, float, np.ndarray]]

# ── Worker process globals (initialized once per worker via _worker_init) ────
_worker_app = None


def _worker_init():
    """
    Called once when each worker process starts.
    Loads the InsightFace model into process-local memory.
    """
    import os
    import sys
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    global _worker_app
    from insightface.app import FaceAnalysis
    _worker_app = FaceAnalysis(name='buffalo_l', providers=_PROVIDERS)
    # det_size=640 catches 3x more medium faces than 1280 (validated empirically).
    # det_thresh=0.5 is InsightFace's default; set explicitly for clarity.
    _worker_app.prepare(ctx_id=-1, det_size=(640, 640), det_thresh=0.5)


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
    """Compute face roll angle from 5-point keypoints."""
    if kps is None or len(kps) < 2:
        return 0.0
    left_eye = kps[0]
    right_eye = kps[1]
    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    return abs(math.degrees(math.atan2(dy, dx)))


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
    """Check for exact pHash duplicate. Fuzzy matching removed (O(N×M) bottleneck)."""
    if not phash_str:
        return False
    row = conn.execute(
        "SELECT id FROM photos WHERE phash = ? AND id != ?",
        (phash_str, current_photo_id)
    ).fetchone()
    return row is not None


def _log_failed_image(db_path: str, path: str, stage: str, error: str, infra: bool = False):
    """
    Log a processing failure to failed_images. Never raises.

    `infra=True` marks a failure of OUR machinery rather than of the image:
    a broken process pool, or the parent-side 90 s watchdog firing. Those are
    recorded for visibility but do NOT increment retry_count and can never set
    permanent=1.

    Why the distinction matters: retry_count >= 3 sets permanent=1, and
    permanently-failed paths are skipped on every future run. Charging a
    perfectly good photo for a memory wobble therefore drops it from the face
    index forever. That risk is not hypothetical on this run — we are on Python
    3.10, where ProcessPoolExecutor's max_tasks_per_child is inert, so worker
    RSS only grows across 28k images and pool restarts are expected.
    """
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")

        if infra:
            # Visibility only: fixed retry_count = -1 sentinel, never permanent.
            conn.execute(
                "INSERT INTO failed_images (path, stage, error, failed_at, retry_count, permanent) "
                "VALUES (?, ?, ?, datetime('now'), -1, 0)",
                (path, f"{stage}_INFRA", str(error)[:500]),
            )
            conn.commit()
            conn.close()
            return

        # Per-image failure: count it against the image.
        prev = conn.execute(
            "SELECT retry_count FROM failed_images WHERE path = ? AND stage = ? "
            "AND retry_count >= 0 ORDER BY id DESC LIMIT 1",
            (path, stage)
        ).fetchone()
        retry_count = (prev[0] + 1) if prev else 0

        conn.execute(
            "INSERT INTO failed_images (path, stage, error, failed_at, retry_count) VALUES (?, ?, ?, datetime('now'), ?)",
            (path, stage, str(error)[:500], retry_count)
        )
        # Mark permanent after 3 genuine per-image failures
        if retry_count >= 3:
            conn.execute(
                "UPDATE failed_images SET permanent = 1 WHERE path = ? AND stage = ? AND retry_count >= 0",
                (path, stage)
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Logging must never crash the pipeline


def _worker_process_photo(photo_path_str: str):
    """
    Process a single photo in a worker process.
    Parent-side timeout (_PARENT_TIMEOUT) is the safety net for hung C++ code.
    signal.alarm removed — unreliable on macOS spawn-mode processes.

    Returns a list of (x1, y1, x2, y2, det_score, lap_var, roll, face_size_ratio, emb_bytes) tuples,
    or "TIMEOUT"/"ERROR:..." strings on failure.
    """
    try:
        import os
        from PIL import Image, ImageOps

        if not os.path.exists(photo_path_str):
            return []

        pil_img = Image.open(photo_path_str)
        pil_img.load()
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')

        # Pre-scale to configurable max dimension (default 1280px)
        orig_w, orig_h = pil_img.size
        scale_factor = 1.0
        MAX_DIM = int(os.environ.get("PIXELRAG_MAX_INFERENCE_PX", "1920"))
        if max(orig_w, orig_h) > MAX_DIM:
            scale_factor = max(orig_w, orig_h) / float(MAX_DIM)
            try:
                resampling = Image.Resampling.LANCZOS
            except AttributeError:
                resampling = Image.LANCZOS
            pil_img.thumbnail((MAX_DIM, MAX_DIM), resampling)

        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        del pil_img

        faces = _worker_app.get(img)

        face_data = []
        for face in faces:
            det_score = getattr(face, 'det_score', 1.0)
            if det_score < MIN_DET_SCORE:
                continue

            scaled_bbox = face.bbox.astype(float)
            bbox = scaled_bbox * scale_factor

            face_w = bbox[2] - bbox[0]
            face_h = bbox[3] - bbox[1]
            if face_w < MIN_FACE_PIXELS or face_h < MIN_FACE_PIXELS:
                continue

            lap_var = _compute_laplacian_variance(img, scaled_bbox)
            if lap_var < MIN_LAPLACIAN_VAR:
                continue

            kps = getattr(face, 'kps', None)
            roll = _compute_roll_angle(kps)
            if roll > MAX_ROLL_DEGREES:
                continue

            emb = face.normed_embedding
            if emb is not None:
                face_size_ratio = float((face_w * face_h) / (orig_w * orig_h)) if (orig_w > 0 and orig_h > 0) else 0.0
                face_data.append((
                    float(bbox[0]), float(bbox[1]),
                    float(bbox[2]), float(bbox[3]),
                    float(det_score), float(lap_var), float(roll), float(face_size_ratio),
                    emb.astype(np.float32).tobytes()
                ))

        return face_data

    except Exception as e:
        return f"ERROR:{e}"
    finally:
        if 'img' in locals():
            del img
        if 'faces' in locals():
            del faces
        import gc
        gc.collect()


def index_faces_for_photos(
    db_path: str,
    limit: Optional[int] = None,
    num_workers: int = _NUM_WORKERS,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    shutdown_event=None,
) -> int:
    """
    For photos where has_faces IS NULL, detect and embed faces
    using a pool of worker processes, then write results to the DB.

    Workers are recycled every _TASKS_PER_CHILD images to prevent
    ONNX runtime resource degradation.

    Failed images are logged to the failed_images table and retried
    on subsequent sync runs (up to 3 attempts before marking permanent).

    :return: Total number of face records inserted.
    """
    db_path = Path(db_path)
    db_path_str = str(db_path)

    # ── Load permanently failed images to skip ────────────────────────────
    permanently_failed = set()
    try:
        conn_check = get_db_connection(db_path_str, timeout=10)
        rows = conn_check.execute(
            "SELECT path FROM failed_images WHERE stage = 'FACES' AND permanent = 1"
        ).fetchall()
        permanently_failed = {r[0] for r in rows}
        conn_check.close()
    except Exception:
        pass  # Table may not exist on first run before migration

    conn = get_db_connection(db_path_str, timeout=30)
    try:
        query = "SELECT id, path FROM photos WHERE has_faces IS NULL"
        if limit is not None:
            query += f" LIMIT {limit}"
        photos = conn.execute(query).fetchall()
    finally:
        conn.close()

    # Filter out permanently failed images
    if permanently_failed:
        before = len(photos)
        photos = [(pid, p) for pid, p in photos if p not in permanently_failed]
        skipped_perm = before - len(photos)
        if skipped_perm > 0:
            print(f"[PixelRAG] Skipped {skipped_perm} permanently failed images.")

    if not photos:
        print("[PixelRAG] No unindexed photos found.")
        return 0

    print(f"[PixelRAG] Indexing faces for {len(photos)} photos "
          f"({num_workers} workers, CPU, recycle@{_TASKS_PER_CHILD})...")

    # ── pHash deduplication phase (exact match only) ─────────────────────
    conn = get_db_connection(db_path_str, timeout=30)
    try:
        photos_to_process = []
        duplicates_skipped = 0

        for photo_id, path in photos:
            photo_path = Path(path)
            phash_str = _compute_phash(photo_path)

            if phash_str:
                conn.execute("UPDATE photos SET phash = ? WHERE id = ?", (phash_str, photo_id))

            if phash_str and _check_phash_duplicate(conn, phash_str, photo_id):
                conn.execute("UPDATE photos SET has_faces = 0 WHERE id = ?", (photo_id,))
                duplicates_skipped += 1
                print(f"[PixelRAG] Skipping near-duplicate: {photo_path.name}")
            else:
                photos_to_process.append((photo_id, path))

        conn.commit()
    finally:
        conn.close()

    if duplicates_skipped > 0:
        print(f"[PixelRAG] Skipped {duplicates_skipped} near-duplicate photos.")

    if not photos_to_process:
        print("[PixelRAG] No unique photos to process after deduplication.")
        return 0

    # ── Parallel inference phase (ProcessPoolExecutor) ─────────────────────
    results: dict[int, FaceResult] = {}
    total = len(photos_to_process)
    completed = 0
    skipped = 0
    shutdown_triggered = False

    # Parent-enforced timeout. By bounding the queue depth, submission time
    # is almost exactly execution start time.
    _PARENT_TIMEOUT = _INFERENCE_TIMEOUT + 30  # 90s total grace

    ctx = get_context('spawn')  # 'spawn' is required on macOS
    
    # Save a copy since the while loop shrinks photos_to_process to zero
    _original_photos_to_process = list(photos_to_process)

    while photos_to_process and not shutdown_triggered:
        # max_tasks_per_child requires Python 3.11+
        import sys
        executor_kwargs = {
            'max_workers': num_workers,
            'mp_context': ctx,
            'initializer': _worker_init,
        }
        if sys.version_info >= (3, 11):
            executor_kwargs['max_tasks_per_child'] = _TASKS_PER_CHILD
        executor = ProcessPoolExecutor(**executor_kwargs)

        future_to_photo = {}
        future_submit_time = {}
        pending = set()
        photos_iter = iter(photos_to_process)
        pool_broken = False

        def _fill_queue():
            # Bound the queue to (workers * 2) so tasks don't idle in the queue.
            # This prevents false "hung" positives.
            while len(pending) < num_workers * 2:
                try:
                    photo_id, path = next(photos_iter)
                    future = executor.submit(_worker_process_photo, path)
                    future_to_photo[future] = (photo_id, path)
                    future_submit_time[future] = time.time()
                    pending.add(future)
                except StopIteration:
                    break

        try:
            _fill_queue()

            while pending:
                if shutdown_event is not None and shutdown_event.is_set():
                    print("[PixelRAG] ⚠️ SHUTDOWN_EVENT detected — breaking out of inference loop")
                    shutdown_triggered = True
                    break

                from concurrent.futures import wait, FIRST_COMPLETED, process
                
                try:
                    done, pending = wait(pending, timeout=10, return_when=FIRST_COMPLETED)
                except Exception:
                    # Broken process pool exception
                    pool_broken = True
                    done = set()

                # Process completed futures
                for future in done:
                    photo_id, path = future_to_photo[future]

                    try:
                        raw = future.result(timeout=1)
                        completed += 1
                        
                        if progress_callback:
                            progress_callback(completed, total, f"Analyzing: {Path(path).name}")

                        if isinstance(raw, str):
                            if raw == "TIMEOUT":
                                # Worker-side timeout is also a machinery signal,
                                # not evidence the image itself is unprocessable.
                                print(f"[PixelRAG] ⚠️  TIMEOUT: {Path(path).name} — skipped")
                                skipped += 1
                                _log_failed_image(db_path_str, path, 'FACES',
                                                  'Inference timeout', infra=True)
                            else:
                                error_detail = raw.replace("ERROR:", "", 1)
                                print(f"[PixelRAG] ⚠️  {Path(path).name}: {raw}")
                                _log_failed_image(db_path_str, path, 'FACES', error_detail)
                            results[photo_id] = []
                        else:
                            face_list = []
                            for x1, y1, x2, y2, det_score, lap_var, roll, face_size_ratio, emb_bytes in raw:
                                emb = np.frombuffer(emb_bytes, dtype=np.float32).copy()
                                face_list.append((x1, y1, x2, y2, det_score, lap_var, roll, face_size_ratio, emb))
                            results[photo_id] = face_list

                    except process.BrokenProcessPool as e:
                        # INFRASTRUCTURE failure: the pool died, not the image.
                        # Do not charge this photo — it is left out of `results`
                        # so the outer while-loop retries it with a fresh pool.
                        pool_broken = True
                        print(f"[PixelRAG] ⚠️  Broken process pool while on "
                              f"{Path(path).name} — will retry with a fresh pool")
                        _log_failed_image(db_path_str, path, 'FACES', str(e), infra=True)
                        break
                    except Exception as e:
                        completed += 1
                        print(f"[PixelRAG] ⚠️  {Path(path).name}: {e}")
                        results[photo_id] = []
                        skipped += 1
                        _log_failed_image(db_path_str, path, 'FACES', str(e))

                        if progress_callback:
                            progress_callback(completed, total, f"Analyzing: {Path(path).name}")

                    if completed % 50 == 0:
                        print(f"[PixelRAG]   ✓ Analyzed {completed}/{total} photos... ({skipped} skipped)")

                if pool_broken:
                    break

                # Check for hung C++ workers using our precise submission time
                now = time.time()
                hung_futures = [
                    f for f in pending
                    if (now - future_submit_time[f]) > _PARENT_TIMEOUT
                ]

                if hung_futures:
                    for f in hung_futures:
                        photo_id, path = future_to_photo[f]
                        elapsed = now - future_submit_time[f]
                        print(f"[PixelRAG] ⚠️  HUNG ({elapsed:.0f}s): {Path(path).name} — killing pool, skipping photo")

                        # The parent-side watchdog cannot distinguish "this image
                        # wedged the decoder" from "the worker was starved/swapping".
                        # Logged as INFRA so a slow moment never accumulates toward
                        # permanent=1. The photo is still marked done for THIS run
                        # (results[photo_id] = []) so the pass can finish, but its
                        # has_faces stays NULL, so the next sync retries it.
                        results[photo_id] = []
                        skipped += 1
                        completed += 1
                        _log_failed_image(db_path_str, path, 'FACES',
                                          f'Hung worker ({elapsed:.0f}s)', infra=True)

                        if progress_callback:
                            progress_callback(completed, total, f"Skipped hung: {Path(path).name}")
                    
                    pool_broken = True
                    break

                _fill_queue()

        finally:
            if pool_broken or shutdown_triggered:
                print("[PixelRAG] Hard resetting ProcessPoolExecutor...")
                # Best-effort cancellation for py 3.9+
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    executor.shutdown(wait=False)
                    
                _kill_executor_children(executor, timeout=5.0)
            else:
                executor.shutdown(wait=True)

        # Retain only photos that haven't been successfully evaluated or cleanly skipped
        photos_to_process = [p for p in photos_to_process if p[0] not in results]

        # Ensure OS has fully reclaimed resources before spawning new workers
        if photos_to_process and not shutdown_triggered:
            time.sleep(3)
        
    print(f"[PixelRAG]   ✓ Finished analyzing photos. Starting DB writes...")

    # ── DB write & Auto-Tagging phase ─────────────────────────────────────
    print("[PixelRAG] Loading Identity Gallery for Auto-Tagging...")
    conn = get_db_connection(db_path_str, timeout=30)
    try:

        gallery_rows = conn.execute(
            """
            SELECT f.person_id, fe.embedding
            FROM faces f
            JOIN face_embeddings fe ON f.id = fe.face_id
            JOIN people p ON f.person_id = p.id
            WHERE f.is_representative = 1 AND p.confirmed = 1
            """
        ).fetchall()

        gallery_person_ids = []
        gallery_embeddings = []
        for pid, emb_blob in gallery_rows:
            gallery_person_ids.append(pid)
            emb_arr = np.frombuffer(emb_blob, dtype=np.float32)
            gallery_embeddings.append(emb_arr)

        gallery_person_ids = np.array(gallery_person_ids) if gallery_person_ids else np.array([])
        if len(gallery_embeddings) > 0:
            gallery_embeddings = np.array(gallery_embeddings)
            norms = np.linalg.norm(gallery_embeddings, axis=1, keepdims=True)
            gallery_embeddings = gallery_embeddings / (norms + 1e-10)
        else:
            gallery_embeddings = np.array([])

        total_faces = 0
        autotag_margin_rejects = 0

        for i, (photo_id, path) in enumerate(_original_photos_to_process):
            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(i + 1, total, f"Committing faces: {Path(path).name}")
            faces = results.get(photo_id, [])


            if not faces:
                conn.execute("UPDATE photos SET has_faces = 0 WHERE id = ?", (photo_id,))
                conn.commit()  # Persist the 0-face result
                continue

            # NOTE: this stage no longer writes scene_category. Scene routing is
            # owned entirely by scene_classifier.py, which reads the faces table
            # directly (any detected face => 'people'). The old ">60% face area"
            # override only fired on close-ups, so group and full-body shots fell
            # through to CLIP and were misfiled — 340 of 476 face-bearing photos
            # on the real library. Keeping the write here would race that logic.
            for bbox_x1, bbox_y1, bbox_x2, bbox_y2, det_score, lap_var, roll, face_size_ratio, emb in faces:

                assigned_person_id = None
                if len(gallery_embeddings) > 0:
                    emb_norm = emb / (np.linalg.norm(emb) + 1e-10)
                    sims = gallery_embeddings @ emb_norm

                    # Reduce per-PERSON before ranking. The gallery holds several
                    # representative faces per person, so a naive top-2 would
                    # usually return the same person twice and the margin would
                    # be meaningless.
                    best_by_person: dict[int, float] = {}
                    for pid_i, s in zip(gallery_person_ids, sims):
                        pid_i = int(pid_i)
                        s = float(s)
                        if s > best_by_person.get(pid_i, -1.0):
                            best_by_person[pid_i] = s

                    ranked = sorted(best_by_person.items(), key=lambda kv: -kv[1])
                    best_pid, best_sim = ranked[0]
                    second_sim = ranked[1][1] if len(ranked) > 1 else -1.0

                    # Assign only when the winner is both confident AND clearly
                    # ahead of the runner-up. A near-tie means the embedding sits
                    # between two identities; leaving it to clustering is
                    # recoverable, writing the wrong person_id here is not.
                    if best_sim > AUTOTAG_THRESHOLD and (best_sim - second_sim) >= AUTOTAG_MARGIN:
                        assigned_person_id = best_pid
                    elif best_sim > AUTOTAG_THRESHOLD:
                        autotag_margin_rejects += 1

                conn.execute(
                    "INSERT INTO faces (photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, person_id, sharpness, roll_angle, det_score, face_size_ratio) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (photo_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, assigned_person_id, lap_var, roll, det_score, face_size_ratio),
                )
                face_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                emb_bytes = emb.astype(np.float32).tobytes()
                conn.execute(
                    "INSERT OR REPLACE INTO face_embeddings (face_id, dim, embedding) VALUES (?, ?, ?)",
                    (face_id, emb.shape[0], emb_bytes),
                )
                total_faces += 1

            conn.execute("UPDATE photos SET has_faces = 1 WHERE id = ?", (photo_id,))
            conn.commit()  # Persist the face results
        
        # Final vacuum / optimize ? No, just stay responsive
    finally:
        conn.close()

    print(f"[PixelRAG] Done. Total faces indexed: {total_faces}")
    if autotag_margin_rejects:
        print(f"[PixelRAG] Auto-tag margin rejected {autotag_margin_rejects} "
              f"near-tie assignments (>= {AUTOTAG_THRESHOLD} but margin < "
              f"{AUTOTAG_MARGIN}) — left for clustering to resolve.")
    return total_faces


def _kill_executor_children(executor, timeout: float = 5.0):
    """Kill all child processes of the executor and reap them to prevent zombies."""
    try:
        child_pids = [p.pid for p in executor._processes.values()
                      if p.pid is not None]
    except Exception:
        return

    if not child_pids:
        return

    print(f"[PixelRAG] Cleaning up {len(child_pids)} worker processes...")

    # First attempt: SIGTERM, give them a moment to exit cleanly
    for pid in child_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # Wait briefly for clean exit
    deadline = time.monotonic() + min(timeout, 2.0)
    remaining = list(child_pids)
    while remaining and time.monotonic() < deadline:
        still_alive = []
        for pid in remaining:
            try:
                result = os.waitpid(pid, os.WNOHANG)
                if result == (0, 0):  # Not exited yet
                    still_alive.append(pid)
                # else: reaped successfully
            except ChildProcessError:
                pass  # Already reaped elsewhere
        remaining = still_alive
        if remaining:
            time.sleep(0.1)

    # Force kill anything still alive
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"[PixelRAG] Sent SIGKILL to child PID {pid}")
        except (ProcessLookupError, PermissionError):
            pass

    # Reap after SIGKILL — this is the critical step that prevents zombies
    for pid in remaining:
        try:
            os.waitpid(pid, 0)  # BLOCKING — waits until reaped
        except ChildProcessError:
            pass  # Already reaped
