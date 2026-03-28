# pixel_rag_server/routers/media.py
"""Media router — serves photos, thumbnails, and face crops with caching."""

import sqlite3
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

router = APIRouter(tags=["media"])

VALID_THUMB_SIZES = {200, 400, 800}
FACE_CROP_SIZE = 160
FACE_PADDING = 0.20  # 20% padding around bounding box


def _get_photo_path(db_path: str, photo_id: int) -> str:
    """Look up a photo's file path by its ID."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    row = conn.execute("SELECT path FROM photos WHERE id = ?", (photo_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail={"error": f"Photo {photo_id} not found"})
    return row[0]


def _open_and_orient(path: str) -> Image.Image:
    """Open an image and apply EXIF orientation."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def _ensure_thumb_dir(db_path: str, subdir: str) -> Path:
    """Ensure the thumbnail cache directory exists."""
    thumb_dir = Path(db_path).parent / "thumbs" / subdir
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir


@router.get("/media/photo/{photo_id}")
async def serve_photo(request: Request, photo_id: int):
    """Serve full-resolution photo by ID."""
    db_path = request.app.state.db_path
    photo_path = _get_photo_path(db_path, photo_id)

    if not Path(photo_path).exists():
        raise HTTPException(status_code=404, detail={"error": "Source file not found on disk"})

    # Convert to JPEG for consistent browser rendering
    img = _open_and_orient(photo_path)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92)
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/media/thumb/{photo_id}")
async def serve_thumbnail(
    request: Request,
    photo_id: int,
    size: int = Query(400),
):
    """Serve a resized WebP thumbnail with disk caching."""
    db_path = request.app.state.db_path

    if size not in VALID_THUMB_SIZES:
        raise HTTPException(
            status_code=400,
            detail={"error": f"Invalid size. Must be one of {VALID_THUMB_SIZES}"},
        )

    # Check cache first
    thumb_dir = _ensure_thumb_dir(db_path, str(size))
    cache_path = thumb_dir / f"{photo_id}.webp"

    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # Generate thumbnail
    photo_path = _get_photo_path(db_path, photo_id)
    if not Path(photo_path).exists():
        raise HTTPException(status_code=404, detail={"error": "Source file not found on disk"})

    img = _open_and_orient(photo_path)
    img.thumbnail((size, size), Image.LANCZOS)

    # Save to cache
    img.save(str(cache_path), format="WEBP", quality=82)

    return Response(
        content=cache_path.read_bytes(),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/media/face/{face_id}")
async def serve_face_crop(request: Request, face_id: int):
    """Serve a cropped face image from a source photo."""
    db_path = request.app.state.db_path

    # Check face crop cache
    face_dir = _ensure_thumb_dir(db_path, "faces")
    cache_path = face_dir / f"{face_id}.webp"

    if cache_path.exists():
        return Response(
            content=cache_path.read_bytes(),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    # Look up face and its bounding box
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    row = conn.execute(
        """
        SELECT f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, p.path
        FROM faces f
        JOIN photos p ON f.photo_id = p.id
        WHERE f.id = ?
        """,
        (face_id,),
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail={"error": f"Face {face_id} not found"})

    x1, y1, x2, y2, photo_path = row

    if not Path(photo_path).exists():
        raise HTTPException(status_code=404, detail={"error": "Source photo not found on disk"})

    img = _open_and_orient(photo_path)
    w, h = img.size

    # Add padding around the bounding box
    box_w = x2 - x1
    box_h = y2 - y1
    pad_x = box_w * FACE_PADDING
    pad_y = box_h * FACE_PADDING

    crop_x1 = max(0, int(x1 - pad_x))
    crop_y1 = max(0, int(y1 - pad_y))
    crop_x2 = min(w, int(x2 + pad_x))
    crop_y2 = min(h, int(y2 + pad_y))

    face_img = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    face_img = face_img.resize((FACE_CROP_SIZE, FACE_CROP_SIZE), Image.LANCZOS)

    # Save to cache
    face_img.save(str(cache_path), format="WEBP", quality=85)

    return Response(
        content=cache_path.read_bytes(),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800"},
    )
