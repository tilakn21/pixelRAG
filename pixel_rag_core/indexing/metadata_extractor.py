# pixel_rag_core/indexing/metadata_extractor.py

import sqlite3
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from PIL import Image, ExifTags

import re

def _fallback_fs_datetime(image_path: Path) -> str | None:
    try:
        ts = image_path.stat().st_mtime
        dt = datetime.fromtimestamp(ts)
        return dt.isoformat()
    except Exception:
        return None

def _parse_filename_datetime(filename: str) -> Optional[str]:
    """
    Common patterns:
    IMG_20230324_...
    IMG20240215...
    2022-10-15...
    """
    # 1. YYYYMMDD (e.g. IMG20230314, IMG_20230314)
    y_m_d = re.search(r'(?:IMG|VID)?_?(\d{4})(\d{2})(\d{2})', filename, re.IGNORECASE)
    if y_m_d:
        try:
            dt = datetime(int(y_m_d.group(1)), int(y_m_d.group(2)), int(y_m_d.group(3)))
            return dt.isoformat()
        except ValueError:
            pass
            
    # 2. YYYY-MM-DD
    hyphenated = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if hyphenated:
        try:
            dt = datetime(int(hyphenated.group(1)), int(hyphenated.group(2)), int(hyphenated.group(3)))
            return dt.isoformat()
        except ValueError:
            pass
            
    return None


# Map EXIF tag ids to names once
EXIF_TAGS = {v: k for k, v in ExifTags.TAGS.items()}


def _get_exif(image_path: Path):
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if not exif:
                return {}
            return {
                EXIF_TAGS.get(tag_id, tag_id): value
                for tag_id, value in exif.items()
            }
    except Exception:
        return {}


def _parse_exif_datetime(exif: dict) -> Optional[str]:
    """
    Try to parse EXIF date fields to ISO string.
    Order: DateTimeOriginal, DateTime, DateTimeDigitized.
    """
    for key in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
        dt_raw = exif.get(key)
        if not dt_raw:
            continue

        # Typically "YYYY:MM:DD HH:MM:SS"
        try:
            dt = datetime.strptime(str(dt_raw), "%Y:%m:%d %H:%M:%S")
            return dt.isoformat()
        except Exception:
            continue

    return None


def _convert_gps_to_degrees(value):
    """
    Convert GPS coordinates stored as (deg, min, sec) rational tuples to float degrees.
    """
    try:
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        return d + (m / 60.0) + (s / 3600.0)
    except Exception:
        return None


def _parse_gps(exif: dict) -> Tuple[Optional[float], Optional[float]]:
    gps_info = exif.get("GPSInfo")
    if not gps_info:
        return None, None

    # gps_info is dict keyed by ints; we need tag names inside GPS
    gps_tags = {}
    for t in gps_info:
        tag_name = ExifTags.GPSTAGS.get(t, t)
        gps_tags[tag_name] = gps_info[t]

    lat = lon = None

    gps_lat = gps_tags.get("GPSLatitude")
    gps_lat_ref = gps_tags.get("GPSLatitudeRef")
    gps_lon = gps_tags.get("GPSLongitude")
    gps_lon_ref = gps_tags.get("GPSLongitudeRef")

    if gps_lat and gps_lat_ref:
        lat_deg = _convert_gps_to_degrees(gps_lat)
        if lat_deg is not None:
            if gps_lat_ref in ["S", "s"]:
                lat_deg = -lat_deg
            lat = lat_deg

    if gps_lon and gps_lon_ref:
        lon_deg = _convert_gps_to_degrees(gps_lon)
        if lon_deg is not None:
            if gps_lon_ref in ["W", "w"]:
                lon_deg = -lon_deg
            lon = lon_deg

    return lat, lon

def extract_metadata_for_photo(image_path: Path):
    exif = _get_exif(image_path)

    created_at = None
    lat = lon = None
    camera_make = camera_model = None

    if exif:
        created_at = _parse_exif_datetime(exif)
        lat, lon = _parse_gps(exif)
        camera_make = exif.get("Make")
        camera_model = exif.get("Model")

        if isinstance(camera_make, bytes):
            camera_make = camera_make.decode(errors="ignore")
        if isinstance(camera_model, bytes):
            camera_model = camera_model.decode(errors="ignore")

    # Fallback 1: Try to parse date from filename strings (often more reliable than FS mtime)
    if created_at is None:
        created_at = _parse_filename_datetime(image_path.name)

    # Fallback 2: Filesystem modification time
    if created_at is None:
        created_at = _fallback_fs_datetime(image_path)

    return created_at, lat, lon, camera_make, camera_model



def enrich_photos_metadata(db_path: str, limit: Optional[int] = None) -> int:
    """
    For photos with NULL created_at (or other empty meta), extract metadata from EXIF
    and update the DB.

    :param db_path: path to SQLite db
    :param limit: optional limit for how many rows to process in one run
    :return: number of rows updated
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Select photos where created_at is NULL; you can extend this condition later
    query = """
        SELECT id, path
        FROM photos
        WHERE created_at IS NULL
    """
    if limit is not None:
        query += " LIMIT ?"
        cur.execute(query, (limit,))
    else:
        cur.execute(query)

    rows = cur.fetchall()

    updated_count = 0

    for photo_id, path in rows:
        img_path = Path(path)
        if not img_path.exists():
            # Skip missing files
            continue

        created_at, lat, lon, make, model = extract_metadata_for_photo(img_path)

        cur.execute(
            """
            UPDATE photos
            SET created_at = COALESCE(?, created_at),
                latitude   = COALESCE(?, latitude),
                longitude  = COALESCE(?, longitude),
                camera_make  = COALESCE(?, camera_make),
                camera_model = COALESCE(?, camera_model)
            WHERE id = ?
            """,
            (created_at, lat, lon, make, model, photo_id),
        )

        if cur.rowcount == 1:
            updated_count += 1

    conn.commit()
    conn.close()

    return updated_count
