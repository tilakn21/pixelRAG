# pixel_rag_server/routers/manage.py
"""
Destructive and export operations: deleting photos, and copying a selection
into a real folder on disk.

Deletion is the only irreversible thing this app does, so it is deliberately
explicit: the caller must name the mode, nothing is deleted implicitly, and the
response reports exactly what happened to each file.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from pixel_rag_server.dependencies import get_db_path, LibraryContext
from pixel_rag_server.services.db import get_conn

router = APIRouter(tags=["manage"])

# Album exports land here by default so they travel with the drive. The scanner
# skips this directory (see scan_photos.SKIP_DIR_NAMES), otherwise every export
# would be re-indexed as a near-duplicate of the original on the next sync.
ALBUM_DIR_NAME = "PixelRAG Albums"


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve_photo_ids(conn, photo_ids: Optional[List[int]], person_id: Optional[int]) -> List[int]:
    """Explicit ids, or every photo containing a given person."""
    if photo_ids:
        return list(dict.fromkeys(int(i) for i in photo_ids))
    if person_id is not None:
        rows = conn.execute(
            "SELECT DISTINCT photo_id FROM faces WHERE person_id = ?", (person_id,)
        ).fetchall()
        return [r[0] for r in rows]
    return []


def _paths_for(conn, ids: List[int]) -> dict:
    out = {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        ph = ",".join("?" * len(chunk))
        for pid, path in conn.execute(
            f"SELECT id, path FROM photos WHERE id IN ({ph})", chunk
        ):
            out[pid] = path
    return out


def _move_to_trash_macos(paths: List[str]) -> tuple[int, List[str]]:
    """Move files to the Trash via Finder (AppleScript)."""
    existing = [p for p in paths if Path(p).exists()]
    if not existing:
        return 0, []
    errors: List[str] = []
    moved = 0
    BATCH = 100
    for i in range(0, len(existing), BATCH):
        chunk = existing[i:i + BATCH]
        items = ", ".join(f'POSIX file "{p}"' for p in chunk)
        script = f"tell application \"Finder\" to delete {{{items}}}"
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                moved += sum(1 for p in chunk if not Path(p).exists())
            else:
                errors.append(r.stderr.strip()[:200] or "Finder refused the delete")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
    return moved, errors


def _move_to_trash_windows(paths: List[str]) -> tuple[int, List[str]]:
    """Move files to the Recycle Bin via SHFileOperationW (allows undo)."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x04
    FOF_NOERRORUI = 0x0400

    existing = [str(Path(p)) for p in paths if Path(p).exists()]
    if not existing:
        return 0, []

    errors: List[str] = []
    moved = 0
    # Double-null-terminated list of paths.
    from_buf = "\0".join(existing) + "\0\0"
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = from_buf
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    op.fAnyOperationsAborted = False
    op.hNameMappings = None
    op.lpszProgressTitle = None

    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result == 0 and not op.fAnyOperationsAborted:
            moved = sum(1 for p in existing if not Path(p).exists())
            if moved < len(existing):
                errors.append("Some files could not be moved to the Recycle Bin")
        else:
            errors.append(f"Recycle Bin operation failed (code {result})")
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
    return moved, errors


def _move_to_trash(paths: List[str]) -> tuple[int, List[str]]:
    """
    Move files to the OS trash / Recycle Bin (recoverable).

    macOS: Finder via AppleScript (works on exFAT volumes via .Trashes).
    Windows: shell32 SHFileOperationW with FOF_ALLOWUNDO.
    Other: clear error — callers can use permanent delete instead.
    """
    if sys.platform == "darwin":
        return _move_to_trash_macos(paths)
    if sys.platform == "win32":
        return _move_to_trash_windows(paths)
    return 0, [
        "Move to Trash is only supported on macOS and Windows. "
        "Use permanent delete instead."
    ]


def _permanently_delete(paths: List[str]) -> tuple[int, List[str]]:
    removed, errors = 0, []
    for p in paths:
        try:
            if Path(p).exists():
                os.remove(p)
                removed += 1
        except Exception as e:
            errors.append(f"{Path(p).name}: {e}")
    return removed, errors


def _purge_db(conn, ids: List[int]) -> int:
    """Remove photos and every dependent row. FKs are ON in the pool, but the
    deletes are explicit so behaviour does not depend on pragma state."""
    total = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        ph = ",".join("?" * len(chunk))
        conn.execute(
            f"DELETE FROM face_embeddings WHERE face_id IN "
            f"(SELECT id FROM faces WHERE photo_id IN ({ph}))", chunk)
        conn.execute(f"DELETE FROM photo_embeddings WHERE photo_id IN ({ph})", chunk)
        conn.execute(f"DELETE FROM faces WHERE photo_id IN ({ph})", chunk)
        cur = conn.execute(f"DELETE FROM photos WHERE id IN ({ph})", chunk)
        total += cur.rowcount
    # Identities left with no faces are meaningless; drop the auto ones.
    conn.execute("""
        DELETE FROM people
         WHERE confirmed = 0
           AND id NOT IN (SELECT DISTINCT person_id FROM faces WHERE person_id IS NOT NULL)
    """)
    conn.commit()
    return total


def _drop_cached_thumbs(lib_ctx: LibraryContext, photo_ids: List[int]):
    """Delete cached renditions so a recycled photo id can never show a stale image."""
    import hashlib
    base = Path.home() / ".pixelrag" / "thumbs" / \
        hashlib.md5(lib_ctx.library_path.encode()).hexdigest()[:12]
    for size in ("200", "400", "800"):
        d = base / size
        if not d.is_dir():
            continue
        for pid in photo_ids:
            f = d / f"{pid}.webp"
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass


# ── delete ───────────────────────────────────────────────────────────────────

class DeleteBody(BaseModel):
    photo_ids: Optional[List[int]] = None
    person_id: Optional[int] = Field(
        None, description="Delete every photo containing this person")
    mode: Literal["trash", "permanent", "forget"] = "trash"


@router.post("/photos/delete")
def delete_photos(request: Request, body: DeleteBody,
                  lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Delete photos.

    mode:
      trash     - move the file to the Trash (recoverable), remove from library
      permanent - erase the file, remove from library
      forget    - remove from the library only, leave the file untouched
    """
    conn = get_conn(lib_ctx.db_path, timeout=30)
    ids = _resolve_photo_ids(conn, body.photo_ids, body.person_id)
    if not ids:
        raise HTTPException(status_code=400,
                            detail={"error": "No photos selected."})

    id_to_path = _paths_for(conn, ids)
    known = list(id_to_path.keys())
    if not known:
        raise HTTPException(status_code=404,
                            detail={"error": "None of those photos exist in this library."})

    paths = [id_to_path[i] for i in known]
    missing = sum(1 for p in paths if not Path(p).exists())

    files_removed, errors = 0, []
    if body.mode == "trash":
        files_removed, errors = _move_to_trash(paths)
    elif body.mode == "permanent":
        files_removed, errors = _permanently_delete(paths)

    removed = _purge_db(conn, known)
    _drop_cached_thumbs(lib_ctx, known)

    return {
        "requested": len(ids),
        "removed_from_library": removed,
        "files_affected": files_removed,
        "files_already_missing": missing,
        "mode": body.mode,
        "errors": errors[:10],
        "note": ("Files were moved to the Trash on the drive they live on "
                 "(<volume>/.Trashes), not the Mac's Trash."
                 if body.mode == "trash" and files_removed else None),
    }


# ── export to a real folder ──────────────────────────────────────────────────

# Where an export can land. The frontend should not have to know the Mac's home
# directory, so it sends a keyword and the server resolves it.
DEST_SHORTCUTS = {
    "desktop": lambda: Path.home() / "Desktop",
    "downloads": lambda: Path.home() / "Downloads",
    "pictures": lambda: Path.home() / "Pictures",
}


def _resolve_destination(destination: Optional[str], lib_ctx: LibraryContext) -> Path:
    """Keyword, explicit path, or the album folder on the library drive."""
    if not destination or destination.lower() == "library":
        return Path(lib_ctx.library_path) / ALBUM_DIR_NAME
    key = destination.lower()
    if key in DEST_SHORTCUTS:
        return DEST_SHORTCUTS[key]()
    return Path(destination).expanduser()


class ExportBody(BaseModel):
    photo_ids: Optional[List[int]] = None
    person_id: Optional[int] = None
    name: str = Field(..., min_length=1, description="Folder name to create")
    destination: Optional[str] = Field(
        None,
        description="'library' (default), 'desktop', 'downloads', 'pictures', "
                    "or an absolute path.")


@router.post("/albums/export")
def export_album(request: Request, body: ExportBody,
                 lib_ctx: LibraryContext = Depends(get_db_path)):
    """Copy the selected photos into a real folder on disk. Originals untouched."""
    safe = "".join(ch for ch in body.name if ch not in '/\\:*?"<>|').strip()
    if not safe:
        raise HTTPException(status_code=400, detail={"error": "Invalid folder name."})

    parent = _resolve_destination(body.destination, lib_ctx)
    target = parent / safe

    conn = get_conn(lib_ctx.db_path, timeout=30)
    ids = _resolve_photo_ids(conn, body.photo_ids, body.person_id)
    if not ids:
        raise HTTPException(status_code=400, detail={"error": "No photos selected."})
    id_to_path = _paths_for(conn, ids)

    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400,
                            detail={"error": f"Could not create folder: {e}"})

    copied, skipped, errors = 0, 0, []
    for pid, src in id_to_path.items():
        s = Path(src)
        if not s.exists():
            skipped += 1
            continue
        dest = target / s.name
        # Never overwrite: disambiguate with the photo id instead.
        if dest.exists():
            dest = target / f"{s.stem}_{pid}{s.suffix}"
        try:
            shutil.copy2(s, dest)
            copied += 1
        except Exception as e:
            errors.append(f"{s.name}: {e}")

    return {
        "folder": str(target),
        "requested": len(ids),
        "copied": copied,
        "skipped_missing": skipped,
        "errors": errors[:10],
    }


# ── zip download ─────────────────────────────────────────────────────────────

# A phone on the LAN cannot reach a folder on the Mac's disk, so "give me these
# photos" has to mean "send me the bytes". Capped deliberately: a 20,000-photo
# zip is not a feature, it is an accident.
MAX_ZIP_PHOTOS = 500
WEB_SIZE_PX = 2048


def _web_copy(src: Path, dest_dir: Path) -> Path:
    """
    Downscaled JPEG for sharing.

    WhatsApp re-compresses everything it sends anyway, so shipping a 6 MB
    original only buys a slower upload and an identical result at the far end.
    Orientation handling is imported rather than reimplemented so it cannot
    drift from what the thumbnail endpoint does.
    """
    from PIL import Image

    from pixel_rag_server.routers.media import _open_and_orient

    img = _open_and_orient(str(src))

    # Already small enough and already a JPEG: hand back the original. Measured
    # on this library, re-encoding such files at quality 88 grew them (184 KB →
    # 216 KB) while adding a generation of loss — worse on both counts.
    if max(img.size) <= WEB_SIZE_PX and src.suffix.lower() in {".jpg", ".jpeg"}:
        img.close()
        return src

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((WEB_SIZE_PX, WEB_SIZE_PX), Image.LANCZOS)
    out = dest_dir / f"{src.stem}.jpg"
    img.save(out, "JPEG", quality=88, optimize=True)
    return out


class ZipBody(BaseModel):
    photo_ids: Optional[List[int]] = None
    person_id: Optional[int] = None
    name: str = Field("PixelRAG", min_length=1)
    size: Literal["original", "web"] = "original"


@router.post("/albums/zip")
def zip_album(request: Request, body: ZipBody,
              lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Return the selection as a .zip the browser can download.

    This is what makes sharing work away from the Mac: on a phone there is no
    filesystem to export into, so the only useful export is the bytes.

    A `def` handler on purpose — zipping hundreds of photos is blocking work and
    belongs in the threadpool, not on the event loop (same reason media.py
    serves thumbnails from a `def`).
    """
    conn = get_conn(lib_ctx.db_path, timeout=30)
    ids = _resolve_photo_ids(conn, body.photo_ids, body.person_id)
    if not ids:
        raise HTTPException(status_code=400, detail={"error": "No photos selected."})
    if len(ids) > MAX_ZIP_PHOTOS:
        raise HTTPException(
            status_code=400,
            detail={"error": f"{len(ids)} photos is too many for one download "
                             f"(limit {MAX_ZIP_PHOTOS}). Export to a folder instead."})

    id_to_path = _paths_for(conn, ids)
    safe = "".join(ch for ch in body.name if ch not in '/\\:*?"<>|').strip() or "PixelRAG"

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    staging = tempfile.mkdtemp(prefix="pixelrag_zip_")

    added, skipped = 0, 0
    try:
        # ZIP_STORED, not DEFLATE: JPEGs are already compressed, so deflating
        # them costs CPU and saves almost nothing.
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:
            used = set()
            for pid, src in id_to_path.items():
                s = Path(src)
                if not s.exists():
                    skipped += 1
                    continue
                try:
                    payload = _web_copy(s, Path(staging)) if body.size == "web" else s
                    arcname = payload.name
                    if arcname in used:
                        arcname = f"{payload.stem}_{pid}{payload.suffix}"
                    used.add(arcname)
                    zf.write(payload, arcname=f"{safe}/{arcname}")
                    added += 1
                except Exception:
                    skipped += 1
    except Exception as e:
        shutil.rmtree(staging, ignore_errors=True)
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail={"error": f"Could not build zip: {e}"})

    shutil.rmtree(staging, ignore_errors=True)
    if added == 0:
        os.unlink(tmp.name)
        raise HTTPException(status_code=404,
                            detail={"error": "None of the selected files could be read."})

    def _cleanup(path: str):
        try:
            os.unlink(path)
        except Exception:
            pass

    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"{safe}.zip",
        headers={
            "X-Photos-Added": str(added),
            "X-Photos-Skipped": str(skipped),
            # Without this the browser cannot read the two counters above.
            "Access-Control-Expose-Headers": "X-Photos-Added, X-Photos-Skipped",
        },
        background=BackgroundTask(_cleanup, tmp.name),
    )


# ── reveal ───────────────────────────────────────────────────────────────────

class RevealBody(BaseModel):
    path: str


@router.post("/albums/reveal")
def reveal_folder(body: RevealBody, lib_ctx: LibraryContext = Depends(get_db_path)):
    """
    Open an exported folder in Finder.

    Confined to the library drive and the usual export destinations. This
    endpoint asks the Mac to open something, so it must never accept an
    arbitrary path just because a request said so.
    """
    if sys.platform != "darwin":
        raise HTTPException(status_code=400,
                            detail={"error": "Revealing a folder is macOS only."})

    target = Path(body.path).expanduser().resolve()
    if not target.is_dir():
        raise HTTPException(status_code=400, detail={"error": "That folder does not exist."})

    roots = [Path(lib_ctx.library_path).resolve()]
    for make in DEST_SHORTCUTS.values():
        try:
            roots.append(make().resolve())
        except Exception:
            pass
    if not any(r == target or r in target.parents for r in roots):
        raise HTTPException(
            status_code=403,
            detail={"error": "Only folders on the library drive or in "
                             "Desktop/Downloads/Pictures can be opened."})

    try:
        subprocess.run(["open", str(target)], check=True, timeout=10)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": f"Finder refused: {e}"})
    return {"opened": str(target)}


@router.get("/identities/{person_id}/photo-ids")
def person_photo_ids(request: Request, person_id: int,
                     lib_ctx: LibraryContext = Depends(get_db_path)):
    """Every photo id containing this person — powers 'select all' in a cluster."""
    conn = get_conn(lib_ctx.db_path, timeout=15)
    rows = conn.execute(
        "SELECT DISTINCT photo_id FROM faces WHERE person_id = ?", (person_id,)
    ).fetchall()
    return {"photo_ids": [r[0] for r in rows], "count": len(rows)}
