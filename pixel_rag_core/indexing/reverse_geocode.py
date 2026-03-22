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
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

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
        city, state, country = get_location_details(lat, lon)
        
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
            
            # Respect Nominatim API usage policy (1 request per second absolute max)
            time.sleep(1.1)
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
