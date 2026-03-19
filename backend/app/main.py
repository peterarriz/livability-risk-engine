"""
backend/app/main.py
tasks: app-001, app-002, app-008, app-019, app-020, app-021, app-023, data-016
lane: app

FastAPI /score endpoint — updated to use the real scoring path
when a DB connection is available, with graceful fallback to the
mocked demo response when it is not (preserving demo mode).

Changes in app-019/020/021/023:
  - /score returns mode ("live"|"demo") and fallback_reason (app-019)
  - /health returns db_configured, db_connection, last_ingest_status (app-020)
  - /debug/score exposes the full scoring path for operator inspection (app-021)
  - Score requests are logged with address, mode, and fallback_reason (app-023)

API contract: docs/04_api_contracts.md
  GET /score?address=<Chicago address>
  Returns: address, disruption_score, confidence, severity, top_risks,
           explanation, mode, fallback_reason
"""

import logging
import os
from dataclasses import asdict

import requests as _requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

log = logging.getLogger(__name__)

app = FastAPI(title="Livability Risk Engine")

# ---------------------------------------------------------------------------
# CORS middleware
# Allows the Next.js dev server (localhost:3000) to call the API directly.
# In production, restrict origins to the deployed frontend domain.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        os.environ.get("FRONTEND_ORIGIN", ""),
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Demo fallback response
# Used when DB is not configured or geocoding fails.
# Matches the approved example in docs/04_api_contracts.md exactly.
# ---------------------------------------------------------------------------

DEMO_RESPONSE = {
    "address": None,            # filled in at request time
    "disruption_score": 62,
    "confidence": "MEDIUM",
    "severity": {
        "noise": "LOW",
        "traffic": "HIGH",
        "dust": "LOW",
    },
    "top_risks": [
        "2-lane eastbound closure on W Chicago Ave within roughly 120 meters",
        "Active closure window runs through 2026-03-22",
        "Traffic is the dominant near-term disruption signal at this address",
    ],
    "explanation": (
        "A nearby 2-lane closure is the main driver, so this address has "
        "elevated short-term traffic disruption even though noise and dust "
        "are limited."
    ),
}


def _build_demo_response(address: str, fallback_reason: str) -> dict:
    """
    Build a demo response for the given address.
    fallback_reason explains why demo mode is active:
      "db_not_configured" | "geocode_failed" | "query_error"
    """
    return {
        **DEMO_RESPONSE,
        "address": address,
        "mode": "demo",
        "fallback_reason": fallback_reason,
    }


# ---------------------------------------------------------------------------
# DB + scoring path (live mode)
# Only activated when DATABASE_URL or POSTGRES_HOST env var is set.
# ---------------------------------------------------------------------------

def _is_db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST"))


def _score_live(address: str) -> dict:
    """
    Full live scoring path:
      1. Geocode address → (lat, lon)
      2. Query nearby projects from canonical DB
      3. Apply scoring engine → ScoreResult
      4. Return as dict matching API contract
    """
    from backend.ingest.geocode import geocode_address
    from backend.scoring.query import compute_score, get_db_connection, get_nearby_projects

    coords = geocode_address(address)
    if not coords:
        raise ValueError(f"Could not geocode address: {address!r}")

    lat, lon = coords
    conn = get_db_connection()

    try:
        nearby = get_nearby_projects(lat, lon, conn)
    finally:
        conn.close()

    result = compute_score(nearby, address)
    return {**asdict(result), "mode": "live", "fallback_reason": None}


# ---------------------------------------------------------------------------
# /suggest endpoint (data-016)
# Returns real Chicago address suggestions from Nominatim (OpenStreetMap).
# Used by the frontend search bar autocomplete.
# ---------------------------------------------------------------------------

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_USER_AGENT = "livability-risk-engine/mvp (contact: project-team)"

# Chicago bounding box: viewbox is west,south,east,north for Nominatim.
_CHICAGO_VIEWBOX = "-87.9401,41.6445,-87.5240,42.0230"


@app.get("/suggest")
def suggest_addresses(
    q: str = Query(..., min_length=3, description="Partial Chicago address to complete"),
) -> list[str]:
    """
    Return up to 5 real Chicago address suggestions for the given partial query.

    Uses Nominatim (OpenStreetMap) with Chicago bounding box filtering.
    Returns a plain list of formatted address strings.
    Falls back to an empty list if the upstream call fails so the UI degrades
    gracefully without a hard error.
    """
    search_query = q.strip()
    if not search_query.lower().endswith("chicago"):
        search_query = f"{search_query}, Chicago, IL"

    params = {
        "q": search_query,
        "format": "json",
        "limit": 5,
        "countrycodes": "us",
        "viewbox": _CHICAGO_VIEWBOX,
        "bounded": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": _NOMINATIM_USER_AGENT}

    try:
        resp = _requests.get(_NOMINATIM_URL, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("suggest: nominatim call failed: %s", exc)
        return []

    suggestions: list[str] = []
    for item in data:
        addr = item.get("address", {})
        parts = []

        house_number = addr.get("house_number", "")
        road = addr.get("road", "")
        if house_number and road:
            parts.append(f"{house_number} {road}")
        elif road:
            parts.append(road)

        city = addr.get("city") or addr.get("town") or addr.get("village") or ""
        state = addr.get("state", "")

        if city and state:
            parts.append(f"{city}, {state}")
        elif city:
            parts.append(city)

        if parts:
            suggestions.append(", ".join(parts))

    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return unique[:5]


# ---------------------------------------------------------------------------
# /score endpoint
# ---------------------------------------------------------------------------

@app.get("/score")
def get_score(
    address: str = Query(..., description="Chicago address to score"),
) -> dict:
    """
    Return a near-term construction disruption risk score for a Chicago address.

    Live mode (when DATABASE_URL or POSTGRES_HOST is set):
      Geocodes the address, queries the canonical projects table,
      and applies the rule-based scoring engine.
      Response includes mode="live" and fallback_reason=null.

    Demo mode (when database is not configured or geocoding fails):
      Returns the approved mocked example from docs/04_api_contracts.md.
      Response includes mode="demo" and a fallback_reason string.
    """
    if not _is_db_configured():
        log.info("score address=%r mode=demo fallback_reason=db_not_configured", address)
        return _build_demo_response(address, "db_not_configured")

    try:
        result = _score_live(address)
        log.info("score address=%r mode=live fallback_reason=None", address)
        return result
    except ValueError as exc:
        # Geocoding failure — return demo response rather than a hard error
        # so the frontend stays functional during partial data availability.
        log.info(
            "score address=%r mode=demo fallback_reason=geocode_failed error=%s",
            address, exc,
        )
        return _build_demo_response(address, "geocode_failed")
    except Exception as exc:
        # Unexpected DB or scoring error — raise 503 so the frontend
        # falls back to its own demo mode gracefully.
        log.error("score address=%r unexpected scoring error: %s", address, exc)
        raise HTTPException(
            status_code=503,
            detail="Scoring service temporarily unavailable.",
        ) from exc


# ---------------------------------------------------------------------------
# /health endpoint (app-020)
# Real readiness check — distinguishes configured vs actually-connected state.
# Never raises 5xx. DB unavailability is reflected in the response body.
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """
    Backend readiness check for operators and CI.

    Fields:
      status:             always "ok" (endpoint never hard-fails)
      mode:               "live" if DATABASE_URL or POSTGRES_HOST is set, else "demo"
      db_configured:      true if DATABASE_URL or POSTGRES_HOST env var is present
      db_connection:      true if a live DB ping succeeded
      db_error:           error string if db_connection is false (omitted on success)
      last_ingest_status: reserved for future ingest tracking; null for MVP
    """
    db_configured = _is_db_configured()
    db_connection = False
    db_error = None

    if db_configured:
        try:
            from backend.scoring.query import get_db_connection
            conn = get_db_connection()
            conn.close()
            db_connection = True
        except Exception as exc:
            db_error = str(exc)

    response: dict = {
        "status": "ok",
        "mode": "live" if db_configured else "demo",
        "db_configured": db_configured,
        "db_connection": db_connection,
        "last_ingest_status": None,
    }
    if db_error is not None:
        response["db_error"] = db_error
    return response


# ---------------------------------------------------------------------------
# /debug/score endpoint (app-021)
# Internal operator endpoint — not part of the public API contract.
# Exposes the full scoring path for QA and demo-readiness checks.
# See docs/handoffs/app.md for usage.
# ---------------------------------------------------------------------------

_DEBUG_PROJECT_FIELDS = frozenset(
    {"project_id", "source", "impact_type", "title", "start_date", "end_date", "status"}
)


def _serialize_project_sample(nearby_list) -> list:
    """
    Return a minimal, JSON-safe summary of up to 3 nearby projects.
    Dates are converted to ISO strings; only key fields are included.
    """
    sample = []
    for np in nearby_list[:3]:
        row = asdict(np.project)
        entry = {}
        for k, v in row.items():
            if k not in _DEBUG_PROJECT_FIELDS:
                continue
            # Convert date objects to ISO strings for JSON serialisation.
            entry[k] = v.isoformat() if hasattr(v, "isoformat") else v
        entry["distance_m"] = round(np.distance_m)
        sample.append(entry)
    return sample


@app.get("/debug/score")
def debug_score(
    address: str = Query(..., description="Chicago address to inspect"),
) -> dict:
    """
    Internal operator endpoint — not part of the public API contract.

    Returns the full scoring path so operators can confirm:
      - Geocoding is working for the submitted address
      - Nearby projects are being found and counted
      - The score result matches expectations
      - Which mode and fallback_reason are in play

    This endpoint does not require auth for MVP but is intended for ops use only.
    It returns a useful partial response even when geocoding or DB is unavailable.
    """
    if not _is_db_configured():
        return {
            "address": address,
            "mode": "demo",
            "lat": None,
            "lon": None,
            "nearby_projects_count": None,
            "nearby_projects_sample": [],
            "score_result": _build_demo_response(address, "db_not_configured"),
            "fallback_reason": "db_not_configured",
        }

    try:
        from backend.ingest.geocode import geocode_address
        from backend.scoring.query import (
            compute_score,
            get_db_connection,
            get_nearby_projects,
        )

        coords = geocode_address(address)
        if not coords:
            return {
                "address": address,
                "mode": "demo",
                "lat": None,
                "lon": None,
                "nearby_projects_count": None,
                "nearby_projects_sample": [],
                "score_result": _build_demo_response(address, "geocode_failed"),
                "fallback_reason": "geocode_failed",
            }

        lat, lon = coords
        conn = get_db_connection()
        try:
            nearby = get_nearby_projects(lat, lon, conn)
        finally:
            conn.close()

        result = compute_score(nearby, address)
        return {
            "address": address,
            "mode": "live",
            "lat": lat,
            "lon": lon,
            "nearby_projects_count": len(nearby),
            "nearby_projects_sample": _serialize_project_sample(nearby),
            "score_result": {**asdict(result), "mode": "live", "fallback_reason": None},
            "fallback_reason": None,
        }

    except Exception as exc:
        log.error("debug_score address=%r error: %s", address, exc)
        return {
            "address": address,
            "mode": "demo",
            "lat": None,
            "lon": None,
            "nearby_projects_count": None,
            "nearby_projects_sample": [],
            "score_result": _build_demo_response(address, "query_error"),
            "fallback_reason": "query_error",
            "error": str(exc),
        }
