# pixel_rag_server/services/db.py
"""
Thread-local SQLite connection pool.

WHY THIS EXISTS — a reproduced, sampled deadlock, not a theory.

Every router used to do `sqlite3.connect(...)` / `conn.close()` per request.
Under the load of the /people page (343 identity rows plus 343 face-crop
requests), a worker thread deadlocked permanently here:

    pysqlite_connection_close
      sqlite3Close
        sqlite3LeaveMutexAndCloseZombie
          sqlite3BtreeClose
            sqlite3PagerClose
              sqlite3WalClose
                unixLock
                  _pthread_mutex_firstfit_lock_slow
                    __psynch_mutexwait        <-- stuck forever

`unixLock` contends on SQLite's process-wide unix-VFS mutex. Because CPython
holds the GIL for the duration of sqlite3_close, one stuck thread freezes the
ENTIRE interpreter — /healthz, which touches no database at all, stopped
answering too. In the browser that surfaces as `ECONNRESET` / socket hang up.

It was first observed with the DB on an exFAT volume, but it reproduced after
moving the DB to APFS, so the filesystem was not the cause — the per-request
close storm was.

The fix: open at most one connection per (thread, database) and never close it.
The anyio threadpool reuses its threads, so connections are reused with it, and
the sqlite3_close path is simply never entered while serving requests.

Connections are created with check_same_thread=False but are still only handed
to the thread that owns them, so no connection is ever used concurrently.
"""

import sqlite3
import threading
from typing import Dict

_local = threading.local()
_ALL_CONNS: list = []          # kept for introspection/diagnostics only
_ALL_LOCK = threading.Lock()


class PooledConnection:
    """
    Thin proxy whose .close() is a deliberate no-op.

    This keeps every existing `conn = ...; try: ... finally: conn.close()`
    call site working untouched, while ensuring the connection is actually
    retained for reuse rather than torn down (the tear-down being what
    deadlocked).
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name == "_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def close(self):
        """No-op: pooled connections outlive the request on purpose."""
        return None

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)


def get_conn(db_path: str, timeout: int = 30) -> PooledConnection:
    """Return this thread's connection for `db_path`, creating it on demand."""
    cache: Dict[str, PooledConnection] = getattr(_local, "conns", None)
    if cache is None:
        cache = {}
        _local.conns = cache

    conn = cache.get(db_path)
    if conn is not None:
        # Safety net for reuse: if a previous handler on this thread returned
        # without committing, an implicit transaction would still be open and
        # would hold a write lock for every later request on this thread.
        # Clear it rather than inherit it.
        try:
            if conn._conn.in_transaction:
                conn._conn.rollback()
        except Exception:
            cache.pop(db_path, None)
            conn = None

    if conn is None:
        raw = sqlite3.connect(db_path, timeout=timeout, check_same_thread=False)
        raw.execute("PRAGMA journal_mode=WAL")
        # Wait for a lock instead of raising instantly under concurrent load.
        raw.execute("PRAGMA busy_timeout=15000")
        raw.execute("PRAGMA foreign_keys=ON")
        conn = PooledConnection(raw)
        cache[db_path] = conn
        with _ALL_LOCK:
            _ALL_CONNS.append(raw)

    return conn


def pool_size() -> int:
    """Number of live pooled connections (diagnostics)."""
    with _ALL_LOCK:
        return len(_ALL_CONNS)
