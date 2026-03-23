"""
backend/app/main.py
tasks: app-001, app-002, app-008, app-019, app-020, app-021, app-023, data-016, data-030
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
import re
import secrets
from dataclasses import asdict

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

import requests as _requests
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
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

# Allow all Vercel preview/production deployments automatically so the
# frontend works before FRONTEND_ORIGIN is explicitly configured in Railway.
_allow_origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_allow_origin_regex,
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
    # Demo signals near 1600 W Chicago Ave (41.8956, -87.6606) for map heat layer.
    "nearby_signals": [
        {
            "lat": 41.8959,
            "lon": -87.6594,
            "impact_type": "closure_multi_lane",
            "title": "W Chicago Ave 2-lane eastbound closure",
            "distance_m": 120,
            "severity_hint": "HIGH",
            "weight": 30.4,
        },
        {
            "lat": 41.8962,
            "lon": -87.6618,
            "impact_type": "construction",
            "title": "Active construction permit at 1550 W Chicago Ave",
            "distance_m": 210,
            "severity_hint": "MEDIUM",
            "weight": 8.8,
        },
        {
            "lat": 41.8948,
            "lon": -87.6602,
            "impact_type": "closure_single_lane",
            "title": "Curb lane closure on S Ashland Ave",
            "distance_m": 380,
            "severity_hint": "MEDIUM",
            "weight": 5.3,
        },
    ],
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


# ---------------------------------------------------------------------------
# API key auth  (data-027)
#
# Enabled by setting REQUIRE_API_KEY=true (or 1/yes) in the environment.
# Off by default so existing usage is unaffected.
#
# Key format:  lre_<64 random hex chars>
# Storage:     prefix (first 8 hex chars) + sha256(full key)
# Header:      X-API-Key: lre_<...>
# ---------------------------------------------------------------------------

def _require_api_key_enabled() -> bool:
    return os.environ.get("REQUIRE_API_KEY", "").lower() in ("1", "true", "yes")


def _hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def _generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_key, prefix, key_hash).
      full_key:  returned to the operator once — never stored
      prefix:    first 8 hex chars of random portion — stored for O(1) lookup
      key_hash:  sha256(full_key) — stored for verification
    """
    random_portion = secrets.token_hex(32)   # 64 hex chars
    prefix = random_portion[:8]
    full_key = f"lre_{random_portion}"
    return full_key, prefix, _hash_key(full_key)


async def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    """
    FastAPI dependency for optional API key authentication.

    When REQUIRE_API_KEY is not set (the default), this is a no-op and every
    request passes through.  When enabled, the caller must supply a valid key
    in the X-API-Key header.
    """
    if not _require_api_key_enabled():
        return

    if not x_api_key or not x_api_key.startswith("lre_"):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    random_portion = x_api_key[4:]    # strip "lre_"
    if len(random_portion) < 8:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    prefix = random_portion[:8]
    submitted_hash = _hash_key(x_api_key)

    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Auth service unavailable (DB not configured)")

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key_hash, is_active FROM api_keys WHERE prefix = %s",
                    (prefix,),
                )
                row = cur.fetchone()
                if row and row[1]:
                    # Update last_used_at asynchronously — best-effort, non-blocking
                    try:
                        cur.execute(
                            "UPDATE api_keys SET last_used_at = now() WHERE prefix = %s",
                            (prefix,),
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        log.error("verify_api_key DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    if not row or not row[1] or row[0] != submitted_hash:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


# ---------------------------------------------------------------------------
# /admin/keys endpoint  (data-027)
# Protected by ADMIN_SECRET header. Creates a new API key and returns it
# once. The raw key is never stored — only the sha256 hash is persisted.
# ---------------------------------------------------------------------------

@app.post("/admin/keys")
def create_api_key(
    label: str = Query(..., description="Human-readable label for this key"),
    x_admin_secret: str | None = Header(None),
) -> dict:
    """
    Create a new API key.

    Requires the X-Admin-Secret header to match the ADMIN_SECRET env var.
    Returns the raw key once — it cannot be retrieved again.

    The key is stored as a sha256 hash; only the prefix is kept for lookup.
    Activate API key enforcement by setting REQUIRE_API_KEY=true on the backend.
    """
    admin_secret = os.environ.get("ADMIN_SECRET", "")
    if not admin_secret or x_admin_secret != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured")

    full_key, prefix, key_hash = _generate_api_key()

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_keys (prefix, key_hash, label)
                    VALUES (%s, %s, %s)
                    """,
                    (prefix, key_hash, label.strip()),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.error("create_api_key DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not persist API key") from exc

    log.info("create_api_key label=%r prefix=%s", label, prefix)
    return {
        "key": full_key,
        "prefix": prefix,
        "label": label.strip(),
        "note": "Store this key securely — it cannot be retrieved again.",
    }


# ---------------------------------------------------------------------------
# /docs/api-access endpoint  (data-027)
# Public — returns information about how to obtain and use an API key.
# ---------------------------------------------------------------------------

@app.get("/docs/api-access")
def api_access_info() -> dict:
    """
    Public documentation endpoint for B2B API access.

    Returns information about how to authenticate requests when API key
    enforcement is active.  Does not require auth.
    """
    return {
        "auth_required": _require_api_key_enabled(),
        "header": "X-API-Key",
        "key_format": "lre_<64 hex chars>",
        "how_to_obtain": (
            "Contact the platform operator to request an API key. "
            "Keys are provisioned via POST /admin/keys."
        ),
        "usage_example": "curl -H 'X-API-Key: lre_...' '<base_url>/score?address=...'",
        "docs": "https://github.com/peterarriz/livability-risk-engine",
    }


def _score_live(address: str) -> dict:
    """
    Full live scoring path:
      1. Confirm the canonical DB is reachable
      2. Geocode address → (lat, lon)
      3. Query nearby projects from canonical DB
      4. Apply scoring engine → ScoreResult
      5. Query neighborhood quality context (data-040) — non-fatal if table absent
      6. Enrich top_risk_details with Claude-rewritten titles (data-042, cache-first)
      7. Return as dict matching API contract (includes latitude/longitude)
    """
    from backend.ingest.geocode import geocode_address
    from backend.scoring.query import (
        compute_score,
        get_db_connection,
        get_nearby_projects,
        get_neighborhood_context,
    )
    from backend.scoring.rewrite import enrich_top_risk_details

    conn = get_db_connection()
    try:
        coords = geocode_address(address)
        if not coords:
            raise ValueError(f"Could not geocode address: {address!r}")

        lat, lon = coords
        nearby = get_nearby_projects(lat, lon, conn)

        # Neighborhood quality context (data-040).
        # Non-fatal: returns None if neighborhood_quality table is not yet populated.
        neighborhood_context = None
        try:
            neighborhood_context = get_neighborhood_context(lat, lon, conn)
        except Exception as nq_exc:
            log.debug("neighborhood_context lookup skipped: %s", nq_exc)
            try:
                conn.rollback()
            except Exception:
                pass

        result = compute_score(nearby, address)
        result_dict = {
            **asdict(result),
            "mode": "live",
            "fallback_reason": None,
            "latitude": lat,
            "longitude": lon,
            "neighborhood_context": neighborhood_context,
        }

        # Enrich top_risk_details with Claude-rewritten titles and descriptions
        # (data-042).  Cache-first: only calls Claude for project_ids not yet
        # seen.  Non-fatal: falls back gracefully when API key is absent.
        result_dict["top_risk_details"] = enrich_top_risk_details(
            result_dict.get("top_risk_details") or [], conn
        )
    finally:
        conn.close()

    return result_dict


# ---------------------------------------------------------------------------
# Score history helpers  (data-025)
# ---------------------------------------------------------------------------

def _write_score_history(address: str, result: dict) -> None:
    """
    Persist a live /score result to the score_history table.
    Intended for use as a BackgroundTask — failures are logged but not raised.
    Only live-mode scores are written; demo results are silently skipped.
    """
    if result.get("mode") != "live":
        return
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO score_history (address, disruption_score, confidence, mode)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        address,
                        result["disruption_score"],
                        result["confidence"],
                        result.get("mode", "live"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        log.debug("score_history written address=%r score=%s", address, result["disruption_score"])
    except Exception as exc:
        log.warning("score_history write failed address=%r error=%s", address, exc)


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
    background_tasks: BackgroundTasks = None,
) -> dict:
    """
    Return a near-term construction disruption risk score for a Chicago address.

    Geocodes the address, queries nearby projects from Railway Postgres, and
    returns a live score. Raises 422 if the address cannot be geocoded, 503
    on unexpected scoring errors.
    """
    try:
        result = _score_live(address)
        log.info("score address=%r mode=live fallback_reason=None", address)
        if background_tasks is not None:
            background_tasks.add_task(_write_score_history, address, result)
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
# /history endpoint  (data-025)
# Returns recent score history for a given address, newest first.
# Used by the frontend sparkline component to visualise score trend.
# ---------------------------------------------------------------------------

@app.get("/history")
def get_history(
    address: str = Query(..., description="Chicago address to look up"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
) -> dict:
    """
    Return the most recent score history entries for a given address.

    Response shape:
      {
        "address": "<address>",
        "history": [
          { "disruption_score": 62, "confidence": "MEDIUM", "mode": "live", "scored_at": "<iso>" },
          ...
        ]
      }

    Returns an empty history list when the DB is not configured (demo mode).
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
                    SELECT disruption_score, confidence, mode, scored_at
                    FROM score_history
                    WHERE address = %s
                    ORDER BY scored_at DESC
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
                "scored_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
            }
            for row in rows
        ]
        log.info("history address=%r returned=%d rows", address, len(history))
        return {"address": address, "history": history}

    except Exception as exc:
        log.error("history address=%r error=%s", address, exc)
        raise HTTPException(
            status_code=503,
            detail="History service temporarily unavailable.",
        ) from exc


# ---------------------------------------------------------------------------
# /health endpoint (app-020)
# Lightweight liveness check — responds instantly so Railway's healthchecker
# never times out waiting for a DB connection.  DB connectivity is reported
# via /health/db (a separate, slower probe for operators / CI).
# Never raises 5xx. DB state is reflected in the response body of /health/db.
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """
    Lightweight liveness probe for Railway's healthchecker.

    Responds immediately — does NOT attempt a DB connection so the endpoint
    always returns within milliseconds regardless of DB state.

    Fields:
      status:        always "ok"
      mode:          "live" if DATABASE_URL or POSTGRES_HOST is set, else "unconfigured"
      db_configured: true if DATABASE_URL or POSTGRES_HOST env var is present
    """
    db_configured = _is_db_configured()
    return {
        "status": "ok",
        "mode": "live" if db_configured else "unconfigured",
        "db_configured": db_configured,
    }


@app.get("/health/db")
def health_db() -> dict:
    """
    DB connectivity probe for operators and CI.  Separate from /health so the
    Railway liveness check is never blocked by a slow or unavailable DB.

    Fields:
      status:             always "ok" (endpoint never hard-fails)
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
_NOMINATIM_VIEWBOX = "-91.5100,42.5100,-87.0200,36.9700"
# Photon: bbox = minLon,minLat,maxLon,maxLat
_PHOTON_BBOX = "-91.5100,36.9700,-87.0200,42.5100"
# Illinois lat/lon bounds for bbox-based filtering
_IL_LAT = (36.9700, 42.5100)
_IL_LON = (-91.5100, -87.0200)


def _in_illinois(lat: float, lon: float) -> bool:
    return _IL_LAT[0] <= lat <= _IL_LAT[1] and _IL_LON[0] <= lon <= _IL_LON[1]


# Directional prefixes to strip when extracting the bare street-name fragment.
_DIRECTIONAL = re.compile(
    r"^(?:north|south|east|west|n\.?|s\.?|e\.?|w\.?)\s+",
    re.IGNORECASE,
)


def _street_prefix(query: str) -> str | None:
    """
    Extract the partial street-name fragment from a raw query so suggestions
    can be post-filtered to only streets whose name starts with that fragment.

    '679 North Peo'  → 'peo'
    '100 W Rand'     → 'rand'
    'Michigan Ave'   → 'michigan'
    '1600 W Chicago' → 'chicago'   (fragment long enough to be useful)
    """
    q = query.strip()
    # Drop trailing city/state suffixes the caller may have appended.
    q = re.sub(r",?\s*illinois.*$", "", q, flags=re.IGNORECASE)
    q = re.sub(r",?\s*[a-z ]+,\s*il\b.*$", "", q, flags=re.IGNORECASE)
    q = re.sub(r",?\s*il\b.*$", "", q, flags=re.IGNORECASE)
    # Drop leading house number.
    q = re.sub(r"^\d+\s*", "", q)
    # Drop directional prefix (North, S, W., etc.).
    q = _DIRECTIONAL.sub("", q).strip()
    # Only use the fragment if it's at least 2 chars (avoids over-filtering).
    return q.lower() if len(q) >= 2 else None


def _parse_nominatim(results: list, street_frag: str | None = None) -> list[str]:
    """Format Nominatim results as 'number road, City, IL' strings.

    If *street_frag* is given, only keep results whose road name starts with
    that fragment (case-insensitive). This prevents Nominatim from returning
    Milwaukee Ave when the user typed 'Peo' (→ Peoria).
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for r in results:
        try:
            if not _in_illinois(float(r["lat"]), float(r["lon"])):
                continue
        except (KeyError, ValueError):
            continue
        addr = r.get("address", {})
        house = addr.get("house_number", "")
        road = addr.get("road") or addr.get("pedestrian") or addr.get("highway") or ""
        if not road:
            continue
        if street_frag and not road.lower().startswith(street_frag):
            continue
        city = addr.get("city") or addr.get("town") or addr.get("village") or ""
        loc = f"{city}, IL" if city else "IL"
        formatted = f"{house} {road}, {loc}" if house else f"{road}, {loc}"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


def _parse_photon(features: list, street_frag: str | None = None) -> list[str]:
    """Format Photon GeoJSON features as 'number road, City, IL' strings.

    If *street_frag* is given, only keep results whose street name starts with
    that fragment (case-insensitive).
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for f in features:
        props = f.get("properties", {})
        if props.get("countrycode", "").upper() != "US":
            continue
        coords = f.get("geometry", {}).get("coordinates", [])
        try:
            lon, lat = float(coords[0]), float(coords[1])
            if not _in_illinois(lat, lon):
                continue
        except (IndexError, ValueError, TypeError):
            continue
        street = props.get("street", "")
        if not street:
            continue
        if street_frag and not street.lower().startswith(street_frag):
            continue
        house = props.get("housenumber", "")
        city = props.get("city", "")
        loc = f"{city}, IL" if city else "IL"
        formatted = f"{house} {street}, {loc}" if house else f"{street}, {loc}"
        if formatted not in seen:
            seen.add(formatted)
            suggestions.append(formatted)
    return suggestions[:5]


# ---------------------------------------------------------------------------
# /neighborhood/<slug> endpoint (data-026)
# Returns all live disruption projects within a neighborhood bounding box
# plus neighborhood metadata. Used by the /neighborhood/[slug] frontend pages.
#
# Bounding boxes are defined as (min_lat, min_lon, max_lat, max_lon).
# Neighborhoods were chosen to cover the most active permit/closure corridors.
# ---------------------------------------------------------------------------

_NEIGHBORHOODS: dict[str, dict] = {
    "wicker-park": {
        "name": "Wicker Park",
        "description": "Dense mixed-use neighborhood with high permit activity along Milwaukee Ave.",
        "center": {"lat": 41.9088, "lon": -87.6776},
        "bbox": {"min_lat": 41.8990, "min_lon": -87.6950, "max_lat": 41.9180, "max_lon": -87.6600},
        # Representative median disruption score for this neighborhood.
        # Source: manual calibration from permit density; replace with a live
        # score_history aggregate once addresses are geocoded at save time.
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
    # ── Expansion to 20 neighborhoods (data-014) ─────────────────────────────
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


@app.get("/neighborhood/{slug}")
def get_neighborhood(slug: str) -> dict:
    """
    Return neighborhood metadata and all active disruption projects within
    the neighborhood bounding box.

    slug:      one of the 8 pre-defined Chicago neighborhood slugs
    Returns:
      slug, name, description, center, bbox, projects (list), project_count, mode
    """
    neighborhood = _NEIGHBORHOODS.get(slug)
    if neighborhood is None:
        raise HTTPException(
            status_code=404,
            detail=f"Neighborhood '{slug}' not found. Valid slugs: {', '.join(_NEIGHBORHOODS)}",
        )

    bbox = neighborhood["bbox"]
    projects = _get_projects_in_bbox(
        bbox["min_lat"], bbox["min_lon"], bbox["max_lat"], bbox["max_lon"]
    )
    mode = "live" if _is_db_configured() else "demo"

    return {
        "slug": slug,
        "name": neighborhood["name"],
        "description": neighborhood["description"],
        "center": neighborhood["center"],
        "bbox": bbox,
        "projects": projects,
        "project_count": len(projects),
        "mode": mode,
        # Median disruption score for addresses in this neighborhood.
        # Currently a calibrated static value; will be replaced by a live
        # score_history aggregate query once address geocoding is stored.
        "median_score": neighborhood.get("median_score"),
        "sample_size": 0,
    }


@app.get("/neighborhoods")
def list_neighborhoods() -> dict:
    """
    Return the list of available neighborhood slugs and their names/centers.
    Used by the frontend to render a neighborhood index.
    """
    return {
        "neighborhoods": [
            {"slug": slug, "name": n["name"], "description": n["description"], "center": n["center"]}
            for slug, n in _NEIGHBORHOODS.items()
        ]
    }


# /neighborhood/{slug}/best-streets endpoint (data-014)
# ---------------------------------------------------------------------------
# Known streets per neighborhood for demo-mode block generation.
# Keys: "quiet" = historically low-activity; "busy" = high-permit corridors.
# ---------------------------------------------------------------------------

_NEIGHBORHOOD_STREETS: dict[str, dict[str, list[str]]] = {
    "wicker-park":      {"quiet": ["N Wood St", "W Schiller St", "N Wolcott Ave", "W Pierce Ave", "N Paulina St"],
                         "busy":  ["N Milwaukee Ave", "N Damen Ave", "W North Ave", "W Division St", "N Ashland Ave"]},
    "logan-square":     {"quiet": ["N Spaulding Ave", "N Drake Ave", "N Sawyer Ave", "N Troy St", "N Kedzie Ave"],
                         "busy":  ["N Milwaukee Ave", "W Logan Blvd", "W Diversey Ave", "W Armitage Ave", "N California Ave"]},
    "river-north":      {"quiet": ["W Superior St", "W Huron St", "W Ohio St", "W Ontario St", "W Erie St"],
                         "busy":  ["N Michigan Ave", "N State St", "W Grand Ave", "W Chicago Ave", "N Orleans St"]},
    "lincoln-park":     {"quiet": ["W Belden Ave", "W Webster Ave", "W Dickens Ave", "N Racine Ave", "W Montana St"],
                         "busy":  ["N Clark St", "N Halsted St", "N Lincoln Ave", "W Diversey Pkwy", "W Fullerton Ave"]},
    "pilsen":           {"quiet": ["S Calumet Ave", "S Loomis St", "S Sangamon St", "S Morgan St", "S Carpenter St"],
                         "busy":  ["W Cermak Rd", "W 18th St", "W Blue Island Ave", "S Halsted St", "W 21st St"]},
    "loop":             {"quiet": ["N Franklin St", "N Wells St", "N LaSalle St", "N Dearborn St", "N Clark St"],
                         "busy":  ["N State St", "N Michigan Ave", "W Wacker Dr", "W Lake St", "W Madison St"]},
    "uptown":           {"quiet": ["W Winona St", "W Carmen Ave", "W Agatite Ave", "W Gunnison St", "W Sunnyside Ave"],
                         "busy":  ["N Broadway", "W Lawrence Ave", "W Wilson Ave", "N Sheridan Rd", "N Clark St"]},
    "bridgeport":       {"quiet": ["S Emerald Ave", "S Stewart Ave", "S Shields Ave", "S Wallace St", "S Princeton Ave"],
                         "busy":  ["S Halsted St", "W Archer Ave", "W 31st St", "W 35th St", "S Wentworth Ave"]},
    "old-town":         {"quiet": ["W Eugenie St", "W Menomonee St", "N Sedgwick St", "W Wisconsin St", "N Hudson Ave"],
                         "busy":  ["N Wells St", "N Clark St", "W North Ave", "W Division St", "N Larrabee St"]},
    "gold-coast":       {"quiet": ["E Schiller St", "E Goethe St", "E Banks St", "E Scott St", "E Bellevue Pl"],
                         "busy":  ["N Lake Shore Dr", "N Michigan Ave", "N Rush St", "N State St", "W Division St"]},
    "streeterville":    {"quiet": ["E Huron St", "E Erie St", "E Ontario St", "E Ohio St", "E Grand Ave"],
                         "busy":  ["N Michigan Ave", "N Lake Shore Dr", "E Illinois St", "E Chicago Ave", "N St Clair St"]},
    "south-loop":       {"quiet": ["S Plymouth Ct", "S Federal St", "S Dearborn St", "S State St", "S Wabash Ave"],
                         "busy":  ["S Michigan Ave", "S Indiana Ave", "W Roosevelt Rd", "S King Dr", "W Cermak Rd"]},
    "andersonville":    {"quiet": ["N Paulina St", "N Ashland Ave", "W Berwyn Ave", "W Catalpa Ave", "W Summerdale Ave"],
                         "busy":  ["N Clark St", "W Foster Ave", "W Balmoral Ave", "W Bryn Mawr Ave", "N Broadway"]},
    "rogers-park":      {"quiet": ["N Glenwood Ave", "N Greenview Ave", "N Paulina St", "W Chase Ave", "W Farwell Ave"],
                         "busy":  ["N Sheridan Rd", "N Clark St", "W Touhy Ave", "W Morse Ave", "W Howard St"]},
    "bucktown":         {"quiet": ["N Hoyne Ave", "N Leavitt St", "W McLean Ave", "N Oakley Ave", "W Moffat St"],
                         "busy":  ["N Damen Ave", "N Milwaukee Ave", "W Fullerton Ave", "W Armitage Ave", "N Western Ave"]},
    "ukrainian-village":{"quiet": ["N Oakley Blvd", "N Leavitt St", "W Iowa St", "W Thomas St", "W Augusta Blvd"],
                         "busy":  ["W Chicago Ave", "W Division St", "N Western Ave", "N Damen Ave", "W Rice St"]},
    "humboldt-park":    {"quiet": ["N Kedzie Ave", "N St Louis Ave", "W Cortez St", "W Thomas St", "W Augusta Blvd"],
                         "busy":  ["N Pulaski Rd", "W Chicago Ave", "W Division St", "N Western Ave", "W North Ave"]},
    "hyde-park":        {"quiet": ["E 53rd St", "E 54th St", "S Blackstone Ave", "S Dorchester Ave", "S Kimbark Ave"],
                         "busy":  ["S Lake Shore Dr", "S King Dr", "E 55th St", "E 63rd St", "S Cottage Grove Ave"]},
    "ravenswood":       {"quiet": ["W Berteau Ave", "W Sunnyside Ave", "N Hermitage Ave", "N Paulina St", "W Leland Ave"],
                         "busy":  ["N Ravenswood Ave", "W Lawrence Ave", "W Montrose Ave", "N Clark St", "W Wilson Ave"]},
    "avondale":         {"quiet": ["N Hamlin Ave", "N Kedzie Ave", "W Waveland Ave", "N Albany Ave", "W Melrose St"],
                         "busy":  ["N Milwaukee Ave", "N Pulaski Rd", "W Belmont Ave", "N Kimball Ave", "W Diversey Ave"]},
}

_BLOCK_IMPACT_WEIGHTS: dict[str, int] = {
    "closure_full": 35,
    "closure_multi_lane": 25,
    "closure_single_lane": 15,
    "demolition": 20,
    "construction": 15,
    "light_permit": 8,
}


def _get_last_ingest_time() -> str:
    """Return the ISO timestamp of the most recent successful ingest run.
    Falls back to the current UTC time if the table is absent or DB is unavailable."""
    import datetime
    if not _is_db_configured():
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(completed_at) FROM ingest_runs WHERE status = 'success'"
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0].replace(microsecond=0).isoformat() + "Z"
        finally:
            conn.close()
    except Exception as exc:
        log.debug("ingest_runs query skipped: %s", exc)
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _extract_street_name(title: str | None) -> str | None:
    """Heuristic: pull the first recognizable street reference out of a permit title."""
    if not title:
        return None
    import re
    m = re.search(
        r"(\d+\s+)?([NSEW]\s+)?[\w\s]+"
        r"(?:Ave|Blvd|Ct|Cir|Dr|Expy|Hwy|Ln|Pkwy|Pl|Rd|St|Ter|Trl|Way)",
        title,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _compute_blocks_from_projects(projects: list[dict]) -> list[dict]:
    """Aggregate raw projects into scored block cells (0.001° grid ≈ 90 m)."""
    cells: dict[tuple[float, float], dict] = {}
    for p in projects:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        key = (round(float(lat), 3), round(float(lon), 3))
        if key not in cells:
            cells[key] = {"score": 0, "count": 0, "street": _extract_street_name(p.get("title"))}
        cells[key]["score"] += _BLOCK_IMPACT_WEIGHTS.get(p.get("impact_type") or "", 8)
        cells[key]["count"] += 1

    blocks = []
    for (clat, _clon), cell in cells.items():
        street = cell["street"] or f"Block near {clat:.3f}°N"
        block_num = (int(abs(clat * 1000)) % 20) * 100 + 1000
        blocks.append({
            "block": f"{street} {block_num}–{block_num + 99}",
            "avg_score": min(100, cell["score"]),
            "active_projects": cell["count"],
        })
    return blocks


def _make_demo_blocks(slug: str, median_score: int) -> list[dict]:
    """Generate plausible block data for demo mode from the street config."""
    streets = _NEIGHBORHOOD_STREETS.get(
        slug,
        {"quiet": ["N Main St", "W Side St", "N Oak Ave", "W Park Pl", "N Elm St"],
         "busy":  ["W Chicago Ave", "N State St", "W Madison St", "N Clark St", "S Michigan Ave"]},
    )
    blocks: list[dict] = []
    for i, street in enumerate(streets["quiet"][:5]):
        base = 1400 + i * 100
        score = max(2, min(18, median_score - 22 + (i % 3) * 4 - (i // 3) * 2))
        blocks.append({"block": f"{street} {base}–{base + 99}", "avg_score": score, "active_projects": 0})
    for i, street in enumerate(streets["busy"][:5]):
        base = 1100 + i * 100
        score = min(92, max(median_score + 18 + i * 6, 45))
        blocks.append({"block": f"{street} {base}–{base + 99}", "avg_score": score, "active_projects": 2 + i // 2})
    return blocks


def _format_month_year(iso: str) -> str:
    """Convert an ISO timestamp to 'March 2026' format."""
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %Y")
    except Exception:
        return "recent"


@app.get("/neighborhood/{slug}/best-streets")
def get_neighborhood_best_streets(slug: str) -> dict:
    """
    Return the 5 quietest and 5 most disrupted blocks in a neighborhood.

    In live mode: aggregates active projects in the bbox into ~90-m grid cells
    and scores each cell by impact type weight.
    In demo mode: returns calibrated static block data derived from known
    high- and low-activity corridors for each neighborhood.

    Returns: slug, name, quietest_blocks, busiest_blocks, last_updated,
             mode, meta_description (unique, generated from real data).
    """
    neighborhood = _NEIGHBORHOODS.get(slug)
    if neighborhood is None:
        raise HTTPException(
            status_code=404,
            detail=f"Neighborhood '{slug}' not found. Valid slugs: {', '.join(_NEIGHBORHOODS)}",
        )

    name = neighborhood["name"]
    last_updated = _get_last_ingest_time()

    if _is_db_configured():
        bbox = neighborhood["bbox"]
        projects = _get_projects_in_bbox(
            bbox["min_lat"], bbox["min_lon"], bbox["max_lat"], bbox["max_lon"]
        )
        all_blocks = _compute_blocks_from_projects(projects)
        mode = "live"
    else:
        all_blocks = _make_demo_blocks(slug, neighborhood.get("median_score", 35))
        mode = "demo"

    quietest = sorted(all_blocks, key=lambda b: b["avg_score"])[:5]
    busiest  = sorted(all_blocks, key=lambda b: b["avg_score"], reverse=True)[:5]
    month_year = _format_month_year(last_updated)

    # Unique meta description generated from the actual block data.
    if quietest and busiest:
        q0, b0 = quietest[0], busiest[0]
        meta_description = (
            f"Find Chicago's quietest streets in {name}. "
            f"{q0['block']} has the lowest disruption score ({q0['avg_score']}/100) "
            f"while {b0['block']} has the highest active construction load "
            f"({b0['avg_score']}/100, {b0['active_projects']} active permit"
            f"{'s' if b0['active_projects'] != 1 else ''}). "
            f"Block-level disruption data for {name}, Chicago — updated {month_year}."
        )
    else:
        meta_description = (
            f"Block-level disruption intelligence for {name}, Chicago. "
            f"Quietest and most disrupted streets updated {month_year}."
        )

    return {
        "slug": slug,
        "name": name,
        "quietest_blocks": quietest,
        "busiest_blocks": busiest,
        "last_updated": last_updated,
        "mode": mode,
        "meta_description": meta_description,
    }


# ---------------------------------------------------------------------------
# /commute endpoint
# Scores the disruption along a commute corridor between two addresses.
# Geocodes both, builds a bounding box, queries active signals in the corridor,
# identifies CTA stations and service alerts, and returns a scored response.
# ---------------------------------------------------------------------------

class CommuteRequest(BaseModel):
    home: str   # origin / home address
    work: str   # destination / workplace address


def _commute_badge(score: int) -> str:
    if score <= 25:
        return "Low"
    if score <= 55:
        return "Moderate"
    return "High"


@app.post("/commute")
def check_commute(body: CommuteRequest) -> dict:
    """
    Score the disruption along a commute corridor between two addresses.

    Steps:
      1. Geocode home + work → (lat, lon) pairs
      2. Build a bounding box (with 0.003° padding) enclosing the corridor
      3. Query all active projects within the bbox via _get_projects_in_bbox
      4. Score the corridor: sum of per-signal impact weights, capped at 100
      5. Identify CTA stations within the bbox
      6. Identify CTA service-alert projects in the bbox (source starts with "cta")
      7. Return score, badge (Low/Moderate/High), signals, and transit alerts

    Falls back to a demo response when DB is not configured or geocoding fails.
    """
    if not _is_db_configured():
        # Demo mode — synthetic corridor between two Chicago landmarks.
        return {
            "home": body.home,
            "work": body.work,
            "commute_score": 38,
            "badge": "Moderate",
            "signals_count": 4,
            "signals": [
                {"title": "W Chicago Ave 2-lane eastbound closure", "impact_type": "closure_multi_lane",
                 "lat": 41.8959, "lon": -87.6594, "source": "chicago_closures"},
                {"title": "Active construction permit near Grand Ave", "impact_type": "construction",
                 "lat": 41.8910, "lon": -87.6462, "source": "chicago_permits"},
                {"title": "Curb lane closure on N State St", "impact_type": "closure_single_lane",
                 "lat": 41.8840, "lon": -87.6280, "source": "chicago_closures"},
                {"title": "Utility work permit on S Wacker Dr", "impact_type": "light_permit",
                 "lat": 41.8788, "lon": -87.6359, "source": "chicago_permits"},
            ],
            "transit_stations": [
                {"name": "Grand", "lat": 41.8915, "lon": -87.6477},
                {"name": "State/Lake", "lat": 41.8858, "lon": -87.6278},
            ],
            "transit_alerts": [],
            "home_coords": None,
            "work_coords": None,
            "mode": "demo",
        }

    try:
        from backend.ingest.geocode import geocode_address

        home_coords = geocode_address(body.home)
        work_coords = geocode_address(body.work)

        if not home_coords or not work_coords:
            missing = "home" if not home_coords else "destination"
            raise HTTPException(
                status_code=422,
                detail=f"Could not geocode {missing} address: "
                       f"{body.home if not home_coords else body.work!r}",
            )

        home_lat, home_lon = home_coords
        work_lat, work_lon = work_coords

        # Build corridor bbox with a small padding so signals on the edges
        # are included. 0.003° ≈ 270 m at Chicago latitude.
        pad = 0.003
        min_lat = min(home_lat, work_lat) - pad
        max_lat = max(home_lat, work_lat) + pad
        min_lon = min(home_lon, work_lon) - pad
        max_lon = max(home_lon, work_lon) + pad

        projects = _get_projects_in_bbox(min_lat, min_lon, max_lat, max_lon)

        # Corridor score: sum of per-signal weights, capped at 100.
        corridor_score = min(
            100,
            sum(_BLOCK_IMPACT_WEIGHTS.get(p.get("impact_type") or "", 8) for p in projects),
        )
        badge = _commute_badge(corridor_score)

        # Separate CTA service alerts from construction/closure signals.
        transit_alerts = [
            p for p in projects
            if (p.get("source") or "").lower().startswith("cta")
        ]
        corridor_signals = [p for p in projects if p not in transit_alerts]

        # Find CTA stations within the bbox.
        transit_stations: list[dict] = []
        try:
            from backend.ingest.cta_alerts import CTA_STATION_COORDS
            for station_name, (slat, slon) in CTA_STATION_COORDS.items():
                if min_lat <= slat <= max_lat and min_lon <= slon <= max_lon:
                    transit_stations.append({"name": station_name, "lat": slat, "lon": slon})
        except Exception as cta_exc:
            log.debug("CTA station lookup skipped: %s", cta_exc)

        log.info(
            "commute home=%r work=%r score=%d badge=%s signals=%d transit_alerts=%d",
            body.home, body.work, corridor_score, badge, len(projects), len(transit_alerts),
        )

        return {
            "home": body.home,
            "work": body.work,
            "commute_score": corridor_score,
            "badge": badge,
            "signals_count": len(projects),
            "signals": [
                {
                    "title": p.get("title"),
                    "impact_type": p.get("impact_type"),
                    "lat": p.get("lat"),
                    "lon": p.get("lon"),
                    "source": p.get("source", ""),
                }
                for p in corridor_signals
            ],
            "transit_stations": transit_stations,
            "transit_alerts": [
                {
                    "title": p.get("title"),
                    "impact_type": p.get("impact_type"),
                    "lat": p.get("lat"),
                    "lon": p.get("lon"),
                    "source": p.get("source", ""),
                }
                for p in transit_alerts
            ],
            "home_coords": {"lat": home_lat, "lon": home_lon},
            "work_coords": {"lat": work_lat, "lon": work_lon},
            "mode": "live",
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("check_commute home=%r work=%r error: %s", body.home, body.work, exc)
        raise HTTPException(status_code=503, detail="Commute scoring temporarily unavailable.") from exc


@app.get("/suggest")
def suggest_addresses(
    q: str = Query(..., min_length=2, description="Partial Chicago address query"),
) -> dict:
    """
    Return up to 5 Chicago address suggestions for a partial address query.
    Used by the frontend autocomplete input.

    Tries Nominatim first; falls back to Photon (komoot) if Nominatim is
    unreachable or returns no results within the Illinois bbox.
    """
    query = q.strip()
    # Bias both geocoders toward Illinois without altering queries that already
    # specify a city/state.
    nominatim_q = query if ", il" in query.lower() else f"{query}, IL"
    photon_q = query if ", il" in query.lower() else f"{query}, IL"

    # Extract the partial street-name fragment so results can be post-filtered.
    # e.g. "679 North Peo" → "peo", preventing Milwaukee/Michigan/etc. showing up.
    street_frag = _street_prefix(query)

    _nom_headers = {"User-Agent": "LivabilityRiskEngine/1.0 (chicago-mvp)"}
    _nom_common = {
        "format": "json",
        "limit": 10,
        "countrycodes": "us",
        "bounded": "1",
        "viewbox": _NOMINATIM_VIEWBOX,
        "addressdetails": "1",
    }

    # 1a. Nominatim free-text search with post-filtering on the street fragment.
    try:
        resp = _requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": nominatim_q, **_nom_common},
            headers=_nom_headers,
            timeout=4,
        )
        if resp.ok:
            suggestions = _parse_nominatim(resp.json(), street_frag)
            if suggestions:
                log.info("suggest q=%r source=nominatim results=%d", q, len(suggestions))
                return {"suggestions": suggestions}
    except Exception as exc:
        log.debug("suggest q=%r nominatim free-text error: %s", q, exc)

    # 1b. Nominatim structured search — better for partial street names.
    #     Strip leading house number and pass it separately so Nominatim
    #     can do a more focused road-name lookup.
    try:
        m = re.match(r"^(\d+)\s+(.*)", query)
        structured_street = m.group(2) if m else query
        resp = _requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "street": structured_street,
                "state": "IL",
                "country": "US",
                **_nom_common,
            },
            headers=_nom_headers,
            timeout=4,
        )
        if resp.ok:
            suggestions = _parse_nominatim(resp.json(), street_frag)
            if suggestions:
                log.info("suggest q=%r source=nominatim-structured results=%d", q, len(suggestions))
                return {"suggestions": suggestions}
    except Exception as exc:
        log.debug("suggest q=%r nominatim structured error: %s", q, exc)

    # 2. Photon fallback
    try:
        resp = _requests.get(
            "https://photon.komoot.io/api/",
            params={
                "q": photon_q,
                "limit": 10,
                "bbox": _PHOTON_BBOX,
                "lang": "en",
            },
            timeout=4,
        )
        if resp.ok:
            suggestions = _parse_photon(resp.json().get("features", []), street_frag)
            log.info("suggest q=%r source=photon results=%d", q, len(suggestions))
            return {"suggestions": suggestions}
    except Exception as exc:
        log.warning("suggest q=%r both geocoders failed, last error: %s", q, exc)

    return {"suggestions": []}


# ---------------------------------------------------------------------------
# /save endpoint (data-021)
# Persists a score result as a shareable report. Returns a UUID.
# When DB is not configured, returns a deterministic demo report_id so the
# frontend save flow can be exercised without a live database.
# ---------------------------------------------------------------------------

_DEMO_REPORT_ID = "00000000-0000-0000-0000-000000000001"


class SaveReportRequest(BaseModel):
    """Score JSON payload to persist as a saved report."""
    address: str
    disruption_score: int
    confidence: str
    severity: dict
    top_risks: list
    explanation: str
    mode: str | None = None
    fallback_reason: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@app.post("/save")
def save_report(body: SaveReportRequest) -> dict:
    """
    Store a score result in the reports table and return a shareable UUID.

    When DB is not configured, returns a demo report_id so the frontend
    save/share flow is exercisable without a live database.
    """
    if not _is_db_configured():
        log.info("save_report address=%r mode=demo", body.address)
        return {"report_id": _DEMO_REPORT_ID}

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        report_id = str(uuid.uuid4())
        score_json = body.model_dump()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO reports (id, address, score_json) VALUES (%s, %s, %s)",
                    (report_id, body.address, score_json),
                )
            conn.commit()
        finally:
            conn.close()
        log.info("save_report address=%r report_id=%s", body.address, report_id)
        return {"report_id": report_id}
    except Exception as exc:
        log.error("save_report error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not save report.") from exc


# ---------------------------------------------------------------------------
# /report/{report_id} endpoint (data-021)
# Fetches a saved report by UUID.
# ---------------------------------------------------------------------------

@app.get("/report/{report_id}")
def get_report(report_id: str) -> dict:
    """
    Return a saved score report by UUID.

    Returns 404 if the report_id does not exist.
    When DB is not configured and the demo report_id is requested, returns
    the canonical demo score so the share flow is exercisable end-to-end.
    """
    if not _is_db_configured():
        if report_id == _DEMO_REPORT_ID:
            return {
                **DEMO_RESPONSE,
                "address": "1600 W Chicago Ave, Chicago, IL",
                "mode": "demo",
                "fallback_reason": "db_not_configured",
                "latitude": 41.8956,
                "longitude": -87.6606,
                "report_id": report_id,
                "created_at": "2026-01-01T00:00:00Z",
            }
        raise HTTPException(status_code=404, detail="Report not found.")

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT score_json, created_at FROM reports WHERE id = %s",
                    (report_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            raise HTTPException(status_code=404, detail="Report not found.")

        score_json, created_at = row
        return {
            **score_json,
            "report_id": report_id,
            "created_at": created_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_report report_id=%r error: %s", report_id, exc)
        raise HTTPException(status_code=503, detail="Could not retrieve report.") from exc


# ---------------------------------------------------------------------------
# /watch endpoints (data-030)
# Score alert watchlist — subscribe an email + threshold to an address.
# When the score crosses the threshold, an entry is written to alert_log
# (email delivery is stubbed for MVP; only logging occurs).
# ---------------------------------------------------------------------------

class WatchRequest(BaseModel):
    email: str
    address: str
    threshold: int  # 0–100 disruption score


@app.post("/watch")
def subscribe_watch(body: WatchRequest) -> dict:
    """
    Subscribe an email address to score alerts for a Chicago address.

    When POST /admin/watch/check is called and the live score for `address`
    meets or exceeds `threshold`, an entry is written to alert_log and a
    stub log message is emitted (email delivery is not yet implemented).

    Returns the watchlist id and the unsubscribe token.
    Requires a live DB. Returns 503 when DB is not configured.
    """
    if not (0 <= body.threshold <= 100):
        raise HTTPException(status_code=422, detail="threshold must be between 0 and 100.")

    if not _is_db_configured():
        # DB not yet live — accept the intent and return a demo success so the
        # email-capture form always works on the free tier. Real alert delivery
        # starts once DATABASE_URL is configured.
        log.info(
            "watch subscribe (demo) email=%r address=%r threshold=%d",
            body.email, body.address, body.threshold,
        )
        return {
            "id": None,
            "email": body.email,
            "address": body.address,
            "threshold": body.threshold,
            "token": None,
            "demo": True,
            "message": "Noted. Alert delivery activates once the live database is connected.",
        }

    try:
        from backend.scoring.query import get_db_connection

        token = secrets.token_hex(32)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO watchlist (email, address, threshold, token)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (email, address)
                    DO UPDATE SET threshold = EXCLUDED.threshold, token = EXCLUDED.token
                    RETURNING id, token
                    """,
                    (body.email, body.address, body.threshold, token),
                )
                row = cur.fetchone()
                watch_id, stored_token = row[0], row[1]
            conn.commit()
        finally:
            conn.close()

        log.info(
            "watch subscribe id=%d email=%r address=%r threshold=%d",
            watch_id, body.email, body.address, body.threshold,
        )
        return {
            "id": watch_id,
            "email": body.email,
            "address": body.address,
            "threshold": body.threshold,
            "token": stored_token,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("subscribe_watch error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not create watchlist entry.") from exc


@app.get("/watch/unsubscribe")
def unsubscribe_watch(token: str = Query(..., description="Unsubscribe token from watchlist entry")) -> dict:
    """
    Remove a watchlist subscription by its unsubscribe token.

    The token is returned by POST /watch and is intended for use in
    unsubscribe links embedded in alert emails. No auth required.
    Returns 404 if the token is not found.
    """
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Watchlist requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM watchlist WHERE token = %s RETURNING id, email, address",
                    (token,),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="Watchlist entry not found.")

        watch_id, email, address = row
        log.info("watch unsubscribe id=%d email=%r address=%r", watch_id, email, address)
        return {"unsubscribed": True, "id": watch_id, "email": email, "address": address}

    except HTTPException:
        raise
    except Exception as exc:
        log.error("unsubscribe_watch error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not process unsubscribe.") from exc


@app.post("/admin/watch/check")
def check_watchlist() -> dict:
    """
    Operator endpoint — score every watched address and fire alerts for entries
    whose score has dropped below their configured threshold (disruption cleared).

    For each triggered entry:
      - Writes a row to alert_log with the current score.
      - Logs a stub email message (actual email delivery not yet implemented).

    Returns a summary of alerts fired in this run.
    Intended to be called on a schedule (e.g. daily cron) or manually by ops.
    Requires a live DB.
    """
    if not _is_db_configured():
        raise HTTPException(
            status_code=503,
            detail="Watchlist requires a live database. Configure DATABASE_URL to enable.",
        )

    try:
        from backend.scoring.query import get_db_connection

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, address, threshold FROM watchlist")
                entries = cur.fetchall()
        finally:
            conn.close()

        alerts_fired = []

        for watch_id, email, address, threshold in entries:
            try:
                result = _score_live(address)
                score = result.get("disruption_score")
                if score is None:
                    continue

                if score < threshold:
                    # Log alert — email delivery stubbed.
                    log.info(
                        "ALERT [stub] watch_id=%d email=%r address=%r "
                        "score=%d threshold=%d — would send alert email",
                        watch_id, email, address, score, threshold,
                    )

                    conn2 = get_db_connection()
                    try:
                        with conn2.cursor() as cur2:
                            cur2.execute(
                                "INSERT INTO alert_log (watchlist_id, score) VALUES (%s, %s)",
                                (watch_id, score),
                            )
                        conn2.commit()
                    finally:
                        conn2.close()

                    alerts_fired.append({
                        "watch_id": watch_id,
                        "email": email,
                        "address": address,
                        "score": score,
                        "threshold": threshold,
                    })
            except Exception as exc:
                log.warning("check_watchlist entry id=%d error: %s", watch_id, exc)
                continue

        log.info("check_watchlist complete entries=%d alerts_fired=%d", len(entries), len(alerts_fired))
        return {
            "entries_checked": len(entries),
            "alerts_fired": len(alerts_fired),
            "alerts": alerts_fired,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_report report_id=%r error: %s", report_id, exc)
        raise HTTPException(status_code=503, detail="Could not retrieve report.") from exc


# ---------------------------------------------------------------------------
# /export/csv endpoint (data-029)
# Returns a CSV download for a scored address.
# ---------------------------------------------------------------------------

@app.get("/export/csv")
def export_csv(
    address: str = Query(..., description="Chicago address to export"),
) -> Response:
    """
    Return a CSV download for a scored address.
    Calls live scoring when DB is configured; falls back to demo data otherwise.
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
