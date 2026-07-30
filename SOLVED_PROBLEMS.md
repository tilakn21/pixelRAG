# PixelRAG: Chronological Problem Resolution Log

This document tracks all technical obstacles and production bugs resolved during the development and hardening of PixelRAG, ranging from critical system failures to UI refinements.

## Phase 1: Foundational Stability & Memory Management
*   **[MAJOR] 100GB RAM Memory Spikes:** Face indexing previously kept all embeddings in memory and leaked handles during high-parallelism runs.
    *   **Fix:** Implementation of `ProcessPoolExecutor` with `max_tasks_per_child` (40), ensuring child processes are recycled after a set number of images to flush RAM back to the OS.
*   **[MAJOR] CoreML Deadlocks on ARM:** Multi-threaded model loading caused the CoreML backend to deadlock on Apple Silicon.
    *   **Fix:** Restricted InsightFace and CLIP to `CPUExecutionProvider` for stable parallelism across background workers.
*   **[MINOR] FastAPI Module Errors:** Resolved persistent pathing issues by consolidating project roots and fixing `sys.path` injections across core modules.

## Phase 2: Intelligence & Accuracy Refinement
*   **[MAJOR] Identity Contamination:** Using HDBSCAN caused over-grouping.
    *   **Fix:** Switched to **Agglomerative Clustering** with a strict 0.48 cosine distance threshold.
*   **[MAJOR] Background Bystander Noise:** Tiny background faces were polluting clusters.
    *   **Fix:** Implemented a **Minimum Face Size Gate (80x80px)**, ignoring anything below this threshold to focus on primary subjects only.
*   **[MAJOR] Mis-categorization of People as 'Landscape':** Photos with people were being scanned by CLIP for scene tagging.
    *   **Fix:** Updated the pipeline to skip CLIP scene classification if InsightFace detected faces (has_faces > 0).
*   **[MINOR] Sharpness/Quality Filtering:** Faces that were blurry or out of focus were indexed, reducing cluster reliability.
    *   **Fix:** Implemented a **Laplacian Variance gate** (threshold current at 40.0) to ignore blurry detections.

## Phase 3: Production Hardening & Resilience
*   **[MAJOR] Silent Sync Aborts:** The system previously shared a stale `SHUTDOWN_EVENT` across runs; if one run failed, all future runs would instantly abort.
    *   **Fix:** Explicit `SHUTDOWN_EVENT.clear()` and stall disarming at every sync start.
*   **[MAJOR] Database Corruption during WIPE_AI:** Deleting folders while a background sync was writing to WAL caused filesystem locking errors.
    *   **Fix:** Implemented a **30s Drain Cycle** + explicit **PRAGMA wal_checkpoint(FULL)** ensuring all writes hit the disk before folder deletion.
*   **[MAJOR] Stall Detector False Positives:** The detector would previously fire if the process was idle because the timestamp wasn't reset.
    *   **Fix:** Implementation of `clear_progress()` in a `finally` block within `sync.py`, ensuring the detector is only armed during active pipeline execution.
*   **[MAJOR] Identity Drift & Contamination:** Manual merges or noisy clusters would "shift" over time without a clean baseline.
    *   **Fix:** Implemented an **Iterative Scrubbing Algorithm** (convergence loop in `update_person_profile`) that uses a Stable Centroid Baseline from the DB to eject outliers.
*   **[MINOR] Watchdog "Hung" False Positives:** Heavy clustering tasks were killed because they were too slow compared to image processing.
    *   **Fix:** Introduced `WATCHDOG_EXEMPT` with a 60-minute safety ceiling.

## Phase 4: Final Polishing
*   **[MINOR] UI "Confidence" Bug:** Confidences were rendering as `0.3%` instead of `30%` due to a JavaScript JS order-of-operation error in `(val || 0 * 100)`.
    *   **Fix:** Parenthetical correction to `((val || 0) * 100)`.
*   **[MINOR] Singleton UI Noise:** Very small or noisy clusters were cluttering the people gallery.
    *   **Fix:** Suppressed identities in the UI that have fewer than `PIXELRAG_MIN_CLUSTER_SIZE` (default 3) faces.
*   **[MAJOR] Event Loop Blocking:** The Suggested Merges API blocked the main web thread while performing $O(N^2)$ similarity calculations.
    *   **Fix:** Offloaded heavy matrix math to a thread pool using `asyncio.to_thread` (FastAPI/AnyIO) to maintain UI responsiveness.
