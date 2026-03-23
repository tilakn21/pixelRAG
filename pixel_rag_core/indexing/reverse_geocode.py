# pixel_rag_core/indexing/reverse_geocode.py

import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

# Add project root to path so we can resolve pixel_rag_core imports easily
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable


def _check_geocache(conn: sqlite3.Connection, lat: float, lon: float):
    """Check if coordinates (rounded to 3 decimals) are in the geocache."""
    lat_r = round(lat, 3)
    lon_r = round(lon, 3)
    row = conn.execute(
        "SELECT city, state, country FROM geocache WHERE lat_rounded = ? AND lon_rounded = ?",
        (lat_r, lon_r)
    ).fetchone()
    if row:
        return row[0], row[1], row[2]
    return None


def _store_geocache(conn: sqlite3.Connection, lat: float, lon: float,
                    city: Optional[str], state: Optional[str], country: Optional[str]):
    """Store geocoding result in cache, rounded to 3 decimal places."""
    lat_r = round(lat, 3)
    lon_r = round(lon, 3)
    conn.execute(
        """INSERT OR REPLACE INTO geocache (lat_rounded, lon_rounded, city, state, country, resolved_at)
           VALUES (?, ?, ?, ?, ?, CAST(strftime('%s', 'now') AS INTEGER))""",
        (lat_r, lon_r, city, state, country)
    )


def get_location_details(lat: float, lon: float) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Reverse geocode a latitude and longitude into City, State, and Country.
    Uses OpenStreetMap's Nominatim API.
    """
    if lat is None or lon is None:
        return None, None, None

    geolocator = Nominatim(user_agent="pixelrag_local_photo_app")
    
    try:
        # Nominatim expects "lat, lon"
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, timeout=10)
        
        if not location or not location.raw.get('address'):
            return None, None, None
            
        address = location.raw['address']
        
        # City parsing: Nominatim can use various keys for the 'city' level
        city = address.get('city', '')
        if not city:
            city = address.get('town', '')
        if not city:
            city = address.get('village', '')
        if not city:
            city = address.get('county', '') # Fallback

        state = address.get('state', '')
        country = address.get('country', '')
        
        return city if city else None, state if state else None, country if country else None

    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        print(f"[PixelRAG] Geocoding error for {lat}, {lon}: {e}")
        return None, None, None
    except Exception as e:
        print(f"[PixelRAG] Unexpected geocoding error: {e}")
        return None, None, None


def enrich_photos_with_location(db_path: str, limit: Optional[int] = None) -> int:
    """
    Find photos with coordinates but no city/state/country, and reverse geocode them.
    Uses a geocache to avoid redundant API calls for nearby locations.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # Ensure geocache table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geocache (
            lat_rounded  REAL NOT NULL,
            lon_rounded  REAL NOT NULL,
            city         TEXT,
            state        TEXT,
            country      TEXT,
            resolved_at  INTEGER,
            PRIMARY KEY (lat_rounded, lon_rounded)
        )
    """)

    # Find photos that have a location but haven't been reverse-geocoded yet
    query = """
        SELECT id, latitude, longitude
        FROM photos
        WHERE latitude IS NOT NULL 
          AND longitude IS NOT NULL
          AND city IS NULL
    """
    
    if limit is not None:
        query += f" LIMIT {limit}"
        
    cur.execute(query)
    rows = cur.fetchall()

    if not rows:
        print("[PixelRAG] No photos need reverse geocoding.")
        conn.close()
        return 0

    print(f"[PixelRAG] Reverse geocoding {len(rows)} photos...")
    updated_count = 0

    for photo_id, lat, lon in rows:
        city = state = country = None

        # Check geocache first
        cached = _check_geocache(conn, lat, lon)
        if cached is not None:
            city, state, country = cached
        else:
            # Live API call
            city, state, country = get_location_details(lat, lon)

            # Store in geocache regardless of result
            _store_geocache(conn, lat, lon, city, state, country)
            conn.commit()

            # Rate limiting: 1.1 seconds between live API calls
            time.sleep(1.1)

        if city or state or country:
            cur.execute(
                """
                UPDATE photos 
                SET city = ?, state = ?, country = ?
                WHERE id = ?
                """,
                (city, state, country, photo_id)
            )
            updated_count += 1
        else:
            # Mark as attempted by setting empty strings so we don't infinitely retry
            cur.execute(
                """
                UPDATE photos 
                SET city = '', state = '', country = ''
                WHERE id = ?
                """,
                (photo_id,)
            )

    conn.commit()
    conn.close()
    
    print(f"[PixelRAG] Successfully geocoded {updated_count} photos.")
    return updated_count

if __name__ == "__main__":
    import argparse
    from pixel_rag_core.config import DB_PATH
    
    parser = argparse.ArgumentParser(description="Reverse geocode photos in DB.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of photos to geocode")
    parser.add_argument("--db", default=str(DB_PATH), help=f"Path to SQLite DB (default: {DB_PATH})")
    args = parser.parse_args()
    
    enrich_photos_with_location(args.db, limit=args.limit)
