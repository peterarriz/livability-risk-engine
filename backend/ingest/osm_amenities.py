"""
backend/ingest/osm_amenities.py
task: data-064
lane: data

Fetches walkable amenities near a lat/lon from the OpenStreetMap Overpass API
and computes an amenity richness score (0–100).

No API key required. Uses the public Overpass API endpoint.

Categories and scoring:
  transit    highway=bus_stop | railway=station|subway_entrance   ≤400m → 25 pts
  grocery    shop=supermarket|grocery|convenience|food            ≤500m → 25 pts
  park       leisure=park|playground|garden                       ≤600m → 20 pts
  restaurant amenity=restaurant|cafe|fast_food|bar                ≤400m → 15 pts
  pharmacy   amenity=pharmacy                                     ≤600m → 15 pts

Usage:
  python backend/ingest/osm_amenities.py --lat 41.8956 --lon -87.6606
  python backend/ingest/osm_amenities.py --lat 41.8956 --lon -87.6606 --dry-run
"""

from __future__ import annotations

import argparse
import json
import math
import time
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_RADIUS_M = 800      # outer bounding radius for the Overpass query
REQUEST_TIMEOUT_S = 20      # seconds before giving up on Overpass

# Per-category OSM tag filters and scoring thresholds
CATEGORIES: dict[str, dict] = {
    "transit": {
        "filters": [
            '["highway"="bus_stop"]',
            '["railway"~"station|subway_entrance"]',
            '["public_transport"="stop_position"]["name"]',
        ],
        "threshold_m": 400,
        "score": 25,
        "label": "Transit",
    },
    "grocery": {
        "filters": [
            '["shop"~"supermarket|grocery|convenience|food"]',
        ],
        "threshold_m": 500,
        "score": 25,
        "label": "Grocery",
    },
    "park": {
        "filters": [
            '["leisure"~"park|playground|garden"]',
        ],
        "threshold_m": 600,
        "score": 20,
        "label": "Park",
    },
    "restaurant": {
        "filters": [
            '["amenity"~"restaurant|cafe|fast_food|bar"]',
        ],
        "threshold_m": 400,
        "score": 15,
        "label": "Restaurant / Cafe",
    },
    "pharmacy": {
        "filters": [
            '["amenity"="pharmacy"]',
        ],
        "threshold_m": 600,
        "score": 15,
        "label": "Pharmacy",
    },
}

MAX_RESULTS_PER_CATEGORY = 5  # return at most this many per category


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two WGS-84 points."""
    r = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build an Overpass QL query for all amenity categories."""
    parts = []
    for cat in CATEGORIES.values():
        for f in cat["filters"]:
            parts.append(f'  node{f}(around:{radius_m},{lat},{lon});')
            parts.append(f'  way{f}(around:{radius_m},{lat},{lon});')
    body = "\n".join(parts)
    return f"[out:json][timeout:{REQUEST_TIMEOUT_S}];\n(\n{body}\n);\nout center;"


def _classify_element(element: dict[str, Any]) -> str | None:
    """Return the category key for an OSM element, or None if uncategorised."""
    tags: dict = element.get("tags") or {}
    highway = tags.get("highway", "")
    railway = tags.get("railway", "")
    pt = tags.get("public_transport", "")
    shop = tags.get("shop", "")
    leisure = tags.get("leisure", "")
    amenity = tags.get("amenity", "")

    if highway == "bus_stop" or railway in ("station", "subway_entrance") or pt == "stop_position":
        return "transit"
    if shop in ("supermarket", "grocery", "convenience", "food"):
        return "grocery"
    if leisure in ("park", "playground", "garden"):
        return "park"
    if amenity in ("restaurant", "cafe", "fast_food", "bar"):
        return "restaurant"
    if amenity == "pharmacy":
        return "pharmacy"
    return None


def _element_latlon(element: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from a node or way-with-center element."""
    if element.get("type") == "node":
        return element.get("lat"), element.get("lon")
    center = element.get("center")
    if center:
        return center.get("lat"), center.get("lon")
    return None


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def fetch_amenities(
    lat: float,
    lon: float,
    radius_m: int = DEFAULT_RADIUS_M,
) -> dict:
    """
    Query Overpass for amenities near (lat, lon) and return:
      {
        "amenity_score": 75,
        "categories": {
          "transit":    [{"name": "...", "lat": ..., "lon": ..., "distance_m": 210, "category": "transit"}, ...],
          "grocery":    [...],
          "park":       [...],
          "restaurant": [...],
          "pharmacy":   [...],
        }
      }

    Raises requests.RequestException on network failure so the caller can
    decide whether to fall back gracefully.
    """
    query = _build_overpass_query(lat, lon, radius_m)
    resp = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=REQUEST_TIMEOUT_S,
        headers={"User-Agent": "livability-risk-engine/1.0 (data-064)"},
    )
    resp.raise_for_status()
    elements: list[dict] = resp.json().get("elements", [])

    # Bucket results by category, compute distance, sort by proximity.
    buckets: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}

    seen_ids: set = set()
    for el in elements:
        osm_id = el.get("id")
        if osm_id in seen_ids:
            continue
        seen_ids.add(osm_id)

        category = _classify_element(el)
        if category is None:
            continue

        coords = _element_latlon(el)
        if coords is None or None in coords:
            continue

        el_lat, el_lon = coords
        dist = _haversine_m(lat, lon, el_lat, el_lon)

        tags = el.get("tags") or {}
        name = (
            tags.get("name")
            or tags.get("name:en")
            or CATEGORIES[category]["label"]
        )

        buckets[category].append({
            "name": name,
            "lat": round(el_lat, 6),
            "lon": round(el_lon, 6),
            "distance_m": round(dist),
            "category": category,
        })

    # Sort each category by distance, keep closest MAX_RESULTS_PER_CATEGORY.
    for cat in buckets:
        buckets[cat].sort(key=lambda x: x["distance_m"])
        buckets[cat] = buckets[cat][:MAX_RESULTS_PER_CATEGORY]

    # Compute score: points for each category that has ≥1 result within threshold.
    score = 0
    for cat_key, cfg in CATEGORIES.items():
        threshold = cfg["threshold_m"]
        within = [a for a in buckets[cat_key] if a["distance_m"] <= threshold]
        if within:
            score += cfg["score"]

    return {"amenity_score": score, "categories": buckets}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OSM amenities near a point.")
    parser.add_argument("--lat",     type=float, default=41.8956, help="Latitude")
    parser.add_argument("--lon",     type=float, default=-87.6606, help="Longitude")
    parser.add_argument("--radius",  type=int,   default=DEFAULT_RADIUS_M, help="Radius in metres")
    parser.add_argument("--dry-run", action="store_true", help="Print result without storing")
    args = parser.parse_args()

    print(f"Querying Overpass for amenities near {args.lat}, {args.lon} (radius={args.radius}m)...")
    t0 = time.time()
    result = fetch_amenities(args.lat, args.lon, args.radius)
    elapsed = time.time() - t0

    print(f"Done in {elapsed:.1f}s  |  amenity_score={result['amenity_score']}")
    for cat, items in result["categories"].items():
        cfg = CATEGORIES[cat]
        within = [a for a in items if a["distance_m"] <= cfg["threshold_m"]]
        print(f"  {cat:12s} ({len(items)} found, {len(within)} within {cfg['threshold_m']}m)")
        for a in items[:3]:
            print(f"    {a['distance_m']:4d}m  {a['name']}")
    if args.dry_run:
        print("\n[dry-run] Result not stored.")
    else:
        print(json.dumps(result, indent=2))
