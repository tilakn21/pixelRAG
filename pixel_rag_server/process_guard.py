# pixel_rag_server/process_guard.py
"""
Process-level hardening for PixelRAG workers.

Centralizes production safety mechanisms:
  - SHUTDOWN_EVENT: Global threading.Event for graceful shutdown coordination
  - Faulthandler: Captures SIGSEGV/SIGBUS crash traces to disk
  - Signal handlers: SIGTERM/SIGINT → graceful drain → sys.exit(0)
  - multiprocessing.set_start_method("spawn"): Required on macOS M-series

Removed (caused more bugs than they caught — see SOLVED_PROBLEMS.md):
  - RSS Memory Watchdog (false-positive aborts on unified memory)
  - Stall Detector (false-positive pipeline aborts)
  - WATCHDOG_EXEMPT mechanism
"""

import faulthandler
import logging
import multiprocessing
import os
import signal
import sys
import threading
import time
from pathlib import Path

# Windows consoles default to a legacy code page (cp1252). Pipeline log lines
# use Unicode (✓, ⚠️, …); printing them raises UnicodeEncodeError and aborts
# face indexing mid-sync. Force UTF-8 for this process and any spawn children.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger = logging.getLogger("pixelrag.process_guard")

# ── SHUTDOWN_EVENT ────────────────────────────────────────────────────────────
# The backbone of all graceful shutdown logic across the entire app.
# Any component can check this to know if the process is draining.
SHUTDOWN_EVENT = threading.Event()

# ── Reference to the sync daemon thread (set by sync.py) ─────────────────────
_sync_thread: threading.Thread | None = None
_sync_thread_lock = threading.Lock()

# ── Guard against double-init ─────────────────────────────────────────────────
_initialized = False
_init_lock = threading.Lock()


def set_sync_thread(thread: threading.Thread | None):
    """Register the sync daemon thread so signal handlers can join it."""
    global _sync_thread
    with _sync_thread_lock:
        _sync_thread = thread


# ── Faulthandler Setup ───────────────────────────────────────────────────────

def _setup_faulthandler():
    """
    Enable faulthandler to capture SIGSEGV/SIGBUS crash traces.
    Writes to ~/.pixelrag/crash_<pid>.log — because try/except will
    never catch these C-level signals.
    """
    crash_dir = Path.home() / ".pixelrag"
    crash_dir.mkdir(parents=True, exist_ok=True)
    crash_log = crash_dir / f"crash_{os.getpid()}.log"

    try:
        crash_file = open(crash_log, "a")
        faulthandler.enable(file=crash_file, all_threads=True)

        # Try to register additional handlers for SIGSEGV and SIGBUS.
        # SIGBUS does not exist on Windows; faulthandler.register() is Unix-only.
        # faulthandler.enable() above already covers crash dumps where supported.
        if hasattr(faulthandler, "register"):
            for name in ("SIGSEGV", "SIGBUS"):
                sig = getattr(signal, name, None)
                if sig is None:
                    continue
                try:
                    faulthandler.register(sig, file=crash_file, all_threads=True, chain=True)
                except (OSError, ValueError, RuntimeError, AttributeError):
                    pass  # Signal can't be registered on this platform — enable() covers it

        logger.info(f"[ProcessGuard] Faulthandler enabled → {crash_log}")
    except Exception as e:
        # Don't crash startup if faulthandler setup fails
        logger.warning(f"[ProcessGuard] Faulthandler setup failed: {e}")
        # Still enable to stderr as fallback
        faulthandler.enable()


# ── Signal Handlers ──────────────────────────────────────────────────────────

def _signal_handler(signum, frame):
    """
    SIGTERM/SIGINT handler: set SHUTDOWN_EVENT, wait for daemon thread
    to finish its current item, then exit cleanly.
    """
    sig_name = signal.Signals(signum).name
    logger.warning(f"[ProcessGuard] Received {sig_name} — initiating graceful shutdown")
    print(f"[ProcessGuard] Received {sig_name} — initiating graceful shutdown", flush=True)

    SHUTDOWN_EVENT.set()

    # Wait for the sync thread to finish its current item
    with _sync_thread_lock:
        thread = _sync_thread

    if thread is not None and thread.is_alive():
        logger.info("[ProcessGuard] Waiting up to 30s for sync thread to finish...")
        thread.join(timeout=30)
        if thread.is_alive():
            logger.warning("[ProcessGuard] Sync thread did not exit in 30s — forcing shutdown")

    logger.info("[ProcessGuard] Exiting cleanly.")
    sys.exit(0)


def _setup_signal_handlers():
    """Register SIGTERM and SIGINT handlers in the main thread only."""
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        logger.info("[ProcessGuard] Signal handlers registered (SIGTERM, SIGINT)")
    except ValueError:
        # signal.signal() can only be called from the main thread
        logger.warning("[ProcessGuard] Cannot register signal handlers (not main thread)")


# ── Spawn Start Method ────────────────────────────────────────────────────────

def _set_spawn_start_method():
    """
    Set multiprocessing start method to 'spawn' — required on macOS M-series.
    'fork' inherits CoreML/ANE session state into sub-processes, causing
    silent, unrecoverable hangs. Called exactly once, guarded.
    """
    try:
        multiprocessing.set_start_method("spawn", force=False)
        logger.info("[ProcessGuard] multiprocessing start method set to 'spawn'")
    except RuntimeError:
        # Already set — this is fine
        current = multiprocessing.get_start_method()
        if current != "spawn":
            logger.warning(
                f"[ProcessGuard] multiprocessing start method already set to '{current}' "
                f"(not 'spawn') — this may cause CoreML hangs on macOS"
            )
        else:
            logger.info("[ProcessGuard] multiprocessing start method already 'spawn'")


# ── OMP/BLAS/MKL env var locks ───────────────────────────────────────────────
# These are set early to prevent ONNX/numpy from spawning extra threads
# that compete with our worker processes for CPU time.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


# ── Main Entry Point ─────────────────────────────────────────────────────────

def init_process_guard():
    """
    Single entry point to activate all process-level hardening.
    Called from main.py lifespan. Safe to call multiple times (idempotent).
    """
    global _initialized

    with _init_lock:
        if _initialized:
            return
        _initialized = True

    logger.info("[ProcessGuard] Initializing process guard...")
    print("[ProcessGuard] Initializing process guard...", flush=True)

    # 1. Faulthandler (must be first — catches crashes during subsequent setup)
    _setup_faulthandler()

    # 2. Spawn start method (must be before any ProcessPoolExecutor is created)
    _set_spawn_start_method()

    # 3. Signal handlers
    _setup_signal_handlers()

    print("[ProcessGuard] All guards active (faulthandler, signals, spawn)", flush=True)
