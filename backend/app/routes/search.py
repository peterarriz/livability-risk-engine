"""
backend/app/routes/search.py

Search-related endpoints extracted from main.py:
  - GET /addresses/search  — address autocomplete for the search bar
  - GET /suggest           — unified address suggestion with geocoder fallback
"""

import hashlib
import logging

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)

router = APIRouter()


def _rows_from_nominatim(query: str, limit: int) -> list[dict]:
    """Fallback suggestions from geocoder when DB index has no strong results."""
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
                "canonical_id": f"geo_{hashlib.sha1(norm.encode('utf-8')).hexdigest()[:16]}",
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
            "canonical_id": row["canonical_id"],
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

    # For empty/short queries, return most popular scored addresses so the
    # frontend can show instant suggestions on focus or after 1-2 keystrokes.
    if len(query) < 3:
        if not popular and len(query) == 0:
            return {"query": query, "suggestions": []}
        top = sorted(rows, key=lambda r: int(r.get("popularity", 0)), reverse=True)[:limit]
        return {
            "query": query,
            "suggestions": [
                {
                    "canonical_id": row["canonical_id"],
                    "display_address": row["display_address"],
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                    "city": row.get("city"),
                    "state": row.get("state"),
                    "zip": row.get("zip"),
                }
                for row in top
                if row.get("canonical_id") and row.get("display_address")
            ],
        }

    ranked_rows = _top_ranked_address_rows(query, rows, limit, with_geo_penalty=True)

    # If backend index has too few strong candidates, allow geocoder-backed
    # rows as a secondary source. They are still normalized + ranked.
    if len(ranked_rows) < limit:
        geocoder_rows = _rows_from_nominatim(query, limit)
        by_norm: dict[str, dict] = {r["normalized_full"]: r for r in ranked_rows}
        for row in geocoder_rows:
            by_norm.setdefault(row["normalized_full"], row)
        ranked_rows = _top_ranked_address_rows(query, list(by_norm.values()), limit, with_geo_penalty=True)

    suggestions = [
        {
            "canonical_id": row["canonical_id"],
            "display_address": row["display_address"],
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "city": row.get("city"),
            "state": row.get("state"),
            "zip": row.get("zip"),
        }
        for row in ranked_rows[:limit]
        if row.get("canonical_id") and row.get("display_address")
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
