# PixelRAG: The Complete Backend Whitepaper

This document is the **explicitly detailed** technical authority for the PixelRAG backend. It combines high-level architectural blueprints with low-level implementation details, covering every major component, constant, and system invariant.

---

## 1. System Invariants & macOS M-Series Configuration

### 1.1 Process Initialization
On startup, `main.py` enforces environment locks to ensure deterministic behavior on Apple Silicon (M1/M2/M3/M4):
*   **Multiprocessing Method:** Forced to `spawn` via `multiprocessing.set_start_method("spawn", force=True)`. 
    *   *Why:* The default `fork` on macOS inherits handles to the Apple Neural Engine (ANE) from the parent process. Sub-processes attempting to use these stale handles will hang indefinitely and silently.
*   **Thread Deadlock Prevention:**
    ```python
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    ```
    This prevents `onnxruntime` and `OpenBLAS` from spawning competing thread pools that clash with the FastAPI/Uvicorn event loop.

### 1.2 Resource Hardening (`process_guard.py`)
*   **The `SHUTDOWN_EVENT`:** A global `threading.Event` serving as the atomic "stop" signal. Checked by almost every loop (scanning, indexing, clustering).
*   **RSS Memory Watchdog:**
    *   **Threshold:** `PIXELRAG_MAX_WORKER_RSS_GB` (Default: 8.0GB).
    *   **Logic:** Tracks the main process RSS. If exceeded, it triggers `SHUTDOWN_EVENT`, waits for a 120s drain, and calls `sys.exit(0)`. Gunicorn then restarts a fresh worker.
    *   **Clustering Exemption:** During Agglomerative Clustering (which is O(n²) memory heavy), the watchdog is paused via `WATCHDOG_EXEMPT`. This exemption has a hard **60-minute ceiling**; if reached, the system clears the exemption and triggers a `SHUTDOWN_EVENT` with a standard 120s drain to prevent indefinite hangs.
*   **Stall Detector:**
    *   **Logic:** The system must receive an `update_progress()` heartbeat. This is called at every stage transition and after every image processed in long-running ML stages (Faces/Scenes). 
    *   **Threshold:** 10 minutes. If no heartbeat is received, it assumes a C++ level hang in ONNX/PyTorch and kills the process.
*   **Faulthandler:** Captures SIGSEGV/SIGBUS (segmentation faults) and writes them to `~/.pixelrag/crash_<pid>.log`.

---

## 2. Sync Pipeline Architecture (`sync.py` & `pipeline.py`)

### 2.1 Content-Hash Change Detection
PixelRAG avoids re-indexing unchanged images using a hybrid strategy:
1.  **Fast Path:** Compare file `mtime` (last modified) against `indexed_files` table.
2.  **Verification Path:** If `mtime` differs, compute **MD5 Hash** in 64KB chunks (`hashlib.md5`).
3.  **Deduplication:** Uses `imagehash` (pHash). If `Hamming Distance <= 2`, the image is treated as a near-duplicate and heavy face detection is skipped.

### 2.2 Pipeline Stages
The pipeline is a generator (`_run_sync_pipeline`) yielding progress tuples: `(stage_id, progress_%, stage_idx, total_stages, message)`.
1.  **SCAN:** filesystem scan and MD5 diffing.
2.  **EXIF:** Extraction of `taken_at`, `camera_make`, `camera_model`, `latitude`, `longitude`.
3.  **GEO:** Reverse geocoding via `geocache` table. Converts coordinates to `City, State, Country`.
4.  **FACES:** Parallel detection and embedding via `InsightFace`. Heartbeat sent per photo.
5.  **SCENES:** Zero-shot scene classification via `CLIP`. Heartbeat sent per photo.
6.  **CLUSTER:** Identity grouping and iterative purification. Heartbeat sent at start/end.

---

## 3. Face Intelligence Deep Dive (`face_indexer.py`)

### 3.1 Worker Process Pool
ML inference is offloaded to a `ProcessPoolExecutor`.
*   **Recycling (`_TASKS_PER_CHILD`):** Child processes are killed and recreated every 40 images to flush the ONNX runtime memory buffers back to the OS.
*   **Execution Provider:** Explicitly set to `['CPUExecutionProvider']`. This prevents multi-process deadlocks that occur when 4+ workers try to access the Neural Engine simultaneously.
*   **Hard Timeouts:** Workers use `signal.alarm(60)` per image. A corrupt or massive image cannot hang a worker indefinitely.

### 3.2 Quality Gates (Face Filtering)
Faces are only indexed if they meet these strict criteria:
*   **`MIN_DET_SCORE` (0.75):** Minimum probability from the detector.
*   **`MIN_FACE_PIXELS` (80):** Faces must be at least 80x80px in the original image.
*   **`MIN_LAPLACIAN_VAR` (40.0):** Sharpness gate using Laplacian variance.
*   **`MAX_ROLL_DEGREES` (35.0):** Maximum side-tilt of the head.

---

## 4. Clustering & Identity Science (`cluster_faces.py`)

### 4.1 Agglomerative Implementation
*   **Metric:** Cosine Similarity.
*   **Threshold:** `0.48`. Valid faces with distance > 0.48 to existing seeds form new clusters.
*   **Linkage:** `average`. Groups based on the average distance between all members of two clusters.

### 4.2 Iterative Scrubbing Algorithm (`update_person_profile`)
This is the "Purity Loop" that prevents contamination:
1.  Load the **Stable Centroid** from the `people` table.
2.  Execute up to 10 iteration passes:
    *   Find the face in the cluster with the highest distance to the centroid.
    *   If `distance > 0.45`, eject that face to noise (`cluster_id = NULL`).
    *   Recalculate centroid from the remaining pool of faces.
3.  Stop immediately if a pass results in 0 ejections (convergence reached).

### 4.3 Suggested Merges
PixelRAG proactively identifies potential identity merges to simplify library management:
*   **Endpoint:** `GET /api/identities/suggested-merges`
*   **Algorithm:** Performs an $O(N^2)$ Cosine Similarity scan across all confirmed person centroids.
*   **Threshold:** Defaults to `PIXELRAG_SUGGEST_MERGE_THRESHOLD: 0.72`. 
*   **Performance:** Similarity calculations are offloaded from the FastAPI event loop using `asyncio.to_thread()` (or `run_in_executor`) to maintain UI responsiveness during heavy matrix math.
*   **Pydantic Model:** `SuggestedMerge` schema contains `person_a`, `person_b`, and the similarity `score`.

---

## 5. Natural Language Query Engine (`query_engine.py`)

### 5.1 LLM Intent Extraction
Uses **Gemini 2.0 Flash** (with Llama-3 fallback) to parse user prompts into structured JSON:
*   **`names`**: Extracted identity strings.
*   **`scene_category`**: Validated against 13 taxonomies (Landscape, Food, etc.).
*   **`strict` / `exclusive`**: Booleans governing logic (AND vs OR and Alone vs Group).

### 5.2 Fuzzy Name Resolution
Uses `rapidfuzz` to resolve user-typed names against confirmed DB identities.
*   **Threshold:** `75` (token_sort_ratio).
*   **Logic:** Prevents search failures due to typos or common nicknames.

---

## 6. Database Persistence Layer

### 6.1 Table DDL Definitions (SQL)

```sql
CREATE TABLE IF NOT EXISTS photos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT NOT NULL UNIQUE,
    created_at   TEXT,
    latitude     REAL,
    longitude    REAL,
    has_faces    INTEGER DEFAULT 0,
    scene_category TEXT,
    scene_confidence REAL,
    file_hash    TEXT
);

CREATE TABLE IF NOT EXISTS faces (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id     INTEGER NOT NULL,
    person_id    INTEGER,
    cluster_id   INTEGER,
    sharpness    REAL,
    roll_angle   REAL,
    face_size_ratio REAL,
    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS people (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    centroid_embedding BLOB,
    confirmed    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    face_id      INTEGER PRIMARY KEY,
    embedding    BLOB NOT NULL,
    FOREIGN KEY(face_id) REFERENCES faces(id) ON DELETE CASCADE
);
```

### 6.3 Design Decisions
*   **Dynamic Singleton Suppression:** The `people` table does NOT store a `face_count`. To ensure accuracy, the UI filters out "singleton" or small clusters at query time using a subquery: `COUNT(*) >= PIXELRAG_MIN_CLUSTER_SIZE` (Default: 3). This avoids stale count anomalies during partial syncs.

### 6.2 Safety Checkpoints
*   **WAL Mode:** `PRAGMA journal_mode=WAL` is active on all connections.
*   **Full Checkpoint:** When deleting a library, the system forces `PRAGMA wal_checkpoint(FULL)` to ensure all uncommitted writes are unified into the main DB file before directory deletion.

---

## 7. Known Limitations & Future Work

### 7.1 The Orphan Graveyard
Faces ejected by the **Iterative Scrubber** have their `cluster_id` and `person_id` set to `NULL`. While the main clustering engine reconsidered these in every sweep, singletons (faces that don't match anything else strictly) would historically accumulate as noise.
*   **Current Solution:** A "Face Re-entry" stage scans orphans against confirmed centroids at the start of every clustering pass.
*   **Persistence:** Faces failing both the re-entry and clustering gates remain as `NULL` identities, serving as a high-precision noise filter.
