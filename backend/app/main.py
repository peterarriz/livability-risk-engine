"""
backend/app/main.py
tasks: app-001, app-002, app-008, app-019, app-020, app-021, app-023, data-016
lane: app

FastAPI /score endpoint — live scoring against the Railway Postgres+PostGIS DB.
Demo fallback removed in data-017 (DB is now live on Railway).

Changes in app-019/020/021/023:
  - /score returns mode ("live") and fallback_reason (app-019)
  - /health returns db_configured, db_connection, last_ingest_status (app-020)
  - /debug/score exposes the full scoring path for operator inspection (app-021)
  - Score requests are logged with address, mode, and fallback_reason (app-023)

API contract: docs/04_api_contracts.md
  GET /score?address=<Chicago address>
  Returns: address, disruption_score, confidence, severity, top_risks,
           explanation, mode, fallback_reason
"""

import csv
import hashlib
import io
import logging
import os
import secrets
from dataclasses import asdict

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

import requests as _requests
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

app = FastAPI(title="Livability Risk Engine")

# ---------------------------------------------------------------------------
# CORS middleware
# Allows the Next.js dev server (localhost:3000) to call the API directly.
# In production, set FRONTEND_ORIGIN to the deployed Vercel domain, e.g.:
#   FRONTEND_ORIGIN=https://livability-risk-engine.vercel.app
# ---------------------------------------------------------------------------

_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
if _frontend_origin:
    _allowed_origins.append(_frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
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


def _build_demo_response(address: str, fallback_reason: str, lat: float | None = None, lon: float | None = None) -> dict:
    """
    Build a demo response for the given address.
    fallback_reason explains why demo mode is active:
      "db_not_configured" | "geocode_failed" | "scoring_error"
    latitude/longitude are included when available so the frontend map can show
    the correct pin even in demo mode.
    """
    return {
        **DEMO_RESPONSE,
        "address": address,
        "mode": "demo",
        "fallback_reason": fallback_reason,
        "latitude": lat,
        "longitude": lon,
    }


# ---------------------------------------------------------------------------
# DB + scoring path (live mode)
# ---------------------------------------------------------------------------

def _is_db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST"))


def _score_live(address: str) -> dict:
    """
    Full live scoring path:
      1. Confirm the canonical DB is reachable
      2. Geocode address → (lat, lon)
      3. Query nearby projects from canonical DB
      4. Apply scoring engine → ScoreResult
      5. Return as dict matching API contract (includes latitude/longitude)
    """
    from backend.ingest.geocode import geocode_address
    from backend.scoring.query import compute_score, get_db_connection, get_nearby_projects

    conn = get_db_connection()
    try:
        coords = geocode_address(address)
        if not coords:
            raise ValueError(f"Could not geocode address: {address!r}")

        lat, lon = coords
        nearby = get_nearby_projects(lat, lon, conn)
    finally:
        conn.close()

    result = compute_score(nearby, address)
    return {**asdict(result), "mode": "live", "fallback_reason": None, "latitude": lat, "longitude": lon}


# ---------------------------------------------------------------------------
# /suggest endpoint (data-016)
# Returns real Chicago address suggestions from Nominatim (OpenStreetMap).
# Used by the frontend search bar autocomplete.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# /score endpoint
# ---------------------------------------------------------------------------

@app.get("/score", dependencies=[Depends(verify_api_key)])
def get_score(
    address: str = Query(..., description="Chicago address to score"),
) -> dict:
    """
    Return a near-term construction disruption risk score for a Chicago address.

    When a live DB is configured: geocodes, queries projects, and scores live.
    When DB is not configured: returns the approved demo scenario so the frontend
    always receives a structured response (never a raw 503).
    Response includes mode, fallback_reason, and latitude/longitude for map display.
    """
    # When no DB is configured, return a demo response.
    # Include pre-resolved coords for known addresses so the frontend map pin works
    # without a second geocode round-trip.
    _KNOWN_COORDS: dict[str, tuple[float, float]] = {
        "1600 W Chicago Ave, Chicago, IL": (41.8956, -87.6606),
        "700 W Grand Ave, Chicago, IL": (41.8910, -87.6462),
        "233 S Wacker Dr, Chicago, IL": (41.8788, -87.6359),
    }
    if not _is_db_configured():
        known = _KNOWN_COORDS.get(address)
        lat, lon = (known[0], known[1]) if known else (None, None)
        if lat is None:
            try:
                from backend.ingest.geocode import geocode_address
                coords = geocode_address(address)
                if coords:
                    lat, lon = coords
            except Exception:
                pass
        log.info("score address=%r mode=demo fallback_reason=db_not_configured", address)
        return _build_demo_response(address, "db_not_configured", lat, lon)

    try:
        result = _score_live(address)
        log.info("score address=%r mode=live fallback_reason=None", address)
        _record_score_history(address, result["disruption_score"], result["confidence"], "live")
        return result
    except ValueError as exc:
        log.warning("score address=%r geocode_failed error=%s", address, exc)
        raise HTTPException(
            status_code=422,
            detail=f"Could not geocode address: {exc}",
        ) from exc
    except Exception as exc:
        log.error("score address=%r unexpected scoring error: %s", address, exc)
        raise HTTPException(
            status_code=503,
            detail="Scoring service temporarily unavailable.",
        ) from exc


# ---------------------------------------------------------------------------
# Score history helpers (data-025)
# ---------------------------------------------------------------------------

def _record_score_history(address: str, score: int, confidence: str, mode: str) -> None:
    """
    Write a score_history row. Fire-and-forget: exceptions are logged and swallowed
    so a history write failure never breaks the /score response.
    """
    if not _is_db_configured():
        return
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO score_history (address, disruption_score, confidence, mode) VALUES (%s, %s, %s, %s)",
                    (address, score, confidence, mode),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.warning("score_history write failed (non-fatal): %s", exc)


@app.get("/history")
def get_score_history(
    address: str = Query(..., description="Chicago address to fetch history for"),
    limit: int = Query(10, ge=1, le=50, description="Max number of historical records to return"),
) -> dict:
    """
    Return the score history for a given address (most recent first).
    Used by the frontend sparkline component to show score trend over time.
    Returns an empty list when DB is not configured or address has no history.
    """
    if not _is_db_configured():
        return {"address": address, "history": []}

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT disruption_score, confidence, mode, created_at
                    FROM score_history
                    WHERE address = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (address, limit),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        history = [
            {
                "disruption_score": row[0],
                "confidence": row[1],
                "mode": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
            }
            for row in rows
        ]
        return {"address": address, "history": history}

    except Exception as exc:
        log.error("get_score_history address=%r error: %s", address, exc)
        return {"address": address, "history": []}


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
        "mode": "live" if db_configured else "unconfigured",
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
    Return a minimal, JSON-safe summary of up to 5 nearby projects.
    Dates are converted to ISO strings; only key fields are included.
    """
    sample = []
    for np in nearby_list[:5]:
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
    try:
        from backend.ingest.geocode import geocode_address
        from backend.scoring.query import (
            compute_score,
            get_db_connection,
            get_nearby_projects,
        )

        conn = get_db_connection()
        try:
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

    except HTTPException:
        raise
    except Exception as exc:
        log.error("debug_score address=%r error: %s", address, exc)
        return {
            "address": address,
            "mode": "demo",
            "lat": None,
            "lon": None,
            "nearby_projects_count": None,
            "nearby_projects_sample": [],
            "score_result": _build_demo_response(address, "scoring_error"),
            "fallback_reason": "scoring_error",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# /suggest endpoint
# Returns up to 5 Chicago address suggestions for a partial query.
# Primary: Nominatim (OpenStreetMap).
# Fallback: Photon by Komoot (also OSM-backed, more permissive from servers).
# ---------------------------------------------------------------------------

# Nominatim: viewbox = left,top,right,bottom = minLon,maxLat,maxLon,minLat
_NOMINATIM_VIEWBOX = "-87.9401,42.0230,-87.5240,41.6445"
# Photon: bbox = minLon,minLat,maxLon,maxLat
_PHOTON_BBOX = "-87.9401,41.6445,-87.5240,42.0230"
# Chicago lat/lon bounds for bbox-based filtering (avoids strict city-name check)
_CHI_LAT = (41.6445, 42.0230)
_CHI_LON = (-87.9401, -87.5240)


def _in_chicago(lat: float, lon: float) -> bool:
    return _CHI_LAT[0] <= lat <= _CHI_LAT[1] and _CHI_LON[0] <= lon <= _CHI_LON[1]


def _parse_nominatim(results: list) -> list[str]:
    """Format Nominatim results as 'number road, Chicago, IL' strings."""
    suggestions: list[str] = []
    seen: set[str] = set()
    for r in results:
        try:
            if not _in_chicago(float(r["lat"]), float(r["lon"])):
                continue
        except (KeyError, ValueError):
            continue
        addr = r.get("address", {})
        house = addr.get("house_number", "")
        road = addr.get("road") or addr.get("pedestrian") or addr.get("highway") or ""
        if not road:
            continue
        formatted = f"{house} {road}, Chicago, IL" if house else f"{road}, Chicago, IL"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


def _parse_photon(features: list) -> list[str]:
    """Format Photon GeoJSON features as 'number road, Chicago, IL' strings."""
    suggestions: list[str] = []
    seen: set[str] = set()
    for f in features:
        props = f.get("properties", {})
        if props.get("countrycode", "").upper() != "US":
            continue
        coords = f.get("geometry", {}).get("coordinates", [])
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if not _in_chicago(lat, lon):
                continue
        except (IndexError, ValueError, TypeError):
            continue
        street = props.get("street", "")
        if not street:
            continue
        house = props.get("housenumber", "")
        formatted = f"{house} {street}, Chicago, IL" if house else f"{street}, Chicago, IL"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


@app.get("/suggest")
def suggest_addresses(
    q: str = Query(..., min_length=2, description="Partial Chicago address query"),
) -> dict:
    """
    Return up to 5 Chicago address suggestions for a partial address query.
    Used by the frontend autocomplete input.

    Tries Nominatim first; falls back to Photon (komoot) if Nominatim is
    unreachable or returns no results within the Chicago bbox.
    """
    query = q.strip()
    # Bias both geocoders toward Chicago without altering short queries.
    nominatim_q = query if "chicago" in query.lower() else f"{query}, Chicago, IL"
    photon_q = query if "chicago" in query.lower() else f"{query} Chicago"

    # 1. Nominatim
    try:
        resp = _requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": nominatim_q,
                "format": "json",
                "limit": 8,
                "countrycodes": "us",
                "bounded": "1",
                "viewbox": _NOMINATIM_VIEWBOX,
                "addressdetails": "1",
            },
            headers={"User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)"},
            timeout=4,
        )
        if resp.ok:
            suggestions = _parse_nominatim(resp.json())
            if suggestions:
                log.info("suggest q=%r source=nominatim results=%d", q, len(suggestions))
                return {"suggestions": suggestions}
    except Exception as exc:
        log.debug("suggest q=%r nominatim error: %s", q, exc)

    # 2. Photon fallback
    try:
        resp = _requests.get(
            "https://photon.komoot.io/api/",
            params={
                "q": photon_q,
                "limit": 8,
                "bbox": _PHOTON_BBOX,
                "lang": "en",
            },
            timeout=4,
        )
        if resp.ok:
            suggestions = _parse_photon(resp.json().get("features", []))
            log.info("suggest q=%r source=photon results=%d", q, len(suggestions))
            return {"suggestions": suggestions}
    except Exception as exc:
        log.warning("suggest q=%r both geocoders failed, last error: %s", q, exc)

    return {"suggestions": []}


# ---------------------------------------------------------------------------
# /neighborhood/<slug> endpoint (data-026)
# Returns all active projects within a neighborhood bounding box.
# Used by the /neighborhood/[slug] Next.js page for the heat map.
# ---------------------------------------------------------------------------

# Chicago neighborhood bounding boxes: (min_lat, min_lon, max_lat, max_lon)
NEIGHBORHOODS: dict[str, dict] = {
    "west-loop": {
        "name": "West Loop",
        "description": "Former meatpacking district turned restaurant and tech corridor.",
        "bbox": (41.8780, -87.6620, 41.8900, -87.6430),
    },
    "wicker-park": {
        "name": "Wicker Park",
        "description": "Dense mixed-use neighborhood with active permit and closure activity.",
        "bbox": (41.9040, -87.6800, 41.9180, -87.6560),
    },
    "logan-square": {
        "name": "Logan Square",
        "description": "Rapidly developing residential and commercial corridor.",
        "bbox": (41.9180, -87.7100, 41.9340, -87.6830),
    },
    "river-north": {
        "name": "River North",
        "description": "High-density area with ongoing construction and street activity.",
        "bbox": (41.8880, -87.6390, 41.9000, -87.6240),
    },
    "lincoln-park": {
        "name": "Lincoln Park",
        "description": "Residential neighborhood adjacent to the lakefront.",
        "bbox": (41.9150, -87.6560, 41.9340, -87.6330),
    },
    "pilsen": {
        "name": "Pilsen",
        "description": "Arts and residential neighborhood with active development.",
        "bbox": (41.8520, -87.6740, 41.8680, -87.6450),
    },
    "bronzeville": {
        "name": "Bronzeville",
        "description": "Historic South Side neighborhood with redevelopment activity.",
        "bbox": (41.8220, -87.6300, 41.8500, -87.6050),
    },
    "uptown": {
        "name": "Uptown",
        "description": "Diverse lakefront neighborhood with mixed-use redevelopment.",
        "bbox": (41.9560, -87.6620, 41.9720, -87.6400),
    },
}

NEIGHBORHOOD_PROJECTS_SQL = """
    SELECT
        project_id, source, impact_type, title, notes,
        start_date, end_date, status, address,
        latitude, longitude
    FROM projects
    WHERE
        status = ANY(%s)
        AND geom IS NOT NULL
        AND ST_Within(
            geom,
            ST_MakeEnvelope(%s, %s, %s, %s, 4326)
        )
    ORDER BY
        CASE impact_type
            WHEN 'closure_full'       THEN 1
            WHEN 'closure_multi_lane' THEN 2
            WHEN 'closure_single_lane' THEN 3
            WHEN 'demolition'         THEN 4
            WHEN 'construction'       THEN 5
            ELSE 6
        END,
        start_date DESC NULLS LAST
    LIMIT 100;
"""


@app.get("/neighborhood/{slug}")
def get_neighborhood(slug: str) -> dict:
    """
    Return all active projects within a named Chicago neighborhood bounding box.
    Used by the /neighborhood/[slug] frontend page.

    Returns 404 for unknown slugs.
    Returns an empty projects list when DB is not configured (demo mode).
    """
    hood = NEIGHBORHOODS.get(slug)
    if not hood:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown neighborhood '{slug}'. Valid slugs: {list(NEIGHBORHOODS)}",
        )

    meta = {
        "slug": slug,
        "name": hood["name"],
        "description": hood["description"],
        "bbox": {
            "min_lat": hood["bbox"][0],
            "min_lon": hood["bbox"][1],
            "max_lat": hood["bbox"][2],
            "max_lon": hood["bbox"][3],
        },
        "available_neighborhoods": [
            {"slug": k, "name": v["name"]} for k, v in NEIGHBORHOODS.items()
        ],
    }

    if not _is_db_configured():
        return {**meta, "projects": [], "mode": "demo"}

    try:
        from backend.scoring.query import get_db_connection
        min_lat, min_lon, max_lat, max_lon = hood["bbox"]
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    NEIGHBORHOOD_PROJECTS_SQL,
                    (list(("active", "planned", "unknown")), min_lon, min_lat, max_lon, max_lat),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        projects = [
            {
                "project_id": r[0],
                "source": r[1],
                "impact_type": r[2],
                "title": r[3],
                "notes": r[4],
                "start_date": r[5].isoformat() if r[5] else None,
                "end_date": r[6].isoformat() if r[6] else None,
                "status": r[7],
                "address": r[8],
                "latitude": float(r[9]) if r[9] is not None else None,
                "longitude": float(r[10]) if r[10] is not None else None,
            }
            for r in rows
        ]

        log.info("neighborhood slug=%r projects=%d", slug, len(projects))
        return {**meta, "projects": projects, "mode": "live"}

    except Exception as exc:
        log.error("neighborhood slug=%r error: %s", slug, exc)
        raise HTTPException(status_code=503, detail="Could not fetch neighborhood data.") from exc


# ---------------------------------------------------------------------------
# /save endpoint (data-021)
# Stores a score result in the reports table and returns a shareable UUID.
# ---------------------------------------------------------------------------

class SaveReportRequest(BaseModel):
    address: str
    score_json: dict


@app.post("/save")
def save_report(body: SaveReportRequest) -> dict:
    """
    Save a score result and return a shareable report_id UUID.

    Requires a live DB. Returns 503 if DB is not configured.
    The frontend uses the returned report_id to build a /report/<id> URL.
    """
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Report saving requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection
        import json

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO reports (address, score_json)
                    VALUES (%s, %s::jsonb)
                    RETURNING report_id
                    """,
                    (body.address, json.dumps(body.score_json)),
                )
                row = cur.fetchone()
                report_id = str(row[0])
            conn.commit()
        finally:
            conn.close()

        log.info("save_report address=%r report_id=%s", body.address, report_id)
        return {"report_id": report_id, "address": body.address}

    except HTTPException:
        raise
    except Exception as exc:
        log.error("save_report error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not save report.") from exc


# ---------------------------------------------------------------------------
# /report/{report_id} endpoint (data-021)
# Fetches a saved report snapshot by UUID.
# ---------------------------------------------------------------------------

@app.get("/report/{report_id}")
def get_report(report_id: str) -> dict:
    """
    Return a previously saved score result by its UUID.

    Used by the shareable /report/<id> Next.js page.
    Returns 404 if the report does not exist.
    """
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Report retrieval requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT report_id, address, score_json, created_at FROM reports WHERE report_id = %s",
                    (report_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Report not found.")

        report_id_val, address, score_json, created_at = row
        return {
            "report_id": str(report_id_val),
            "address": address,
            "score": score_json,
            "created_at": created_at.isoformat() if created_at else None,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_report report_id=%r error: %s", report_id, exc)
        raise HTTPException(status_code=503, detail="Could not retrieve report.") from exc


# ---------------------------------------------------------------------------
# API key auth middleware (data-027)
#
# Optional gating: only enforced when REQUIRE_API_KEY=true env var is set.
# This means existing public usage continues to work by default.
# Keys are stored as SHA-256 hashes — full key is never persisted.
# ---------------------------------------------------------------------------

_REQUIRE_API_KEY = os.environ.get("REQUIRE_API_KEY", "").lower() in ("true", "1", "yes")
_ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(
    x_api_key: str | None = None,
    api_key: str | None = Query(default=None, alias="api_key"),
) -> None:
    """
    FastAPI dependency that enforces API key authentication when
    REQUIRE_API_KEY=true. Pass-through (no-op) otherwise.

    Accepts the key via:
      - X-Api-Key header  (preferred)
      - ?api_key=<key>    (query param fallback)
    """
    if not _REQUIRE_API_KEY:
        return  # Auth disabled — pass through.

    raw = (x_api_key or api_key or "").strip()
    if not raw:
        raise HTTPException(
            status_code=401,
            detail="API key required. Pass X-Api-Key header or ?api_key= query param.",
        )

    if not _is_db_configured():
        # DB unavailable and auth required — fail safe.
        raise HTTPException(status_code=503, detail="Auth service unavailable.")

    try:
        from backend.scoring.query import get_db_connection
        key_hash = _hash_key(raw)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM api_keys WHERE key_hash = %s AND is_active = true",
                    (key_hash,),
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE api_keys SET last_used_at = now() WHERE key_hash = %s",
                        (key_hash,),
                    )
            conn.commit()
        finally:
            conn.close()

        if not row:
            raise HTTPException(status_code=403, detail="Invalid or inactive API key.")

    except HTTPException:
        raise
    except Exception as exc:
        log.error("verify_api_key error: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service error.") from exc


class CreateKeyRequest(BaseModel):
    label: str


@app.post("/admin/keys")
def create_api_key(body: CreateKeyRequest, admin_secret: str = Query(...)) -> dict:
    """
    Create a new API key. Protected by the ADMIN_SECRET env var.

    Returns the full key ONCE — it is never stored. Record the key immediately.
    Subsequent requests will only show the 8-char prefix.
    """
    if not _ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="ADMIN_SECRET not configured.")
    if admin_secret != _ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret.")
    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured.")

    raw_key = f"lre_{secrets.token_urlsafe(32)}"
    prefix = raw_key[:8]
    key_hash = _hash_key(raw_key)

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO api_keys (key_prefix, key_hash, label) VALUES (%s, %s, %s) RETURNING id",
                    (prefix, key_hash, body.label),
                )
                key_id = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        log.info("create_api_key label=%r prefix=%r id=%d", body.label, prefix, key_id)
        return {
            "id": key_id,
            "label": body.label,
            "key_prefix": prefix,
            "key": raw_key,  # Full key shown ONCE — store it now.
            "note": "This is the only time the full key will be shown. Store it securely.",
        }
    except Exception as exc:
        log.error("create_api_key error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not create API key.") from exc


@app.get("/admin/keys")
def list_api_keys(admin_secret: str = Query(...)) -> dict:
    """List all API keys (prefix + label only — no hashes returned)."""
    if not _ADMIN_SECRET:
        raise HTTPException(status_code=503, detail="ADMIN_SECRET not configured.")
    if admin_secret != _ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret.")
    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured.")

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, key_prefix, label, created_at, last_used_at, is_active FROM api_keys ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return {
            "keys": [
                {
                    "id": r[0],
                    "key_prefix": r[1],
                    "label": r[2],
                    "created_at": r[3].isoformat() if r[3] else None,
                    "last_used_at": r[4].isoformat() if r[4] else None,
                    "is_active": r[5],
                }
                for r in rows
            ]
        }
    except Exception as exc:
        log.error("list_api_keys error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not list API keys.") from exc


@app.get("/docs/api-access")
def api_access_info() -> dict:
    """
    Public endpoint documenting how to request API access.
    Useful for B2B prospects landing on the developer docs.
    """
    return {
        "title": "Livability Risk Engine API",
        "version": "1.0",
        "description": (
            "Programmatic access to Chicago disruption scoring. "
            "Query /score with any Chicago address to get a 0-100 disruption score, "
            "severity breakdown, and top risk signals."
        ),
        "auth": {
            "required": _REQUIRE_API_KEY,
            "method": "Pass your API key in the X-Api-Key header or ?api_key= query param.",
            "request_access": "Contact the operator to request an API key.",
        },
        "endpoints": [
            {"method": "GET", "path": "/score", "description": "Score a Chicago address (0–100)"},
            {"method": "GET", "path": "/suggest", "description": "Address autocomplete"},
            {"method": "GET", "path": "/history", "description": "Score history for an address"},
            {"method": "GET", "path": "/neighborhood/{slug}", "description": "Projects in a named neighborhood"},
            {"method": "POST", "path": "/save", "description": "Save a score result for sharing"},
            {"method": "GET", "path": "/report/{report_id}", "description": "Fetch a saved report"},
            {"method": "GET", "path": "/health", "description": "Backend readiness check"},
            {"method": "GET", "path": "/export/csv", "description": "Download score and nearby projects as CSV"},
        ],
        "rate_limits": "Unauthenticated requests are rate-limited at the infrastructure level.",
        "example": {
            "request": "GET /score?address=100+W+Randolph+St+Chicago+IL",
            "response_shape": {
                "address": "string",
                "disruption_score": "0–100 integer",
                "confidence": "LOW | MEDIUM | HIGH",
                "severity": {"noise": "...", "traffic": "...", "dust": "..."},
                "top_risks": ["string", "string", "string"],
                "explanation": "string",
                "mode": "live | demo",
            },
        },
    }


# ---------------------------------------------------------------------------
# /export/csv endpoint  (data-029)
# Returns nearby projects for an address as a downloadable CSV file.
# Works in both live and demo mode.
# ---------------------------------------------------------------------------

_DEMO_CSV_PROJECTS = [
    {
        "distance_m": 120,
        "title": "2-lane eastbound closure on W Chicago Ave",
        "source": "street_closure",
        "source_id": "DEMO-001",
        "impact_type": "multi_lane_closure",
        "status": "active",
        "start_date": "2026-03-01",
        "end_date": "2026-03-22",
        "address": "W Chicago Ave",
        "weighted_score": 28,
    },
    {
        "distance_m": 210,
        "title": "Active construction permit near 120 W Randolph St",
        "source": "building_permit",
        "source_id": "DEMO-002",
        "impact_type": "construction",
        "status": "active",
        "start_date": "2026-02-15",
        "end_date": "2026-06-30",
        "address": "120 W Randolph St",
        "weighted_score": 18,
    },
]


@app.get("/export/csv", dependencies=[Depends(verify_api_key)])
def export_csv(
    address: str = Query(..., description="Chicago address to score and export"),
) -> StreamingResponse:
    """
    data-029: Export score results for an address as a CSV file.

    Returns one row per nearby project plus a summary row.
    Columns: distance_m, title, source, source_id, impact_type, status,
             start_date, end_date, address, weighted_score.
    A summary row (distance_m=SUMMARY) captures disruption_score and confidence.
    Works in demo mode when DB is not configured.
    """
    # -- Live path -----------------------------------------------------------
    if _is_db_configured():
        try:
            from backend.ingest.geocode import geocode_address
            from backend.scoring.query import compute_score, get_db_connection, get_nearby_projects

            conn = get_db_connection()
            try:
                coords = geocode_address(address)
                if not coords:
                    raise ValueError(f"Could not geocode: {address!r}")
                lat, lon = coords
                nearby = get_nearby_projects(lat, lon, conn)
            finally:
                conn.close()

            result = compute_score(nearby, address)
            disruption_score = result.disruption_score
            confidence = result.confidence

            # Build project rows from top_risk_details when available,
            # otherwise fall back to a minimal row per NearbyProject.
            if result.top_risk_details:
                project_rows = result.top_risk_details
            else:
                project_rows = [
                    {
                        "distance_m": round(nbp.distance_m),
                        "title": nbp.project.title or "",
                        "source": nbp.project.source or "",
                        "source_id": nbp.project.source_id or "",
                        "impact_type": nbp.project.impact_type or "",
                        "status": nbp.project.status or "",
                        "start_date": str(nbp.project.start_date) if nbp.project.start_date else "",
                        "end_date": str(nbp.project.end_date) if nbp.project.end_date else "",
                        "address": nbp.project.address or "",
                        "weighted_score": "",
                    }
                    for nbp in nearby
                ]

        except Exception as exc:
            log.warning("export_csv live path failed, falling back to demo: %s", exc)
            disruption_score = 62
            confidence = "MEDIUM"
            project_rows = _DEMO_CSV_PROJECTS

    # -- Demo path -----------------------------------------------------------
    else:
        disruption_score = 62
        confidence = "MEDIUM"
        project_rows = _DEMO_CSV_PROJECTS

    # -- Build CSV -----------------------------------------------------------
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "distance_m", "title", "source", "source_id",
            "impact_type", "status", "start_date", "end_date",
            "address", "weighted_score",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()

    # Summary row first
    writer.writerow({
        "distance_m": "SUMMARY",
        "title": f"disruption_score={disruption_score} confidence={confidence}",
        "source": "", "source_id": "", "impact_type": "", "status": "",
        "start_date": "", "end_date": "",
        "address": address,
        "weighted_score": disruption_score,
    })

    for row in project_rows:
        writer.writerow(row)

    output.seek(0)
    safe_addr = address.replace(" ", "_").replace(",", "")[:60]
    filename = f"livability_risk_{safe_addr}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
