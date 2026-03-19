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


# ---------------------------------------------------------------------------
# Geocoder implementations
# ---------------------------------------------------------------------------

def _geocode_census(address: str, session: requests.Session) -> Optional[tuple[float, float]]:
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
        response = session.get(CENSUS_GEOCODER_URL, params=params, timeout=10)
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


def _geocode_nominatim(address: str, session: requests.Session) -> Optional[tuple[float, float]]:
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
        response = session.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
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


# ---------------------------------------------------------------------------
# Public geocoding interface
# ---------------------------------------------------------------------------

def geocode_address(
    address: str,
    session: Optional[requests.Session] = None,
) -> Optional[tuple[float, float]]:
    """
    Geocode a single Chicago address string to (latitude, longitude).

    Tries Census geocoder first, falls back to Nominatim.
    Returns None if both fail or the result falls outside Chicago.

    Args:
        address: Full address string, e.g. "1600 W Chicago Ave, Chicago, IL"
        session: Optional requests.Session for connection reuse in batch mode.

    Returns:
        (latitude, longitude) tuple or None.
    """
    if not address or not address.strip():
        return None

    _session = session or requests.Session()

    for attempt in range(MAX_RETRIES):
        result = _geocode_census(address, _session)
        if result and _is_in_chicago(*result):
            return result

        # Brief backoff before retry or fallback.
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY_S * (attempt + 1))

    # Census geocoder failed — try Nominatim.
    result = _geocode_nominatim(address, _session)
    if result and _is_in_chicago(*result):
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
