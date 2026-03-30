"""
backend/app/routes/dashboard.py

Dashboard and shared address helper endpoints extracted from main.py:
  - GET /dashboard         — authenticated user dashboard
  - GET /dashboard/address — canonical address dashboard

Shared helpers also exported for use by other route modules:
  - _get_address_rows, _top_ranked_address_rows, _address_row_by_canonical_id
  - _address_row_by_coords, _haversine_meters, _normalize_address_text
  - _address_features, _query_features, _candidate_matches_query
  - _rank_address_candidate, _load_address_rows_from_db
  - _parse_nominatim, _parse_photon, _debug_search_flow
  - _get_projects_in_bbox, _NEIGHBORHOODS, _STATE_NAME_TO_ABBREV
  - _US_STATE_ABBREVS, _state_abbrev, _street_prefix, _DIRECTIONAL
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from backend.app.address_normalization import (
    DIRECTION_NORMALIZATION as _DIRECTION_NORMALIZATION,
    STREET_SUFFIX_NORMALIZATION as _STREET_SUFFIX_NORMALIZATION,
    build_address_search_tokens,
    format_display_address,
    normalize_address_query,
    normalize_address_record,
)
from backend.app.deps import _is_db_configured
from backend.app.services.livability import _extract_zip

log = logging.getLogger(__name__)
_DEBUG_SEARCH_FLOW_ENABLED = os.environ.get("DEBUG_SEARCH_FLOW", "").strip().lower() in {"1", "true", "yes", "on"}

router = APIRouter()


# ---------------------------------------------------------------------------
# Debug logging helper
# ---------------------------------------------------------------------------

def _debug_search_flow(stage: str, **payload) -> None:
    """Temporary structured debug logs for search/dashboard flow."""
    if not _DEBUG_SEARCH_FLOW_ENABLED:
        return
    log.info("[DBG:%s] %s", stage, payload)


# ---------------------------------------------------------------------------
# /suggest helper parsers (shared with search.py)
# ---------------------------------------------------------------------------

# US state name -> 2-letter abbreviation (for formatting nationwide suggestions)
_US_STATE_ABBREVS: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _state_abbrev(raw: str) -> str:
    """Return 2-letter state abbreviation from a full name or ISO code like 'US-IL'."""
    if not raw:
        return ""
    # ISO 3166-2 format: "US-IL" -> "IL"
    if "-" in raw:
        return raw.split("-")[-1].upper()
    return _US_STATE_ABBREVS.get(raw.lower().strip(), raw[:2].upper())


# Directional prefixes to strip when extracting the bare street-name fragment.
_DIRECTIONAL = re.compile(
    r"^(?:north|south|east|west|n\.?|s\.?|e\.?|w\.?)\s+",
    re.IGNORECASE,
)


def _street_prefix(query: str) -> str | None:
    """
    Extract the partial street-name fragment from a raw query so suggestions
    can be post-filtered to only streets whose name starts with that fragment.

    '679 North Peo'  -> 'peo'
    '100 W Rand'     -> 'rand'
    'Michigan Ave'   -> 'michigan'
    '1600 W Chicago' -> 'chicago'   (fragment long enough to be useful)
    """
    q = query.strip()
    # Drop trailing city/state suffixes the caller may have appended.
    q = re.sub(r",\s*[a-z][a-z\s]+,\s*[a-z]{2}\b.*$", "", q, flags=re.IGNORECASE)
    q = re.sub(r",\s*[a-z]{2}\b.*$", "", q, flags=re.IGNORECASE)
    # Drop leading house number.
    q = re.sub(r"^\d+\s*", "", q)
    # Drop directional prefix (North, S, W., etc.).
    q = _DIRECTIONAL.sub("", q).strip()
    # Only use the fragment if it's at least 2 chars (avoids over-filtering).
    return q.lower() if len(q) >= 2 else None


def _parse_nominatim(results: list, street_frag: str | None = None) -> list[str]:
    """Format Nominatim results as 'number road, City, ST' strings (any US state).

    If *street_frag* is given, only keep results whose road name starts with
    that fragment (case-insensitive). This prevents Nominatim from returning
    Milwaukee Ave when the user typed 'Peo' (-> Peoria).
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for r in results:
        addr = r.get("address", {})
        house = addr.get("house_number", "")
        road = addr.get("road") or addr.get("pedestrian") or addr.get("highway") or ""
        if not road:
            continue
        if street_frag and not road.lower().startswith(street_frag):
            continue
        city = addr.get("city") or addr.get("town") or addr.get("village") or ""
        # Nominatim returns ISO3166-2-lvl4 like "US-IL"; fall back to full state name.
        state_raw = addr.get("ISO3166-2-lvl4") or addr.get("state", "")
        state = _state_abbrev(state_raw)
        loc = f"{city}, {state}" if city and state else (city or state or "US")
        formatted = f"{house} {road}, {loc}" if house else f"{road}, {loc}"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


def _parse_photon(features: list, street_frag: str | None = None) -> list[str]:
    """Format Photon GeoJSON features as 'number road, City, ST' strings (any US state).

    If *street_frag* is given, only keep results whose street name starts with
    that fragment (case-insensitive).
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for f in features:
        props = f.get("properties", {})
        if props.get("countrycode", "").upper() != "US":
            continue
        street = props.get("street", "")
        if not street:
            continue
        if street_frag and not street.lower().startswith(street_frag):
            continue
        house = props.get("housenumber", "")
        city = props.get("city", "")
        state_raw = props.get("state", "")
        state = _state_abbrev(state_raw)
        loc = f"{city}, {state}" if city and state else (city or state or "US")
        formatted = f"{house} {street}, {loc}" if house else f"{street}, {loc}"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


# ---------------------------------------------------------------------------
# Address search data structures and helpers
# ---------------------------------------------------------------------------

_ADDRESS_SEARCH_CACHE_TTL_SEC = 60
_address_search_cache: dict[str, object] = {
    "loaded_at": 0.0,
    "rows": [],
}

_FALLBACK_ADDRESSES = [
    {"canonical_id": "addr_demo_1", "display_address": "1600 W Chicago Ave, Chicago, IL 60622", "lat": 41.8956, "lon": -87.6606},
    {"canonical_id": "addr_demo_2", "display_address": "700 W Grand Ave, Chicago, IL 60654", "lat": 41.8910, "lon": -87.6462},
    {"canonical_id": "addr_demo_3", "display_address": "233 S Wacker Dr, Chicago, IL 60606", "lat": 41.8788, "lon": -87.6359},
]

_STATE_NAME_TO_ABBREV = {
    "illinois": "IL",
    "indiana": "IN",
    "wisconsin": "WI",
}


def _normalize_address_text(raw: str) -> str:
    return normalize_address_query(raw)


def _address_features(display_address: str) -> dict:
    raw = (display_address or "").strip()
    base = normalize_address_record(raw)
    normalized_full = base["normalized_full"]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    street_raw = parts[0] if parts else raw
    city_raw = parts[1] if len(parts) >= 2 else ""
    state_zip_raw = parts[2] if len(parts) >= 3 else ""

    state_match = re.search(r"\b([A-Za-z]{2})\b", state_zip_raw)
    state_abbrev = state_match.group(1).upper() if state_match else _STATE_NAME_TO_ABBREV.get(_normalize_address_text(state_zip_raw), "")
    street_normalized = base["street"]
    city_normalized = base["city"]
    street_match = re.match(r"^(?P<number>\d+[a-z]?)\s+(?P<name>.+)$", street_normalized)
    street_number = street_match.group("number") if street_match else ""
    street_name = street_match.group("name").strip() if street_match else street_normalized
    number_street = f"{street_number} {street_name}".strip()
    city_state = _normalize_address_text(f"{city_raw} {state_abbrev}".strip())
    return {
        "normalized_full": normalized_full,
        "street_normalized": street_normalized,
        "street_number": street_number,
        "street_name": street_name,
        "number_street": number_street,
        "city_state": city_state,
        "city": city_raw,
        "city_normalized": city_normalized,
        "state": state_abbrev,
        "state_normalized": state_abbrev.lower(),
        "zip": _extract_zip(raw),
    }


def _query_features(query: str) -> dict:
    normalized = _normalize_address_text(query)
    parts = [p.strip() for p in query.split(",") if p.strip()]
    street_raw = parts[0] if parts else query
    street_normalized = _normalize_address_text(street_raw)
    street_match = re.match(r"^(?P<number>\d+[a-z]?)\s+(?P<name>.+)$", street_normalized)
    street_number = street_match.group("number") if street_match else ""
    street_name = street_match.group("name").strip() if street_match else street_normalized
    query_zip = _extract_zip(query or "")
    if query_zip and street_name == query_zip and not street_number:
        street_name = ""
    state_token = ""
    city_token = ""
    for token in normalized.split():
        if len(token) == 2 and token.isalpha():
            state_token = token
        elif token in _STATE_NAME_TO_ABBREV:
            state_token = _STATE_NAME_TO_ABBREV[token].lower()
        elif token.isalpha() and token not in _STREET_SUFFIX_NORMALIZATION and token not in _DIRECTION_NORMALIZATION:
            city_token = token if not city_token else city_token
    return {
        "normalized_full": normalized,
        "street_number": street_number,
        "street_name": street_name,
        "number_street": f"{street_number} {street_name}".strip(),
        "zip": query_zip,
        "city_token": city_token,
        "state_token": state_token,
        "tokens": build_address_search_tokens(normalized),
    }


def _candidate_matches_query(query_feats: dict, row: dict) -> bool:
    q_norm = query_feats["normalized_full"]
    if not q_norm:
        return True
    q_tokens = query_feats["tokens"]
    if not q_tokens:
        return True
    strong_match = (
        row["normalized_full"].startswith(q_norm)
        or (bool(query_feats["number_street"]) and row["number_street"].startswith(query_feats["number_street"]))
        or (bool(query_feats["street_name"]) and row["street_name"].startswith(query_feats["street_name"]))
        or (query_feats["zip"] and row.get("zip") == query_feats["zip"])
    )
    if query_feats["city_token"] and query_feats["city_token"] in row["city_normalized"]:
        strong_match = True
    if query_feats["state_token"] and query_feats["state_token"] == row.get("state_normalized"):
        strong_match = True
    if not strong_match:
        return False

    if query_feats["street_number"]:
        if not row["street_number"].startswith(query_feats["street_number"]):
            return False
    if query_feats["street_name"]:
        if not row["street_name"].startswith(query_feats["street_name"]):
            return False
    return all(token in row["normalized_full"] for token in q_tokens)


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points in meters."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _rank_address_candidate(query_feats: dict, row: dict, query_coords: tuple[float, float] | None = None) -> tuple:
    q_norm = query_feats["normalized_full"]
    q_number_street = query_feats["number_street"]
    q_street_name = query_feats["street_name"]
    q_zip = query_feats["zip"]
    q_city = query_feats["city_token"]
    q_state = query_feats["state_token"]

    exact_full = int(bool(q_norm) and row["normalized_full"] == q_norm)
    prefix_full = int(bool(q_norm) and row["normalized_full"].startswith(q_norm))
    exact_number_street = int(bool(q_number_street) and row["number_street"] == q_number_street)
    prefix_number_street = int(bool(q_number_street) and row["number_street"].startswith(q_number_street))
    prefix_street_name = int(bool(q_street_name) and row["street_name"].startswith(q_street_name))
    city_alignment = int(bool(q_city) and q_city in row["city_normalized"])
    state_alignment = int(bool(q_state) and q_state == row.get("state_normalized"))
    zip_alignment = int(bool(q_zip) and q_zip == row.get("zip"))
    weak_token_penalty = -sum(1 for t in query_feats["tokens"] if t not in row["normalized_full"])
    length_penalty = abs(len(row["normalized_full"]) - len(q_norm))
    popularity = int(row.get("popularity", 0))
    geo_penalty = 0
    if query_coords and row.get("lat") is not None and row.get("lon") is not None:
        dist_m = _haversine_meters(query_coords[0], query_coords[1], float(row["lat"]), float(row["lon"]))
        # Penalize distant candidates in 25km bands. Close matches keep zero penalty.
        geo_penalty = -int(dist_m // 25000)

    return (
        exact_full,
        prefix_full,
        exact_number_street,
        prefix_number_street,
        prefix_street_name,
        city_alignment,
        state_alignment,
        zip_alignment,
        weak_token_penalty,
        geo_penalty,
        -length_penalty,
        popularity,
    )


def _top_ranked_address_rows(query: str, rows: list[dict], limit: int, with_geo_penalty: bool = False) -> list[dict]:
    if not rows:
        return []
    query_feats = _query_features(query)
    query_coords: tuple[float, float] | None = None
    if with_geo_penalty and bool(re.search(r"\d", query)) and len(query.strip()) >= 8:
        try:
            from backend.ingest.geocode import geocode_address
            query_coords = geocode_address(query, statewide=True)
        except Exception:
            query_coords = None
    filtered = [row for row in rows if _candidate_matches_query(query_feats, row)]
    ranked = sorted(filtered, key=lambda r: _rank_address_candidate(query_feats, r, query_coords), reverse=True)
    return ranked[:limit]


def _load_address_rows_from_db() -> list[dict]:
    from backend.scoring.query import get_db_connection

    conn = get_db_connection()
    try:
        rows: list[tuple[str, Optional[float], Optional[float], int]] = []
        with conn.cursor() as cur:
            for sql in (
                """
                SELECT address,
                       NULLIF(score_json->>'latitude', '')::double precision AS lat,
                       NULLIF(score_json->>'longitude', '')::double precision AS lon,
                       COUNT(*)::int AS popularity
                FROM reports
                WHERE address IS NOT NULL AND address <> ''
                GROUP BY address, lat, lon
                """,
                """
                SELECT address, NULL::double precision AS lat, NULL::double precision AS lon, COUNT(*)::int AS popularity
                FROM watchlist
                WHERE address IS NOT NULL AND address <> ''
                GROUP BY address
                """,
                """
                SELECT address, NULL::double precision AS lat, NULL::double precision AS lon, COUNT(*)::int AS popularity
                FROM score_history
                WHERE address IS NOT NULL AND address <> ''
                GROUP BY address
                """,
            ):
                try:
                    cur.execute(sql)
                    rows.extend(cur.fetchall())
                except Exception:
                    conn.rollback()
                    continue

        by_norm: dict[str, dict] = {}
        for address, lat, lon, popularity in rows:
            display = address.strip()
            if not display:
                continue
            feats = _address_features(display)
            norm = feats["normalized_full"]
            if not norm:
                continue
            existing = by_norm.get(norm)
            if existing is None:
                canonical_id = f"addr_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]}"
                by_norm[norm] = {
                    "canonical_id": canonical_id,
                    "display_address": display,
                    "lat": lat,
                    "lon": lon,
                    "popularity": int(popularity or 0),
                    **feats,
                }
            else:
                existing["popularity"] += int(popularity or 0)
                if existing.get("lat") is None and lat is not None:
                    existing["lat"] = lat
                if existing.get("lon") is None and lon is not None:
                    existing["lon"] = lon
        return list(by_norm.values())
    finally:
        conn.close()


def _get_address_rows() -> list[dict]:
    now = time.time()
    cached_at = float(_address_search_cache.get("loaded_at", 0.0))
    cached_rows = _address_search_cache.get("rows", [])
    if (now - cached_at) < _ADDRESS_SEARCH_CACHE_TTL_SEC and isinstance(cached_rows, list):
        return cached_rows

    if not _is_db_configured():
        rows = [
            {
                **entry,
                "popularity": 1,
                **_address_features(entry["display_address"]),
            }
            for entry in _FALLBACK_ADDRESSES
        ]
        _address_search_cache["loaded_at"] = now
        _address_search_cache["rows"] = rows
        return rows

    try:
        rows = _load_address_rows_from_db()
    except Exception as exc:
        log.warning("address search dataset load failed: %s", exc)
        rows = [
            {
                **entry,
                "popularity": 1,
                **_address_features(entry["display_address"]),
            }
            for entry in _FALLBACK_ADDRESSES
        ]

    _address_search_cache["loaded_at"] = now
    _address_search_cache["rows"] = rows
    return rows


def _address_row_by_canonical_id(canonical_id: str) -> dict | None:
    if not canonical_id:
        return None
    for row in _get_address_rows():
        if row.get("canonical_id") == canonical_id:
            return row
    return None


def _address_row_by_coords(lat: float, lon: float, max_distance_m: float = 1500.0) -> dict | None:
    """Find nearest canonical address row for fallback resolution."""
    best_row: dict | None = None
    best_dist: float | None = None
    for row in _get_address_rows():
        row_lat = row.get("lat")
        row_lon = row.get("lon")
        if row_lat is None or row_lon is None:
            continue
        dist = _haversine_meters(float(lat), float(lon), float(row_lat), float(row_lon))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_row = row
    if best_row is None or best_dist is None or best_dist > max_distance_m:
        return None
    return best_row


# ---------------------------------------------------------------------------
# Neighborhoods data (shared with neighborhood.py and map.py)
# ---------------------------------------------------------------------------

_NEIGHBORHOODS: dict[str, dict] = {
    "wicker-park": {
        "name": "Wicker Park",
        "description": "Dense mixed-use neighborhood with high permit activity along Milwaukee Ave.",
        "center": {"lat": 41.9088, "lon": -87.6776},
        "bbox": {"min_lat": 41.8990, "min_lon": -87.6950, "max_lat": 41.9180, "max_lon": -87.6600},
        "median_score": 42,
    },
    "logan-square": {
        "name": "Logan Square",
        "description": "Rapidly developing neighborhood with significant construction along the 606 trail corridor.",
        "center": {"lat": 41.9217, "lon": -87.7082},
        "bbox": {"min_lat": 41.9100, "min_lon": -87.7250, "max_lat": 41.9330, "max_lon": -87.6900},
        "median_score": 38,
    },
    "river-north": {
        "name": "River North",
        "description": "High-density commercial and residential construction zone north of the Chicago River.",
        "center": {"lat": 41.8940, "lon": -87.6340},
        "bbox": {"min_lat": 41.8850, "min_lon": -87.6500, "max_lat": 41.9030, "max_lon": -87.6200},
        "median_score": 51,
    },
    "lincoln-park": {
        "name": "Lincoln Park",
        "description": "Affluent lakefront neighborhood with ongoing street and utility work.",
        "center": {"lat": 41.9240, "lon": -87.6450},
        "bbox": {"min_lat": 41.9100, "min_lon": -87.6630, "max_lat": 41.9380, "max_lon": -87.6270},
        "median_score": 29,
    },
    "pilsen": {
        "name": "Pilsen",
        "description": "Arts and manufacturing district with active infrastructure upgrades.",
        "center": {"lat": 41.8560, "lon": -87.6640},
        "bbox": {"min_lat": 41.8470, "min_lon": -87.6850, "max_lat": 41.8650, "max_lon": -87.6430},
        "median_score": 35,
    },
    "loop": {
        "name": "The Loop",
        "description": "Chicago's downtown core with continuous street closure and utility activity.",
        "center": {"lat": 41.8827, "lon": -87.6323},
        "bbox": {"min_lat": 41.8740, "min_lon": -87.6480, "max_lat": 41.8920, "max_lon": -87.6180},
        "median_score": 58,
    },
    "uptown": {
        "name": "Uptown",
        "description": "Dense lakeside neighborhood undergoing significant transit corridor improvements.",
        "center": {"lat": 41.9650, "lon": -87.6540},
        "bbox": {"min_lat": 41.9540, "min_lon": -87.6680, "max_lat": 41.9750, "max_lon": -87.6390},
        "median_score": 33,
    },
    "bridgeport": {
        "name": "Bridgeport",
        "description": "South Side industrial-residential neighborhood with ongoing utility and road work.",
        "center": {"lat": 41.8350, "lon": -87.6444},
        "bbox": {"min_lat": 41.8250, "min_lon": -87.6600, "max_lat": 41.8460, "max_lon": -87.6300},
        "median_score": 27,
    },
    "old-town": {
        "name": "Old Town",
        "description": "Historic entertainment and residential corridor with steady permit activity near Wells St.",
        "center": {"lat": 41.9095, "lon": -87.6373},
        "bbox": {"min_lat": 41.9010, "min_lon": -87.6490, "max_lat": 41.9180, "max_lon": -87.6260},
        "median_score": 31,
    },
    "gold-coast": {
        "name": "Gold Coast",
        "description": "Luxury lakefront neighborhood with periodic utility and streetscape work along Lake Shore Dr.",
        "center": {"lat": 41.9026, "lon": -87.6289},
        "bbox": {"min_lat": 41.8940, "min_lon": -87.6400, "max_lat": 41.9110, "max_lon": -87.6170},
        "median_score": 24,
    },
    "streeterville": {
        "name": "Streeterville",
        "description": "Dense lakefront district with hospital campus construction and ongoing utility upgrades.",
        "center": {"lat": 41.8920, "lon": -87.6180},
        "bbox": {"min_lat": 41.8840, "min_lon": -87.6270, "max_lat": 41.9000, "max_lon": -87.6080},
        "median_score": 44,
    },
    "south-loop": {
        "name": "South Loop",
        "description": "Fast-growing residential district with significant high-rise construction along Michigan Ave.",
        "center": {"lat": 41.8680, "lon": -87.6280},
        "bbox": {"min_lat": 41.8590, "min_lon": -87.6430, "max_lat": 41.8770, "max_lon": -87.6140},
        "median_score": 47,
    },
    "andersonville": {
        "name": "Andersonville",
        "description": "North Side commercial corridor with active sewer and streetscape improvements along Clark St.",
        "center": {"lat": 41.9810, "lon": -87.6580},
        "bbox": {"min_lat": 41.9730, "min_lon": -87.6700, "max_lat": 41.9890, "max_lon": -87.6450},
        "median_score": 28,
    },
    "rogers-park": {
        "name": "Rogers Park",
        "description": "Diverse lakefront neighborhood at Chicago's northern edge with periodic utility work.",
        "center": {"lat": 42.0030, "lon": -87.6690},
        "bbox": {"min_lat": 41.9940, "min_lon": -87.6810, "max_lat": 42.0120, "max_lon": -87.6550},
        "median_score": 22,
    },
    "bucktown": {
        "name": "Bucktown",
        "description": "Trendy residential neighborhood with active construction on 606 trail corridor and Damen Ave.",
        "center": {"lat": 41.9170, "lon": -87.6850},
        "bbox": {"min_lat": 41.9090, "min_lon": -87.6980, "max_lat": 41.9260, "max_lon": -87.6720},
        "median_score": 39,
    },
    "ukrainian-village": {
        "name": "Ukrainian Village",
        "description": "Quiet residential grid with intermittent water main and alley repaving activity.",
        "center": {"lat": 41.8950, "lon": -87.6750},
        "bbox": {"min_lat": 41.8870, "min_lon": -87.6870, "max_lat": 41.9030, "max_lon": -87.6620},
        "median_score": 19,
    },
    "humboldt-park": {
        "name": "Humboldt Park",
        "description": "West Side neighborhood with infrastructure investment and road resurfacing along Pulaski Rd.",
        "center": {"lat": 41.9000, "lon": -87.7220},
        "bbox": {"min_lat": 41.8910, "min_lon": -87.7380, "max_lat": 41.9090, "max_lon": -87.7060},
        "median_score": 30,
    },
    "hyde-park": {
        "name": "Hyde Park",
        "description": "University district on the South Side with campus-driven construction and ongoing transit work.",
        "center": {"lat": 41.7950, "lon": -87.5950},
        "bbox": {"min_lat": 41.7840, "min_lon": -87.6090, "max_lat": 41.8060, "max_lon": -87.5810},
        "median_score": 26,
    },
    "ravenswood": {
        "name": "Ravenswood",
        "description": "North Side residential neighborhood with rail corridor activity and Metra track work.",
        "center": {"lat": 41.9700, "lon": -87.6740},
        "bbox": {"min_lat": 41.9620, "min_lon": -87.6860, "max_lat": 41.9790, "max_lon": -87.6610},
        "median_score": 25,
    },
    "avondale": {
        "name": "Avondale",
        "description": "Northwest Side neighborhood with light industrial activity and sewer infrastructure work.",
        "center": {"lat": 41.9450, "lon": -87.7100},
        "bbox": {"min_lat": 41.9360, "min_lon": -87.7230, "max_lat": 41.9540, "max_lon": -87.6970},
        "median_score": 32,
    },
}


def _get_projects_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[dict]:
    """
    Query active projects within a bounding box from the canonical projects table.

    Uses the same PostGIS geom index as the /score endpoint (ST_Within +
    ST_MakeEnvelope) so rows with a NULL latitude/longitude but a valid geom
    are still returned.  Coordinates are extracted from the geometry via
    ST_Y/ST_X and fall back to the stored latitude/longitude columns so both
    legacy and new rows are handled correctly.

    Returns a list of JSON-serializable project dicts.
    Falls back to an empty list when DB is not configured or on any error.
    """
    if not _is_db_configured():
        return []
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        project_id,
                        source,
                        impact_type,
                        title,
                        start_date,
                        end_date,
                        status,
                        COALESCE(ST_Y(geom), latitude)  AS lat,
                        COALESCE(ST_X(geom), longitude) AS lon
                    FROM projects
                    WHERE status IN ('active', 'planned')
                      AND geom IS NOT NULL
                      AND ST_Within(
                          geom,
                          ST_MakeEnvelope(%s, %s, %s, %s, 4326)
                      )
                    ORDER BY start_date DESC NULLS LAST
                    LIMIT 200
                    """,
                    (min_lon, min_lat, max_lon, max_lat),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        projects = []
        for row in rows:
            project_id, source, impact_type, title, start_date, end_date, status, lat, lon = row
            projects.append({
                "project_id": project_id,
                "source": source,
                "impact_type": impact_type,
                "title": title,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "status": status,
                "lat": float(lat) if lat is not None else None,
                "lon": float(lon) if lon is not None else None,
            })
        return projects
    except Exception as exc:
        log.error("neighborhood bbox query error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# GET /dashboard/address endpoint
# ---------------------------------------------------------------------------

@router.get("/dashboard/address")
def get_dashboard_for_address(
    canonical_id: str | None = Query(None, description="Canonical address identifier from /suggest"),
    lat: float | None = Query(None, description="Latitude fallback from selected suggestion"),
    lon: float | None = Query(None, description="Longitude fallback from selected suggestion"),
    address: str | None = Query(None, description="Display address fallback label"),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    row = _address_row_by_canonical_id(canonical_id or "") if canonical_id else None
    resolution_source = "canonical_id"
    if not row and lat is not None and lon is not None:
        row = _address_row_by_coords(lat, lon)
        resolution_source = "lat_lon" if row else "lat_lon_unmatched"
    if not row:
        _debug_search_flow(
            "ADDRESS_DASHBOARD_RESOLUTION",
            canonical_id=canonical_id,
            lat=lat,
            lon=lon,
            available=False,
            status="unsupported",
            reason="not_found",
        )
        return {
            "status": "unsupported",
            "available": False,
            "canonical_id": canonical_id,
            "reason": "not_found",
            "address": {
                "display_address": address,
                "city": None,
                "state": None,
                "zip": None,
                "lat": lat,
                "lon": lon,
            } if address or (lat is not None and lon is not None) else None,
            "location_summary": {
                "display_address": address,
                "city": None,
                "state": None,
                "zip": None,
                "lat": lat,
                "lon": lon,
                "resolution_source": resolution_source,
            },
            "score_summary": None,
            "modules_unavailable": ["history", "dashboard"],
            "history": [],
        }

    if not _is_db_configured():
        _debug_search_flow(
            "ADDRESS_DASHBOARD_RESOLUTION",
            canonical_id=row.get("canonical_id"),
            available=False,
            status="partial",
            reason="db_not_configured",
            resolution_source=resolution_source,
        )
        return {
            "status": "partial",
            "available": False,
            "canonical_id": row.get("canonical_id"),
            "reason": "db_not_configured",
            "address": {
                "display_address": row["display_address"],
                "city": row.get("city"),
                "state": row.get("state"),
                "zip": row.get("zip"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
            },
            "location_summary": {
                "display_address": row["display_address"],
                "city": row.get("city"),
                "state": row.get("state"),
                "zip": row.get("zip"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "resolution_source": resolution_source,
            },
            "score_summary": None,
            "modules_unavailable": ["history", "dashboard"],
            "history": [],
        }

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT disruption_score, livability_score, confidence, mode, scored_at
                    FROM score_history
                    WHERE regexp_replace(lower(address), '\\s+', ' ', 'g') = %s
                    ORDER BY scored_at DESC
                    LIMIT %s
                    """,
                    (row["normalized_full"], limit),
                )
                history_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT disruption_score, livability_score, confidence, mode, scored_at
                    FROM score_history
                    WHERE regexp_replace(lower(address), '\\s+', ' ', 'g') = %s
                    ORDER BY scored_at DESC
                    LIMIT 1
                    """,
                    (row["normalized_full"],),
                )
                latest_row = cur.fetchone()
        finally:
            conn.close()

        history = [
            {
                "disruption_score": r[0],
                "livability_score": r[1],
                "confidence": r[2],
                "mode": r[3],
                "scored_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
            }
            for r in history_rows
        ]
        available = len(history) > 0
        status = "full" if available else "partial"
        modules_unavailable = [] if available else ["history"]
        score_summary = (
            {
                "disruption_score": latest_row[0],
                "livability_score": latest_row[1],
                "confidence": latest_row[2],
                "mode": latest_row[3],
                "scored_at": latest_row[4].isoformat() if hasattr(latest_row[4], "isoformat") else str(latest_row[4]),
            }
            if latest_row
            else None
        )
        _debug_search_flow(
            "ADDRESS_DASHBOARD_RESOLUTION",
            canonical_id=row.get("canonical_id"),
            available=available,
            status=status,
            resolution_source=resolution_source,
            matched_display_address=row["display_address"],
            history_count=len(history),
        )
        return {
            "status": status,
            "available": available,
            "canonical_id": row.get("canonical_id"),
            "reason": None if available else "no_backend_record",
            "address": {
                "display_address": row["display_address"],
                "city": row.get("city"),
                "state": row.get("state"),
                "zip": row.get("zip"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
            },
            "location_summary": {
                "display_address": row["display_address"],
                "city": row.get("city"),
                "state": row.get("state"),
                "zip": row.get("zip"),
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "resolution_source": resolution_source,
            },
            "score_summary": score_summary,
            "modules_unavailable": modules_unavailable,
            "history": history,
        }
    except Exception as exc:
        _debug_search_flow(
            "ADDRESS_DASHBOARD_RESOLUTION",
            canonical_id=canonical_id,
            lat=lat,
            lon=lon,
            available=False,
            status="partial",
            reason="error",
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Could not load canonical address dashboard data.") from exc


# ---------------------------------------------------------------------------
# GET /dashboard endpoint
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_dashboard(authorization: str = Header(default=None)) -> dict:
    from backend.app.auth import get_current_user
    from backend.scoring.query import get_db_connection

    user = get_current_user(authorization)
    account_id = int(user["sub"])
    _debug_search_flow(
        "DASHBOARD_RESOLVER_INBOUND",
        account_id=account_id,
        identifier_type="account_id",
    )

    if not _is_db_configured():
        return {"saved_reports": [], "watchlist": []}

    try:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                # Saved reports (last 10) filtered by account_id stored in score_json.
                cur.execute(
                    """
                    SELECT id, address, score_json, created_at
                    FROM reports
                    WHERE (score_json->>'account_id') = %s
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    (str(account_id),),
                )
                report_rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT id, address, threshold_score, created_at
                    FROM watchlist
                    WHERE account_id = %s AND is_active = true
                    ORDER BY created_at DESC
                    """,
                    (account_id,),
                )
                watch_rows = cur.fetchall()
                _debug_search_flow(
                    "DASHBOARD_RESOLVER_MATCH",
                    account_id=account_id,
                    saved_report_rows=len(report_rows),
                    watch_rows=len(watch_rows),
                )
        finally:
            conn.close()

        saved_reports = []
        saved_report_by_key: dict[str, dict] = {}
        for rid, address, score_json, created_at in report_rows:
            canonical_key = _normalize_address_text(address)
            report_entry = {
                "report_id": str(rid),
                "address": address,
                "saved_disruption_score": score_json.get("disruption_score"),
                "saved_livability_score": score_json.get("livability_score"),
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            }
            saved_reports.append(report_entry)
            saved_report_by_key[canonical_key] = report_entry

        watch_items = []
        for wid, address, threshold_score, created_at in watch_rows:
            current = None
            diff = None
            try:
                from backend.app.routes.score import _score_live
                current_result = _score_live(address)
                current = current_result.get("livability_score")
            except Exception:
                current = None

            watch_key = _normalize_address_text(address)
            saved_match = saved_report_by_key.get(watch_key)
            if saved_match and saved_match.get("saved_livability_score") is not None and current is not None:
                diff = int(current) - int(saved_match["saved_livability_score"])
            elif saved_match is None:
                _debug_search_flow(
                    "DASHBOARD_RESOLVER_JOIN_FAIL",
                    account_id=account_id,
                    watchlist_id=wid,
                    join_key="normalized_canonical_key",
                    inbound_identifier=watch_key,
                    matched_record=None,
                )

            watch_items.append(
                {
                    "id": wid,
                    "address": address,
                    "threshold": threshold_score,
                    "current_livability_score": current,
                    "score_diff_since_saved": diff,
                    "score_changed": diff is not None and diff != 0,
                    "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
                }
            )

        _debug_search_flow(
            "DASHBOARD_RESOLVER_FINAL",
            account_id=account_id,
            saved_reports=len(saved_reports),
            watch_items=len(watch_items),
        )
        return {"saved_reports": saved_reports, "watchlist": watch_items}
    except Exception as exc:
        log.error("dashboard error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not load dashboard.") from exc
