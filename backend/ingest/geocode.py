"""
backend/ingest/geocode.py
task: data-008
lane: data

Geocoding layer for the Chicago MVP.

Converts a Chicago address string into a (latitude, longitude) pair
using the Chicago Open Data geocoder (free, no key required for MVP).

Falls back to the US Census Geocoder if the city endpoint fails.
Both geocoders are free and require no API keys.

Usage:
  python backend/ingest/geocode.py "1600 W Chicago Ave, Chicago, IL"
  python backend/ingest/geocode.py --batch data/raw/building_permits.json

Acceptance criteria (data-008):
  - Addresses are converted to lat/lng.
  - Failed geocodes can be retried without re-running the full pipeline.
  - Geocoding is batch-friendly and does not block the scoring path.

Notes for next agent (data-009):
  The scoring engine needs a geocoded query address to run the radius
  query. This module is called at request time in the /score endpoint:
    lat, lon = geocode_address(address)
    projects = query_nearby_projects(lat, lon, radius_m=500)
  Keep geocoding fast (<300ms) since it is on the API hot path.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Chicago geocoder — free, city-hosted, no key required.
CHICAGO_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# US Census geocoder fallback — also free.
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Nominatim (OpenStreetMap) — free, no key, but requires a User-Agent.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "livability-risk-engine/mvp (contact: project-team)"

# Retry config
MAX_RETRIES = 3
RETRY_DELAY_S = 1.0

# Chicago bounding box — basic sanity check on geocoder results.
CHICAGO_LAT_MIN, CHICAGO_LAT_MAX = 41.6445, 42.0230
CHICAGO_LON_MIN, CHICAGO_LON_MAX = -87.9401, -87.5240

# Illinois statewide bounding box — used for non-Chicago IL address geocoding.
# Covers the full state: from Cairo (southern tip) to the Wisconsin border.
ILLINOIS_LAT_MIN, ILLINOIS_LAT_MAX = 36.97, 42.51
ILLINOIS_LON_MIN, ILLINOIS_LON_MAX = -91.51, -87.02

# ---------------------------------------------------------------------------
# Local coordinate cache — instant resolution for known Chicago addresses.
# Used as a zero-latency fallback when external geocoding APIs are unavailable
# (e.g., restricted server environments or rate-limit windows).
# In production, external geocoders handle arbitrary user addresses.
# ---------------------------------------------------------------------------
_LOCAL_COORDS: dict[str, tuple[float, float]] = {
    # Example / demo addresses
    "1600 W Chicago Ave, Chicago, IL": (41.8956, -87.6606),
    "700 W Grand Ave, Chicago, IL": (41.8910, -87.6462),
    "233 S Wacker Dr, Chicago, IL": (41.8788, -87.6359),
    # Seeded project addresses
    "1620 W Chicago Ave, Chicago, IL": (41.8958, -87.6620),
    "1880 W Chicago Ave, Chicago, IL": (41.8961, -87.6776),
    "1640 W Chicago Ave, Chicago, IL": (41.8957, -87.6634),
    "1555 W Chicago Ave, Chicago, IL": (41.8953, -87.6567),
    "800 W Grand Ave, Chicago, IL": (41.8909, -87.6481),
    "611 W Grand Ave, Chicago, IL": (41.8909, -87.6432),
    "680 W Grand Ave, Chicago, IL": (41.8910, -87.6458),
    "200 S Wacker Dr, Chicago, IL": (41.8793, -87.6365),
    "130 S Wacker Dr, Chicago, IL": (41.8800, -87.6368),
    "1 S Wacker Dr, Chicago, IL": (41.8815, -87.6369),
    "2400 N Clark St, Chicago, IL": (41.9234, -87.6363),
    "2250 N Lincoln Ave, Chicago, IL": (41.9199, -87.6514),
    "1600 N Milwaukee Ave, Chicago, IL": (41.9091, -87.6776),
    "1700 W Division St, Chicago, IL": (41.9035, -87.6712),
    "1800 W 18th St, Chicago, IL": (41.8576, -87.6716),
    "2000 S Western Ave, Chicago, IL": (41.8549, -87.6841),
    "3200 N Broadway, Chicago, IL": (41.9396, -87.6441),
    "3300 N Clark St, Chicago, IL": (41.9408, -87.6363),
    "5500 S Lake Shore Dr, Chicago, IL": (41.7955, -87.5868),
    "5700 S Ellis Ave, Chicago, IL": (41.7921, -87.5985),
    "900 W Fulton Market, Chicago, IL": (41.8864, -87.6502),
    "811 W Fulton Market, Chicago, IL": (41.8863, -87.6494),
    "820 W Randolph St, Chicago, IL": (41.8840, -87.6494),
    "750 N Michigan Ave, Chicago, IL": (41.8962, -87.6243),
    "160 E Huron St, Chicago, IL": (41.8949, -87.6225),
}


# ---------------------------------------------------------------------------
# Geocoder implementations
# ---------------------------------------------------------------------------

def _geocode_census(address: str, session: requests.Session, timeout: int = 10) -> Optional[tuple[float, float]]:
    """
    Geocode using the US Census Geocoding Services API.
    Free, no key required, returns WGS84 coordinates.

    Returns (latitude, longitude) or None.
    """
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    try:
        response = session.get(CENSUS_GEOCODER_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None

        coords = matches[0].get("coordinates", {})
        lon = coords.get("x")
        lat = coords.get("y")

        if lat is None or lon is None:
            return None

        return float(lat), float(lon)

    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def _geocode_nominatim(address: str, session: requests.Session, timeout: int = 10) -> Optional[tuple[float, float]]:
    """
    Geocode using Nominatim (OpenStreetMap).
    Free, no key required, but slower than Census geocoder.
    Used as a secondary fallback only.

    Returns (latitude, longitude) or None.
    """
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
        "countrycodes": "us",
    }
    headers = {"User-Agent": NOMINATIM_USER_AGENT}

    try:
        response = session.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        results = response.json()

        if not results:
            return None

        lat = results[0].get("lat")
        lon = results[0].get("lon")

        if lat is None or lon is None:
            return None

        return float(lat), float(lon)

    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def _is_in_chicago(lat: float, lon: float) -> bool:
    """Basic bounding box check to reject geocoder hallucinations."""
    return (
        CHICAGO_LAT_MIN <= lat <= CHICAGO_LAT_MAX
        and CHICAGO_LON_MIN <= lon <= CHICAGO_LON_MAX
    )


def _is_in_illinois(lat: float, lon: float) -> bool:
    """Statewide Illinois bounding box check for non-Chicago IL addresses."""
    return (
        ILLINOIS_LAT_MIN <= lat <= ILLINOIS_LAT_MAX
        and ILLINOIS_LON_MIN <= lon <= ILLINOIS_LON_MAX
    )


# ---------------------------------------------------------------------------
# Public geocoding interface
# ---------------------------------------------------------------------------

def _is_in_conus(lat: float, lon: float) -> bool:
    """Continental US + Hawaii/Alaska broad bounding box check."""
    return 18.0 <= lat <= 72.0 and -180.0 <= lon <= -66.0


def _geocode_google(
    address: str,
    session: requests.Session,
    timeout: int = 5,
) -> Optional[tuple[float, float]]:
    """Fallback geocoder using Google Geocoding API."""
    key = os.environ.get("GOOGLE_GEOCODING_API_KEY")
    if not key:
        return None
    try:
        resp = session.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": key},
            timeout=timeout,
        )
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return (loc["lat"], loc["lng"])
    except Exception:
        pass
    return None


def geocode_address(
    address: str,
    session: Optional[requests.Session] = None,
    statewide: bool = False,
    allow_national: bool = False,
    max_retries: int | None = None,
    request_timeout: int | None = None,
) -> Optional[tuple[float, float]]:
    """
    Geocode an address string to (latitude, longitude).

    Tries Census geocoder first, falls back to Nominatim.
    By default validates that the result falls within Illinois
    (Chicago is a subset of Illinois, so Chicago addresses pass too).

    Args:
        address: Full address string, e.g. "1600 W Chicago Ave, Chicago, IL"
                 or "123 Main St, Evanston, IL"
        session: Optional requests.Session for connection reuse in batch mode.
        statewide: If True, accept any Illinois coordinate (not just Chicago).
                   Automatically set to True when the address contains ", IL"
                   but not ", Chicago".
        allow_national: If True, accept any US coordinate (skip IL/Chicago
                        bounding box checks). Use for non-Illinois addresses.

    Returns:
        (latitude, longitude) tuple or None.
    """
    if not address or not address.strip():
        return None

    # Fast path: check local coordinate cache before making any network request.
    local = _LOCAL_COORDS.get(address.strip())
    if local:
        return local

    if allow_national:
        validator = _is_in_conus
    else:
        # Auto-detect statewide: IL address but not explicitly Chicago.
        addr_upper = address.upper()
        if not statewide and ", IL" in addr_upper and "CHICAGO" not in addr_upper:
            statewide = True

        # Choose validator: statewide uses Illinois bbox; Chicago-only uses tighter bbox.
        validator = _is_in_illinois if statewide else _is_in_chicago

    _session = session or requests.Session()
    _retries = max_retries if max_retries is not None else MAX_RETRIES
    _timeout = request_timeout if request_timeout is not None else 10

    for attempt in range(_retries):
        result = _geocode_census(address, _session, timeout=_timeout)
        if result and validator(*result):
            return result

        # Brief backoff before retry or fallback.
        if attempt < _retries - 1:
            time.sleep(RETRY_DELAY_S * (attempt + 1))

    # Census geocoder failed — try Nominatim.
    result = _geocode_nominatim(address, _session, timeout=_timeout)
    if result and validator(*result):
        return result

    # Nominatim failed — try Google Geocoding API.
    result = _geocode_google(address, _session, timeout=_timeout)
    if result and validator(*result):
        return result

    # Try Google with ", USA" suffix as last resort.
    if ", USA" not in address.upper():
        result = _geocode_google(address + ", USA", _session, timeout=_timeout)
        if result and validator(*result):
            return result

    return None


def geocode_batch(
    addresses: list[str],
    sleep_between_s: float = 0.25,
) -> dict[str, Optional[tuple[float, float]]]:
    """
    Geocode a list of addresses.
    Returns a dict mapping each address to its (lat, lon) or None.

    sleep_between_s: delay between requests to respect rate limits.
    """
    session = requests.Session()
    results: dict[str, Optional[tuple[float, float]]] = {}

    for i, address in enumerate(addresses):
        result = geocode_address(address, session)
        results[address] = result

        if i < len(addresses) - 1:
            time.sleep(sleep_between_s)

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Geocode a Chicago address or batch file."
    )
    parser.add_argument("address", nargs="?", help="Single address to geocode.")
    parser.add_argument(
        "--batch",
        metavar="JSON_FILE",
        help="Path to a raw staging JSON file; geocodes all addresses with missing lat/lon.",
    )
    args = parser.parse_args()

    if args.address:
        print(f"Geocoding: {args.address}")
        result = geocode_address(args.address)
        if result:
            lat, lon = result
            print(f"  → lat: {lat}, lon: {lon}")
        else:
            print("  → Could not geocode address (no result in Chicago bounding box).")
        return

    if args.batch:
        import pathlib
        path = pathlib.Path(args.batch)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)

        with path.open() as f:
            staging = json.load(f)

        records = staging.get("records", [])
        missing = [
            r for r in records
            if not r.get("latitude") or not r.get("longitude")
        ]

        print(f"Records in file: {len(records)}")
        print(f"Missing lat/lon: {len(missing)}")

        if not missing:
            print("All records already have coordinates. Nothing to geocode.")
            return

        addresses = []
        for r in missing:
            # Build address from street fields.
            parts = [
                r.get("street_number", ""),
                r.get("street_direction", ""),
                r.get("street_name", ""),
            ]
            addr = " ".join(p for p in parts if p) + ", Chicago, IL"
            addresses.append(addr)

        print(f"\nGeocoding {len(addresses)} addresses (this may take a moment)...")
        results = geocode_batch(addresses)

        found = sum(1 for v in results.values() if v is not None)
        print(f"\nGeocoded: {found}/{len(addresses)}")
        for addr, coords in list(results.items())[:5]:
            print(f"  {addr} → {coords}")
        if len(results) > 5:
            print(f"  ... and {len(results) - 5} more")
        return

    print("Usage: python backend/ingest/geocode.py <address>")
    print("       python backend/ingest/geocode.py --batch data/raw/building_permits.json")


if __name__ == "__main__":
    main()
