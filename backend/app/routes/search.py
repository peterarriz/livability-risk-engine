"""
backend/app/routes/search.py

Search-related endpoints extracted from main.py:
  - GET /addresses/search  — address autocomplete for the search bar
  - GET /suggest           — unified address suggestion with geocoder fallback
"""

import logging
import re

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

router = APIRouter()

_STREET_QUERY_TERMS = {
    "ave", "avenue", "st", "street", "rd", "road", "dr", "drive",
    "blvd", "boulevard", "ln", "lane", "way", "pl", "place",
    "ct", "court", "pkwy", "parkway", "hwy", "highway", "terrace", "ter",
}


def _suggestion_from_row(row: dict) -> dict:
    return {
        "canonical_id": row.get("canonical_id"),
        "display_address": row["display_address"],
        "lat": row.get("lat"),
        "lon": row.get("lon"),
        "city": row.get("city"),
        "state": row.get("state"),
        "zip": row.get("zip"),
    }


def _numeric_prefix_rows(query: str, rows: list[dict], limit: int) -> list[dict]:
    q = query.strip().lower()
    if not re.fullmatch(r"\d+[a-z]?", q):
        return []
    matches = [row for row in rows if str(row.get("street_number", "")).lower().startswith(q)]
    return sorted(matches, key=lambda r: int(r.get("popularity", 0)), reverse=True)[:limit]


def _city_prefix_rows(query: str, rows: list[dict], limit: int) -> list[dict]:
    q = re.sub(r"[^a-z]", "", query.strip().lower())
    if len(q) < 3:
        return []
    matches = [
        row for row in rows
        if str(row.get("city_normalized", "")).startswith(q)
        or q in str(row.get("city_normalized", ""))
    ]
    return sorted(matches, key=lambda r: int(r.get("popularity", 0)), reverse=True)[:limit]


def _looks_like_external_address_query(query: str) -> bool:
    """Allow geocoder fallback only for full-ish typed addresses, not prefixes."""
    q = query.strip().lower()
    if len(q) < 12:
        return False
    if not re.search(r"\d", q) or not re.search(r"[a-z]", q):
        return False
    if re.fullmatch(r"\d+[a-z]?", q):
        return False
    tokens = re.findall(r"[a-z0-9]+", q)
    has_street_term = any(token in _STREET_QUERY_TERMS for token in tokens)
    has_context = "," in query or any(len(token) == 2 and token.isalpha() for token in tokens)
    return has_street_term or has_context


def _rows_from_nominatim(query: str, limit: int) -> list[dict]:
    """Fallback suggestions from geocoder when curated rows have no strong results."""
    import requests as _requests
    from backend.app.routes.dashboard import _state_abbrev, _address_features
    from backend.app.address_normalization import format_display_address
    from backend.app.services.livability import _extract_zip

    _nom_headers = {"User-Agent": "LivabilityRiskEngine/1.0 (us-mvp)"}
    try:
        resp = _requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": max(6, limit),
                "countrycodes": "us",
                "addressdetails": "1",
            },
            headers=_nom_headers,
            timeout=2.5,
        )
        if not resp.ok:
            return []
        by_norm: dict[str, dict] = {}
        for row in resp.json():
            address = row.get("address", {}) if isinstance(row, dict) else {}
            house = address.get("house_number", "")
            road = address.get("road", "") or address.get("pedestrian", "")
            city = address.get("city") or address.get("town") or address.get("village") or ""
            state = _state_abbrev(address.get("state") or address.get("ISO3166-2-lvl4") or "")
            if not road:
                continue
            display = format_display_address(
                f"{house} {road}".strip(),
                city,
                state,
                _extract_zip(str(row.get("display_name", ""))),
            )
            features = _address_features(display)
            norm = features["normalized_full"]
            if not norm:
                continue
            if norm in by_norm:
                continue
            by_norm[norm] = {
                "canonical_id": None,
                "display_address": display,
                "lat": float(row.get("lat")) if row.get("lat") is not None else None,
                "lon": float(row.get("lon")) if row.get("lon") is not None else None,
                "popularity": 0,
                **features,
            }
        return list(by_norm.values())
    except Exception:
        return []


@router.get("/addresses/search")
def search_addresses(
    q: str = Query("", description="Partial address query"),
    limit: int = Query(8, ge=1, le=8, description="Maximum results to return"),
    popular: bool = Query(False, description="Return popular recent addresses when query is empty"),
) -> dict:
    from backend.app.routes.dashboard import (
        _get_address_rows,
        _top_ranked_address_rows,
        _debug_search_flow,
    )

    query = q.strip()
    if len(query) < 3 and not popular:
        return {"query": query, "suggestions": []}

    rows = _get_address_rows()
    if not rows:
        return {"query": query, "suggestions": []}

    if popular and not query:
        top = sorted(rows, key=lambda r: int(r.get("popularity", 0)), reverse=True)[:limit]
    else:
        top = _top_ranked_address_rows(query, rows, limit, with_geo_penalty=False)

    suggestions = [
        {
            "canonical_id": row.get("canonical_id"),
            "display_address": row["display_address"],
            "city": row.get("city"),
            "state": row.get("state"),
            "zip": row.get("zip"),
            "lat": row.get("lat"),
            "lon": row.get("lon"),
        }
        for row in top
    ]
    _debug_search_flow(
        "ADDRESS_SEARCH_RESPONSE",
        query=query,
        popular=popular,
        candidate_count=len(rows),
        returned=len(suggestions),
        top=[s["display_address"] for s in suggestions[:3]],
    )
    return {"query": query, "suggestions": suggestions}


@router.get("/suggest")
def suggest_addresses(
    q: str = Query("", description="Partial US address query"),
    limit: int = Query(8, ge=1, le=8, description="Maximum results to return"),
    popular: bool = Query(False, description="Return popular addresses when query is short or empty"),
) -> dict:
    from backend.app.routes.dashboard import (
        _get_address_rows,
        _top_ranked_address_rows,
        _debug_search_flow,
    )

    query = q.strip()

    rows = _get_address_rows()

    # For empty/short queries, avoid open-ended geocoder or fuzzy matches.
    # Public autocomplete should not show odd guesses for one- or two-letter input.
    if len(query) < 3:
        if not popular:
            return {"query": query, "suggestions": []}
        top = sorted(rows, key=lambda r: int(r.get("popularity", 0)), reverse=True)[:limit]
        return {
            "query": query,
            "suggestions": [
                _suggestion_from_row(row)
                for row in top
                if row.get("display_address")
            ],
        }

    numeric_rows = _numeric_prefix_rows(query, rows, limit)
    if numeric_rows:
        return {"query": query, "suggestions": [_suggestion_from_row(row) for row in numeric_rows]}

    if not re.search(r"\d", query):
        city_rows = _city_prefix_rows(query, rows, limit)
        return {"query": query, "suggestions": [_suggestion_from_row(row) for row in city_rows]}

    ranked_rows = _top_ranked_address_rows(query, rows, limit, with_geo_penalty=False)

    # If backend index has too few strong candidates, allow geocoder-backed
    # rows as a secondary source. Nominatim has already matched the full query,
    # so keep those rows after dedupe instead of re-filtering them through the
    # stricter local prefix matcher.
    if not ranked_rows and _looks_like_external_address_query(query):
        geocoder_rows = _rows_from_nominatim(query, limit)
        by_norm: dict[str, dict] = {r["normalized_full"]: r for r in ranked_rows}
        for row in geocoder_rows:
            norm = row.get("normalized_full")
            if norm and norm not in by_norm:
                by_norm[norm] = row
                ranked_rows.append(row)

    suggestions = [
        _suggestion_from_row(row)
        for row in ranked_rows[:limit]
        if row.get("display_address")
    ]
    _debug_search_flow(
        "SUGGEST_RESPONSE",
        query=query,
        limit=limit,
        backend_candidates=len(rows),
        returned=len(suggestions),
        top=[s["display_address"] for s in suggestions[:3]],
    )
    return {"query": query, "suggestions": suggestions}
