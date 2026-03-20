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

import logging
import os
import secrets
from dataclasses import asdict

import requests as _requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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

@app.get("/score")
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
        raise HTTPException(
            status_code=503,
            detail="Watchlist requires a live database. Configure DATABASE_URL to enable.",
        )

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
    whose score meets or exceeds their configured threshold.

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

                if score >= threshold:
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
        log.error("check_watchlist error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not run watchlist check.") from exc
