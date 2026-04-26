"""
backend/app/main.py
tasks: app-001, app-002, app-008, app-019, app-020, app-021, app-023, data-016, data-030
lane: app

FastAPI /score endpoint -- live scoring against the Railway Postgres+PostGIS DB.
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
import csv
import datetime
import hashlib
import time
import requests as _requests
import io
import json
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.app.deps import _is_db_configured, require_api_key, verify_api_key, _build_demo_response, DEMO_RESPONSE, _require_api_key_enabled, _hash_key, _generate_api_key
from backend.app.services.clerk import _resolve_clerk_email, _verify_clerk_claims
from backend.app.address_normalization import (
    DIRECTION_NORMALIZATION as _DIRECTION_NORMALIZATION,
    STREET_SUFFIX_NORMALIZATION as _STREET_SUFFIX_NORMALIZATION,
    build_address_search_tokens,
    normalize_address_query,
    normalize_address_record,
)

log = logging.getLogger(__name__)

app = FastAPI(title="Livability Risk Engine")

# ---------------------------------------------------------------------------
# Router includes -- extracted route modules
# ---------------------------------------------------------------------------
from backend.app.routes.auth import router as _auth_router
from backend.app.routes.dashboard import router as _dashboard_router
from backend.app.routes.keys import router as _keys_router
from backend.app.routes.map import router as _map_router
from backend.app.routes.neighborhood import router as _neighborhood_router
from backend.app.routes.reports import router as _reports_router
from backend.app.routes.score import router as _score_router
from backend.app.routes.search import router as _search_router
from backend.app.routes.watchlist import router as _watchlist_router

app.include_router(_auth_router)
app.include_router(_dashboard_router)
app.include_router(_keys_router)
app.include_router(_map_router)
app.include_router(_neighborhood_router)
app.include_router(_reports_router)
app.include_router(_score_router)
app.include_router(_search_router)
app.include_router(_watchlist_router)

# Log env var configuration state at startup so Railway logs surface
# missing-variable problems immediately (values are never logged).
logging.basicConfig(level=logging.INFO)
log.info(
    "startup config: DATABASE_URL=%s CLERK_SECRET_KEY=%s REQUIRE_API_KEY=%s FRONTEND_ORIGIN=%s",
    "set" if os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST") else "MISSING",
    "set" if os.environ.get("CLERK_SECRET_KEY") else "MISSING",
    os.environ.get("REQUIRE_API_KEY", "false"),
    os.environ.get("FRONTEND_ORIGIN", "(not set -- using hardcoded default)"),
)


# ---------------------------------------------------------------------------
# Startup migrations
# ---------------------------------------------------------------------------

def _run_startup_migrations() -> None:
    """Idempotently create tables/columns that may be missing from the live DB."""
    db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST")
    if not db_url:
        log.info("startup_migrations: DB not configured, skipping")
        return
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id                TEXT        PRIMARY KEY,
                        email             TEXT        NOT NULL,
                        subscription_tier TEXT        NOT NULL DEFAULT 'free',
                        created_at        TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS users_email_idx ON users (email)")
                cur.execute("""
                    ALTER TABLE api_keys
                    ADD COLUMN IF NOT EXISTS user_id TEXT REFERENCES users(id) ON DELETE SET NULL
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS api_keys_user_id_idx ON api_keys (user_id)
                    WHERE user_id IS NOT NULL
                """)
            conn.commit()
            log.info("startup_migrations: OK")
        finally:
            conn.close()
    except Exception as exc:
        log.error("startup_migrations: failed (non-fatal): %s", exc)


_run_startup_migrations()

# Pre-warm the address index cache so the first autocomplete request is fast.
try:
    _get_address_rows()
    log.info("startup: address index cache warmed")
except Exception as _warm_exc:
    log.debug("startup: address cache warm skipped: %s", _warm_exc)

# ---------------------------------------------------------------------------
# CORS middleware
# Allows the Next.js dev server (localhost:3000) to call the API directly.
# In production, set FRONTEND_ORIGIN to the deployed Vercel domain, e.g.:
#   FRONTEND_ORIGIN=https://livability-risk-engine.vercel.app
# ---------------------------------------------------------------------------

_allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Hardcoded production Vercel URL as a fallback so CORS works even when
    # FRONTEND_ORIGIN is not set in Railway.
    "https://livability-risk-engine.vercel.app",
]
_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
if _frontend_origin and _frontend_origin not in _allowed_origins:
    _allowed_origins.append(_frontend_origin)

# Allow all Vercel preview/production deployments automatically so the
# frontend works before FRONTEND_ORIGIN is explicitly configured in Railway.
_allow_origin_regex = r"https://livability-risk-engine.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_allow_origin_regex,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Explicit CORS preflight handler
#
# Railway's proxy sometimes returns 503 on OPTIONS requests before they reach
# FastAPI's CORSMiddleware (e.g. during cold starts or health-check windows).
# This route handler catches all OPTIONS preflights at the application layer
# and responds immediately with the correct CORS headers, bypassing any
# proxy-level interference.  It must be registered as a route (not middleware)
# so FastAPI handles it before the request reaches the proxy error path.
# ---------------------------------------------------------------------------

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str, request: Request) -> JSONResponse:
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, X-API-Key",
            "Access-Control-Max-Age": "86400",
        },
    )


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """
    Lightweight liveness probe for Railway's healthchecker.

    Responds immediately -- does NOT attempt a DB connection so the endpoint
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
      last_ingest_at:     ISO timestamp of the most recent finished ingest run (null if none)
      last_ingest_status: "success" | "failed" | "running" from the most recent run (null if none)
      last_ingest_count:  active project count recorded at end of the last run (null if none)
    """
    db_configured = _is_db_configured()
    db_connection = False
    db_error = None
    last_ingest_at = None
    last_ingest_status = None
    last_ingest_count = None

    if db_configured:
        try:
            from backend.scoring.query import get_db_connection
            conn = get_db_connection()
            db_connection = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT finished_at, status, record_count
                           FROM ingest_runs
                           WHERE finished_at IS NOT NULL
                           ORDER BY finished_at DESC LIMIT 1"""
                    )
                    row = cur.fetchone()
                    if row:
                        last_ingest_at = row[0].isoformat() if row[0] else None
                        last_ingest_status = row[1]
                        last_ingest_count = row[2]
            except Exception:
                pass  # ingest_runs table may not exist on first deploy
            finally:
                conn.close()
        except Exception as exc:
            db_error = str(exc)
            db_connection = False
    response: dict = {
        "status": "ok",
        "db_configured": db_configured,
        "db_connection": db_connection,
        "last_ingest_at": last_ingest_at,
        "last_ingest_status": last_ingest_status,
        "last_ingest_count": last_ingest_count,
    }
    if db_error is not None:
        response["db_error"] = db_error
    return response


@app.post("/score/batch", dependencies=[Depends(require_api_key)])
class BatchScoreRequest(BaseModel):
    addresses: list[str]

def post_score_batch(
    body: BatchScoreRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Score multiple Chicago addresses in a single request.

    Request body:
      {"addresses": ["addr1", "addr2", ...]}   (max 200 addresses)

    Response:
      {
        "batch_id": "<uuid>",
        "scored":   N,
        "failed":   N,
        "results":  [{address, disruption_score, confidence, severity,
                      top_risks, explanation, mode, error?}, ...]
      }

    - Addresses are geocoded and scored in parallel (up to 10 concurrent workers).
    - Per-address failures (geocode failure, scoring error) are returned inline
      with an "error" key rather than failing the whole request.
    - API key is always required regardless of REQUIRE_API_KEY env var.
    - Results are written to score_history with a shared batch_id.
    """
    addresses = body.addresses
    if len(addresses) > _BATCH_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"Batch limit is {_BATCH_MAX} addresses; {len(addresses)} submitted.",
        )
    if not addresses:
        raise HTTPException(status_code=422, detail="At least one address is required.")

    batch_id = str(uuid.uuid4())
    results: list[dict] = [{}] * len(addresses)

    with ThreadPoolExecutor(max_workers=min(_BATCH_WORKERS, len(addresses))) as pool:
        futures = {pool.submit(_score_one, addr): i for i, addr in enumerate(addresses)}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    scored = sum(1 for r in results if r.get("error") is None)
    failed = len(results) - scored

    log.info("score_batch batch_id=%s total=%d scored=%d failed=%d", batch_id, len(addresses), scored, failed)
    background_tasks.add_task(_write_batch_history, results, batch_id)

    return {
        "batch_id": batch_id,
        "scored": scored,
        "failed": failed,
        "results": results,
    }


# CSV column order for /score/batch/csv output.
_CSV_FIELDNAMES = [
    "address",
    "disruption_score",
    "confidence",
    "severity_noise",
    "severity_traffic",
    "severity_dust",
    "top_risk_1",
    "top_risk_2",
    "top_risk_3",
    "error",
]


def _result_to_csv_row(r: dict) -> dict:
    """Flatten a single score result into a CSV-ready dict."""
    sev = r.get("severity") or {}
    risks = r.get("top_risks") or []
    return {
        "address":          r.get("address", ""),
        "disruption_score": "" if r.get("disruption_score") is None else r["disruption_score"],
        "confidence":       r.get("confidence", ""),
        "severity_noise":   sev.get("noise", ""),
        "severity_traffic": sev.get("traffic", ""),
        "severity_dust":    sev.get("dust", ""),
        "top_risk_1":       risks[0] if len(risks) > 0 else "",
        "top_risk_2":       risks[1] if len(risks) > 1 else "",
        "top_risk_3":       risks[2] if len(risks) > 2 else "",
        "error":            r.get("error", ""),
    }


@app.post("/score/batch/csv", dependencies=[Depends(require_api_key)])
async def post_score_batch_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV file with one address per row"),
) -> StreamingResponse:
    """
    Score addresses from a CSV upload and return results as a CSV download.

    Input CSV format (UTF-8):
      - One address per row.
      - Optional header row: if the first row contains "address" (case-insensitive),
        it is treated as a header and skipped.
      - Maximum 200 addresses (rows beyond 200 are ignored with a warning logged).

    Output CSV columns:
      address, disruption_score, confidence,
      severity_noise, severity_traffic, severity_dust,
      top_risk_1, top_risk_2, top_risk_3, error

    - API key is always required.
    - Per-address failures appear as rows with an "error" value and empty score fields.
    - Results are written to score_history with a shared batch_id.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handle BOM from Excel exports
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    addresses: list[str] = []
    for row in reader:
        if not row:
            continue
        cell = row[0].strip()
        if not cell:
            continue
        # Skip header row.
        if not addresses and cell.lower() in ("address", "addresses"):
            continue
        addresses.append(cell)
        if len(addresses) >= _BATCH_MAX:
            log.warning("score_batch_csv: input truncated to %d addresses", _BATCH_MAX)
            break

    if not addresses:
        raise HTTPException(status_code=422, detail="No addresses found in uploaded CSV.")

    batch_id = str(uuid.uuid4())
    results: list[dict] = [{}] * len(addresses)

    with ThreadPoolExecutor(max_workers=min(_BATCH_WORKERS, len(addresses))) as pool:
        futures = {pool.submit(_score_one, addr): i for i, addr in enumerate(addresses)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    scored = sum(1 for r in results if r.get("error") is None)
    log.info("score_batch_csv batch_id=%s total=%d scored=%d", batch_id, len(addresses), scored)
    background_tasks.add_task(_write_batch_history, results, batch_id)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for r in results:
        writer.writerow(_result_to_csv_row(r))

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"livability_scores_{batch_id[:8]}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class MapNarrationSignal(BaseModel):
    lat: float
    lon: float
    impact_type: str
    title: str
    source: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    distance_m: Optional[float] = None


class MapNarrationRequest(BaseModel):
    address: str
    interaction_type: str  # default_load | signal_click | map_pan
    signals: list[MapNarrationSignal]
    top_signal_title: Optional[str] = None
    clicked_signal: Optional[MapNarrationSignal] = None
    original_score: Optional[int] = None
    current_lat: Optional[float] = None
    current_lon: Optional[float] = None


def _calmer_direction(lat: float, lon: float, signals: list[dict]) -> str:
    """
    Pick the cardinal direction with the fewest nearby signals.
    Used to provide a directional "calmer area" hint in map narration.
    """
    if not signals:
        return "north"

    counts = {"north": 0, "south": 0, "east": 0, "west": 0}
    for s in signals:
        slat = float(s.get("lat", lat))
        slon = float(s.get("lon", lon))
        if slat >= lat:
            counts["north"] += 1
        else:
            counts["south"] += 1
        if slon >= lon:
            counts["east"] += 1
        else:
            counts["west"] += 1

    return min(counts, key=lambda k: counts[k])


@app.post("/map/narrate")
def narrate_map(body: MapNarrationRequest, _: None = Depends(verify_api_key)) -> dict:
    """
    Internal map narrator endpoint.
    Returns {"narration": <2-3 sentence summary>} or {"narration": null} on any
    failure so the frontend can fail silently and hide the panel.
    """
    if not body.signals:
        return {"narration": None}

    # Compute score for the panned-to map center when available.
    current_score: Optional[int] = None
    if (
        body.interaction_type == "map_pan"
        and body.current_lat is not None
        and body.current_lon is not None
        and _is_db_configured()
    ):
        try:
            from backend.scoring.query import compute_score, get_db_connection, get_nearby_projects
            conn_pan = get_db_connection()
            try:
                nearby_pan = get_nearby_projects(body.current_lat, body.current_lon, conn_pan)
                current_score = compute_score(nearby_pan, body.address).disruption_score
            finally:
                conn_pan.close()
        except Exception as exc:
            log.debug("map narrator pan-score lookup skipped: %s", exc)

    signals = [s.model_dump() for s in body.signals]
    clicked_signal = body.clicked_signal.model_dump() if body.clicked_signal else None

    try:
        from backend.scoring.query import get_db_connection
        from backend.scoring.rewrite import get_map_narration

        conn = get_db_connection() if _is_db_configured() else None
        try:
            narration = get_map_narration(
                address=body.address,
                signals=signals,
                interaction_type=body.interaction_type,
                top_signal_title=body.top_signal_title or signals[0].get("title", "nearby disruption"),
                calmer_direction=_calmer_direction(
                    body.current_lat or signals[0]["lat"],
                    body.current_lon or signals[0]["lon"],
                    signals,
                ),
                clicked_signal=clicked_signal,
                original_score=body.original_score,
                current_score=current_score,
                conn=conn,
            )
            return {"narration": narration}
        finally:
            if conn:
                conn.close()
    except Exception as exc:
        log.debug("map narrator unavailable: %s", exc)
        return {"narration": None}


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
    address: str | None = Query(None, description="US address to score"),
    canonical_id: str | None = Query(None, description="Canonical address identifier from /suggest"),
    lat: float | None = Query(None, description="Latitude override from selected suggestion"),
    lon: float | None = Query(None, description="Longitude override from selected suggestion"),
    background_tasks: BackgroundTasks = None,
) -> dict:
    """
    Return a near-term construction disruption risk score for a US address.

    Geocodes the address, queries nearby projects from Railway Postgres, and
    returns a live score. When the address is in a city we haven't ingested data
    for yet, returns score=0 with fallback_reason="city_not_covered".
    Raises 422 if the address cannot be geocoded, 503 on unexpected scoring errors.
    """
    resolved_address = (address or "").strip() or None
    resolved_coords: tuple[float, float] | None = None
    resolution_source = "address_text"

    if canonical_id:
        row = _address_row_by_canonical_id(canonical_id)
        _debug_search_flow("SCORE_RESOLUTION", canonical_id=canonical_id, matched=bool(row))
        if row:
            resolved_address = row.get("display_address") or resolved_address
            if row.get("lat") is not None and row.get("lon") is not None:
                resolved_coords = (float(row["lat"]), float(row["lon"]))
            resolution_source = "canonical_id"
        elif canonical_id.startswith("geo_"):
            # Geocoder-derived canonical_id — not stored in our DB index.
            # Fall through to address text + any lat/lon provided by the caller.
            resolution_source = "address_text"
        else:
            raise HTTPException(status_code=422, detail="Unknown canonical_id for score lookup.")

    if lat is not None and lon is not None:
        resolved_coords = (float(lat), float(lon))
        resolution_source = "lat_lon"

    if not resolved_address:
        if canonical_id and resolved_address is None:
            # Already handled above, but keep the failure explicit.
            raise HTTPException(status_code=422, detail="Canonical score lookup missing display address.")
        raise HTTPException(status_code=422, detail="Provide address or canonical_id for score lookup.")

    _debug_search_flow(
        "SCORE_REQUEST",
        source=resolution_source,
        canonical_id=canonical_id,
        address=resolved_address,
        has_coords=bool(resolved_coords),
        lat=resolved_coords[0] if resolved_coords else None,
        lon=resolved_coords[1] if resolved_coords else None,
    )

    try:
        result = _score_live(resolved_address, coords=resolved_coords)
        log.info("score address=%r mode=live fallback_reason=None source=%s", resolved_address, resolution_source)
        if background_tasks is not None:
            background_tasks.add_task(_write_score_history, resolved_address, result)
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        log.warning("score address=%r geocode_failed error=%s", resolved_address, exc)
        raise HTTPException(
            status_code=422,
            detail=f"Could not geocode address: {exc}",
        ) from exc
    except Exception as exc:
        log.error("score address=%r unexpected scoring error: %s", resolved_address, exc)
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
                    SELECT disruption_score, livability_score, confidence, mode, scored_at
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
                "livability_score": row[1],
                "confidence": row[2],
                "mode": row[3],
                "scored_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
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
# /score-trend endpoint  (data-062)
# Aggregates score_history by day for all addresses within radius_m of a
# lat/lon point — used by the frontend to render an area-level disruption
# trend sparkline independent of whether the exact address has been searched
# before.
# ---------------------------------------------------------------------------

@app.get("/score-trend")
def get_score_trend(
    lat: float = Query(..., description="Latitude of the point of interest"),
    lon: float = Query(..., description="Longitude of the point of interest"),
    radius_m: int = Query(1000, ge=100, le=5000, description="Search radius in metres"),
    days: int = Query(30, ge=7, le=90, description="Number of days to look back"),
) -> dict:
    """
    Return a daily aggregated disruption/livability trend for all scored
    addresses within radius_m metres of (lat, lon) over the past `days` days.

    Uses haversine distance math (no PostGIS required) to filter rows.

    Response shape:
      {
        "lat": 41.89, "lon": -87.65, "radius_m": 1000, "days": 30,
        "trend": [
          { "day": "2026-02-22", "avg_disruption": 45, "avg_livability": 52, "sample_count": 3 },
          ...
        ]
      }

    Returns an empty trend list when the DB is not configured or no nearby
    history exists.
    """
    if not _is_db_configured():
        return {"lat": lat, "lon": lon, "radius_m": radius_m, "days": days, "trend": []}

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            # Bounding box pre-filter (cheap) then haversine for accuracy.
            lat_delta = radius_m / 111_320.0
            lon_delta = radius_m / (111_320.0 * abs(math.cos(math.radians(lat))) + 1e-9)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        date_trunc('day', scored_at AT TIME ZONE 'America/Chicago')::date AS day,
                        round(avg(disruption_score))::int   AS avg_disruption,
                        round(avg(livability_score))::int   AS avg_livability,
                        count(*)::int                       AS sample_count
                    FROM score_history
                    WHERE
                        latitude  IS NOT NULL
                        AND longitude IS NOT NULL
                        AND latitude  BETWEEN %s AND %s
                        AND longitude BETWEEN %s AND %s
                        AND scored_at >= now() - (%s || ' days')::interval
                        AND 6371000.0 * 2.0 * asin(
                            sqrt(
                                power(sin(radians((latitude  - %s) / 2.0)), 2) +
                                cos(radians(%s)) * cos(radians(latitude)) *
                                power(sin(radians((longitude - %s) / 2.0)), 2)
                            )
                        ) <= %s
                    GROUP BY day
                    ORDER BY day ASC
                    """,
                    (
                        lat - lat_delta, lat + lat_delta,
                        lon - lon_delta, lon + lon_delta,
                        days,
                        lat, lat, lon,
                        radius_m,
                    ),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        trend = [
            {
                "day": str(row[0]),
                "avg_disruption": row[1],
                "avg_livability": row[2],
                "sample_count": row[3],
            }
            for row in rows
        ]
        log.info("score_trend lat=%.4f lon=%.4f radius=%dm days=%d returned=%d buckets",
                 lat, lon, radius_m, days, len(trend))
        return {"lat": lat, "lon": lon, "radius_m": radius_m, "days": days, "trend": trend}

    except Exception as exc:
        log.error("score_trend error lat=%.4f lon=%.4f: %s", lat, lon, exc)
        raise HTTPException(
            status_code=503,
            detail="Score trend service temporarily unavailable.",
        ) from exc


# ---------------------------------------------------------------------------
# /nearby-amenities endpoint  (data-064)
# Returns OSM walkable amenities near a lat/lon, with a 0–100 richness score.
# Results are cached in amenity_cache for 7 days (keyed on 0.01° bucket).
# ---------------------------------------------------------------------------

_AMENITY_CACHE_TTL_DAYS = 7


@app.get("/nearby-amenities")
def get_nearby_amenities(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
) -> dict:
    """
    Return walkable amenity data (parks, grocery, transit, restaurants,
    pharmacies) near (lat, lon) from OpenStreetMap via the Overpass API.

    Results are cached per 0.01° grid cell (~800 m) for 7 days so repeat
    requests for nearby addresses are instant.

    Response shape:
      {
        "amenity_score": 75,          // 0-100; null when Overpass unavailable
        "categories": {
          "transit":    [{"name": "...", "lat": ..., "lon": ..., "distance_m": 210, "category": "transit"}, ...],
          "grocery":    [...],
          "park":       [...],
          "restaurant": [...],
          "pharmacy":   [...],
        }
      }

    Returns {"amenity_score": null, "categories": {}} on any error.
    """
    _EMPTY = {"amenity_score": None, "categories": {}}

    lat_b = round(lat, 2)
    lon_b = round(lon, 2)

    # ── Cache lookup ──────────────────────────────────────────────────────────
    if _is_db_configured():
        try:
            from backend.scoring.query import get_db_connection
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT amenities, amenity_score
                        FROM amenity_cache
                        WHERE lat_bucket = %s AND lon_bucket = %s
                          AND fetched_at >= now() - INTERVAL '7 days'
                        """,
                        (lat_b, lon_b),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()

            if row:
                log.debug("amenity_cache hit lat_b=%s lon_b=%s", lat_b, lon_b)
                return {"amenity_score": row[1], "categories": row[0]}
        except Exception as cache_exc:
            log.debug("amenity_cache lookup failed: %s", cache_exc)

    # ── Overpass fetch ────────────────────────────────────────────────────────
    try:
        from backend.ingest.osm_amenities import fetch_amenities
        result = fetch_amenities(lat, lon)
    except Exception as fetch_exc:
        log.warning("nearby_amenities Overpass fetch failed lat=%s lon=%s: %s", lat, lon, fetch_exc)
        return _EMPTY

    # ── Cache write ───────────────────────────────────────────────────────────
    if _is_db_configured():
        try:
            from backend.scoring.query import get_db_connection
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO amenity_cache (lat_bucket, lon_bucket, amenities, amenity_score)
                        VALUES (%s, %s, %s::jsonb, %s)
                        ON CONFLICT (lat_bucket, lon_bucket) DO UPDATE SET
                            amenities     = EXCLUDED.amenities,
                            amenity_score = EXCLUDED.amenity_score,
                            fetched_at    = now()
                        """,
                        (lat_b, lon_b, json.dumps(result["categories"]), result["amenity_score"]),
                    )
                conn.commit()
            finally:
                conn.close()
            log.info("amenity_cache stored lat_b=%s lon_b=%s score=%s", lat_b, lon_b, result["amenity_score"])
        except Exception as write_exc:
            log.warning("amenity_cache write failed: %s", write_exc)

    return result


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
      last_ingest_at:     ISO timestamp of the most recent finished ingest run (null if none)
      last_ingest_status: "success" | "failed" | "running" from the most recent run (null if none)
      last_ingest_count:  active project count recorded at end of the last run (null if none)
    """
    # task: data-041 — add last_ingest_at and last_ingest_status from ingest_runs
    db_configured = _is_db_configured()
    db_connection = False
    db_error = None
    last_ingest_at = None
    last_ingest_status = None
    last_ingest_count = None

    if db_configured:
        try:
            from backend.scoring.query import get_db_connection
            conn = get_db_connection()
            db_connection = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT finished_at, status, record_count
                           FROM ingest_runs
                           WHERE finished_at IS NOT NULL
                           ORDER BY finished_at DESC LIMIT 1"""
                    )
                    row = cur.fetchone()
                    if row:
                        last_ingest_at = row[0].isoformat() if row[0] else None
                        last_ingest_status = row[1]
                        last_ingest_count = row[2]
            except Exception:
                pass  # ingest_runs table may not exist on first deploy
            finally:
                conn.close()
        except Exception as exc:
            db_error = str(exc)
            db_connection = False

    response: dict = {
        "status": "ok",
        "db_configured": db_configured,
        "db_connection": db_connection,
        "last_ingest_at": last_ingest_at,
        "last_ingest_status": last_ingest_status,
        "last_ingest_count": last_ingest_count,
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

# US state name → 2-letter abbreviation (for formatting nationwide suggestions)
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
    # ISO 3166-2 format: "US-IL" → "IL"
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

    '679 North Peo'  → 'peo'
    '100 W Rand'     → 'rand'
    'Michigan Ave'   → 'michigan'
    '1600 W Chicago' → 'chicago'   (fragment long enough to be useful)
    """
    q = query.strip()
    # Drop trailing city/state suffixes the caller may have appended.
    # e.g. "1600 W Chicago Ave, Chicago, IL" → "1600 W Chicago Ave"
    # Strip ", City, ST" or ", ST" patterns (any 2-letter state code).
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
    Milwaukee Ave when the user typed 'Peo' (→ Peoria).
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
# /addresses/search endpoint
# Canonical backend-backed combobox suggestions with strict relevance ranking.
# ---------------------------------------------------------------------------

_ADDRESS_SEARCH_CACHE_TTL_SEC = 300  # 5 minutes — reduce DB churn
_address_search_cache: dict[str, object] = {
    "loaded_at": 0.0,
    "rows": [],
}

# Per-query Nominatim result cache so the same partial string doesn't hit the
# network on every keystroke.  Keyed on normalized query string, TTL 10 min.
_nominatim_suggest_cache: dict[str, dict] = {}
_NOMINATIM_SUGGEST_CACHE_TTL_SEC = 600

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


def _extract_zip(raw: str) -> str | None:
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", raw)
    return m.group(1) if m else None


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


def _rows_from_nominatim(query: str, limit: int) -> list[dict]:
    """Fallback suggestions from geocoder when DB index has no results.

    Results are cached per normalized query string for 10 minutes so repeated
    keystrokes don't each incur a network round-trip.
    """
    cache_key = normalize_address_query(query)
    entry = _nominatim_suggest_cache.get(cache_key)
    if entry and (time.time() - entry["ts"]) < _NOMINATIM_SUGGEST_CACHE_TTL_SEC:
        return entry["rows"][:limit]

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
        rows = list(by_norm.values())
        _nominatim_suggest_cache[cache_key] = {"ts": time.time(), "rows": rows}
        return rows[:limit]
    except Exception:
        return []


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


@app.get("/addresses/search")
def search_addresses(
    q: str = Query("", description="Partial address query"),
    limit: int = Query(8, ge=1, le=8, description="Maximum results to return"),
    popular: bool = Query(False, description="Return popular recent addresses when query is empty"),
) -> dict:
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


@app.get("/dashboard/address")
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
                    WHERE regexp_replace(lower(address), '\s+', ' ', 'g') = %s
                    ORDER BY scored_at DESC
                    LIMIT %s
                    """,
                    (row["normalized_full"], limit),
                )
                rows = cur.fetchall()

                cur.execute(
                    """
                    SELECT disruption_score, livability_score, confidence, mode, scored_at
                    FROM score_history
                    WHERE regexp_replace(lower(address), '\s+', ' ', 'g') = %s
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
            for r in rows
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
                    "SELECT MAX(finished_at) FROM ingest_runs WHERE status = 'success'"
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
    q: str = Query("", description="Partial US address query"),
    limit: int = Query(8, ge=1, le=8, description="Maximum results to return"),
    popular: bool = Query(False, description="Return popular addresses when query is short or empty"),
) -> dict:
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

    # Only fall back to Nominatim when the DB index has NO results at all.
    # Previously this triggered whenever results < limit, causing a network
    # call on every keystroke even when the DB had 3-4 good matches.
    if len(ranked_rows) == 0:
        geocoder_rows = _rows_from_nominatim(query, limit)
        if geocoder_rows:
            ranked_rows = _top_ranked_address_rows(query, geocoder_rows, limit, with_geo_penalty=True)

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
    livability_score: int | None = None
    livability_breakdown: dict | None = None
    confidence: str
    severity: dict
    top_risks: list
    explanation: str
    mode: str | None = None
    fallback_reason: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@app.post("/save")
def save_report(body: SaveReportRequest, authorization: str = Header(default=None)) -> dict:
    """
    Store a score result in the reports table and return a shareable UUID.

    When DB is not configured, returns a demo report_id so the frontend
    save/share flow is exercisable without a live database.
    """
    if not _is_db_configured():
        log.info("save_report address=%r mode=demo", body.address)
        return {"report_id": _DEMO_REPORT_ID}

    try:
        from backend.app.auth import get_current_user_optional
        from backend.scoring.query import get_db_connection
        user = get_current_user_optional(authorization)
        account_id = int(user["sub"]) if user and user.get("sub") else None
        conn = get_db_connection()
        report_id = str(uuid.uuid4())
        score_json = body.model_dump()
        if account_id is not None:
            score_json["account_id"] = account_id
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO reports (id, address, score_json) VALUES (%s, %s, %s)",
                    (report_id, body.address, score_json),
                )
                if account_id is not None:
                    cur.execute(
                        """
                        INSERT INTO score_history
                            (address, disruption_score, livability_score, livability_breakdown, confidence, mode, account_id)
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                        """,
                        (
                            body.address,
                            body.disruption_score,
                            body.livability_score if body.livability_score is not None else body.disruption_score,
                            json.dumps(body.livability_breakdown or {}),
                            body.confidence,
                            body.mode or "live",
                            account_id,
                        ),
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
# /dashboard endpoint
# Authenticated summary for saved reports + watchlist health.
# ---------------------------------------------------------------------------

@app.get("/dashboard")
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


# ---------------------------------------------------------------------------
# /watch endpoints (data-030)
# Score alert watchlist — subscribe an email + threshold to an address.
# When the score crosses the threshold, an entry is written to alert_log
# (email delivery is stubbed for MVP; only logging occurs).
# ---------------------------------------------------------------------------

class WatchRequest(BaseModel):
    email: str | None = None
    address: str
    threshold: int  # 0–100 disruption score


@app.post("/watch")
@app.post("/watchlist")
def subscribe_watch(body: WatchRequest, authorization: str = Header(default=None)) -> dict:
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

    from backend.app.auth import get_current_user_optional
    user = get_current_user_optional(authorization)
    account_id = int(user["sub"]) if user and user.get("sub") else None
    email = (body.email or (user.get("email") if user else None) or "").strip()

    if not _is_db_configured():
        # DB not yet live — accept the intent and return a demo success so the
        # email-capture form always works on the free tier. Real alert delivery
        # starts once DATABASE_URL is configured.
        log.info(
            "watch subscribe (demo) email=%r address=%r threshold=%d",
            email, body.address, body.threshold,
        )
        return {
            "id": None,
            "email": email,
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
                    INSERT INTO watchlist (email, address, threshold_score, token, account_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (email, address)
                    DO UPDATE SET
                        threshold_score = EXCLUDED.threshold_score,
                        token = EXCLUDED.token,
                        account_id = COALESCE(EXCLUDED.account_id, watchlist.account_id)
                    RETURNING id, token
                    """,
                    (email, body.address, body.threshold, token, account_id),
                )
                row = cur.fetchone()
                watch_id, stored_token = row[0], row[1]
            conn.commit()
        finally:
            conn.close()

        log.info(
            "watch subscribe id=%d email=%r address=%r threshold=%d",
            watch_id, email, body.address, body.threshold,
        )
        return {
            "id": watch_id,
            "email": email,
            "address": body.address,
            "threshold": body.threshold,
            "token": stored_token,
        }

    except HTTPException:
        raise
    except Exception as exc:
        log.error("subscribe_watch error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not create watchlist entry.") from exc


@app.get("/watchlist")
def get_watchlist(authorization: str = Header(default=None)) -> dict:
    """
    Return active watchlist entries for the authenticated user.
    """
    from backend.app.auth import get_current_user
    user = get_current_user(authorization)
    account_id = int(user["sub"])

    if not _is_db_configured():
        return {"entries": []}

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, address, threshold_score, created_at, is_active
                    FROM watchlist
                    WHERE account_id = %s AND is_active = true
                    ORDER BY created_at DESC
                    """,
                    (account_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        return {
            "entries": [
                {
                    "id": r[0],
                    "email": r[1],
                    "address": r[2],
                    "threshold": r[3],
                    "created_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                    "is_active": r[5],
                }
                for r in rows
            ]
        }
    except Exception as exc:
        log.error("get_watchlist error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not fetch watchlist.") from exc


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
                cur.execute("SELECT id, email, address, threshold_score FROM watchlist")
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
                                "INSERT INTO alert_log (watchlist_id, disruption_score) VALUES (%s, %s)",
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
            # data-043: Claude-generated display fields (empty when not enriched)
            "display_title", "distance", "description", "why_it_matters",
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


# ---------------------------------------------------------------------------
# /auth/* endpoints  (data-045)
#
# Email+password and Google OAuth account management.
#
# ---------------------------------------------------------------------------
# Clerk JWT verification helper  (app-025)
#
# Verifies a Clerk session token from an Authorization: Bearer header.
# Strategy: base64-decode the JWT payload to extract the session_id (sid),
# then confirm it is active via GET /v1/sessions/{id} using CLERK_SECRET_KEY.
# This requires no new dependencies — only stdlib base64/json + requests.
# ---------------------------------------------------------------------------

def _jwks_b64decode(s: str) -> bytes:
    """URL-safe base64 decode with automatic padding."""
    return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4))


def _fetch_jwks(issuer: str) -> dict:
    """
    Fetch Clerk's public JWKS from <issuer>/.well-known/jwks.json.
    This endpoint is public — no auth header required.
    Result is cached in _JWKS_CACHE for _JWKS_CACHE_TTL seconds.
    """
    now = time.monotonic()
    cached = _JWKS_CACHE.get(issuer)
    if cached and (now - cached["fetched_at"]) < _JWKS_CACHE_TTL:
        log.debug("clerk_jwks: using cached keys for iss=%s", issuer)
        return cached["keys"]

    jwks_url = f"{issuer}/.well-known/jwks.json"
    log.info("clerk_jwks: fetching %s", jwks_url)
    try:
        resp = _requests.get(jwks_url, timeout=10)
    except Exception as exc:
        log.exception("clerk_jwks: network error fetching %s: %s", jwks_url, exc)
        raise HTTPException(
            status_code=503, detail=f"Could not fetch Clerk JWKS ({exc})"
        ) from exc

    log.info("clerk_jwks: response status=%d url=%s", resp.status_code, jwks_url)
    if not resp.ok:
        log.error("clerk_jwks: non-OK response status=%d body=%s", resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=503, detail=f"Clerk JWKS returned {resp.status_code}"
        )

    keys = resp.json()
    num_keys = len(keys.get("keys", []))
    log.info("clerk_jwks: cached %d key(s) for iss=%s", num_keys, issuer)
    _JWKS_CACHE[issuer] = {"keys": keys, "fetched_at": now}
    return keys


def _verify_clerk_jwt(authorization: str | None) -> str:
    """
    Verify a Clerk frontend session token locally via RS256 + JWKS.

    Strategy:
      1. Decode the JWT header/payload (unverified) to get kid, alg, iss, exp.
      2. Fetch Clerk's public JWKS from <iss>/.well-known/jwks.json (cached 1h).
      3. Find the matching public key by kid.
      4. Verify the JWT signature + expiry with PyJWT (RS256, local — no network call).
      5. Return payload["sub"] as the Clerk user_id.

    This replaces the per-request GET /v1/sessions/{sid} call which caused
    timeouts on Railway when api.clerk.com egress was slow.

    Raises HTTP 401 if the token is missing, malformed, expired, or signature invalid.
    Raises HTTP 503 if CLERK_SECRET_KEY is not configured or JWKS is unreachable.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization[7:]
    log.info("clerk_jwt: verifying token (len=%d)", len(token))

    # ── Step 1: decode header and payload without signature verification ──────
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("not a 3-part JWT")
        header = json.loads(_jwks_b64decode(parts[0]))
        payload_unverified = json.loads(_jwks_b64decode(parts[1]))
        kid = header.get("kid")
        alg = header.get("alg", "RS256")
        iss = payload_unverified.get("iss", "").rstrip("/")
        if not kid:
            raise ValueError("missing kid in JWT header")
        if not iss:
            raise ValueError("missing iss in JWT payload")
        if alg != "RS256":
            raise ValueError(f"unsupported algorithm: {alg!r}")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("clerk_jwt: decode error: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token format")

    log.info("clerk_jwt: header kid=%s alg=%s iss=%s", kid, alg, iss)

    # ── Step 2: require CLERK_SECRET_KEY as a config guard ────────────────────
    if not os.environ.get("CLERK_SECRET_KEY", ""):
        log.error("clerk_jwt: CLERK_SECRET_KEY is not set")
        raise HTTPException(status_code=503, detail="CLERK_SECRET_KEY not configured on backend")

    # ── Step 3: get JWKS and find the matching public key ─────────────────────
    try:
        jwks = _fetch_jwks(iss)
    except HTTPException:
        raise

    def _find_key(jwks_data: dict) -> dict | None:
        for k in jwks_data.get("keys", []):
            if k.get("kid") == kid:
                log.info("clerk_jwt: found key kid=%s kty=%s", kid, k.get("kty"))
                return k
        return None

    key_dict = _find_key(jwks)
    if key_dict is None:
        # kid not in cache — key may have rotated; force re-fetch once
        log.warning("clerk_jwt: kid=%s not in cached JWKS, forcing re-fetch for iss=%s", kid, iss)
        _JWKS_CACHE.pop(iss, None)
        try:
            jwks = _fetch_jwks(iss)
        except HTTPException:
            raise
        key_dict = _find_key(jwks)

    if key_dict is None:
        log.error("clerk_jwt: kid=%s not found after re-fetch for iss=%s", kid, iss)
        raise HTTPException(status_code=401, detail="JWT signing key not found in JWKS")

    # ── Step 4: verify signature + expiry locally (no network call) ───────────
    try:
        payload = _jose_jwt.decode(
            token,
            key_dict,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk JWTs use azp, not aud
        )
    except _JoseExpired:
        log.warning("clerk_jwt: token expired for iss=%s", iss)
        raise HTTPException(status_code=401, detail="Token expired")
    except _JoseJWTError as exc:
        log.error("clerk_jwt: signature/claim validation failed: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    # ── Step 5: extract user_id ───────────────────────────────────────────────
    user_id = payload.get("sub")
    if not user_id:
        log.error("clerk_jwt: no sub claim in verified payload keys=%s", list(payload.keys()))
        raise HTTPException(status_code=401, detail="Could not resolve user from token")

    log.info("clerk_jwt: OK user_id=%r iss=%s", user_id, iss)
    return user_id


# ---------------------------------------------------------------------------
# API key management endpoints  (app-025)
#
# POST   /keys            — generate a new key for the calling Clerk user
# GET    /keys            — list the user's keys (masked)
# DELETE /keys/{key_id}   — revoke a key
#
# All three require a valid Clerk session token in Authorization: Bearer.
# ---------------------------------------------------------------------------

class _CreateKeyBody(BaseModel):
    label: str = ""


@app.post("/keys", status_code=201)
def create_user_key(
    body: _CreateKeyBody,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Generate a new API key for the authenticated Clerk user.
    task: app-025

    Requires Authorization: Bearer <clerk_session_token>.
    Returns the plaintext key exactly once — it is never stored.
    """
    user_id = _verify_clerk_jwt(authorization)

    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured")

    full_key, prefix, key_hash = _generate_api_key()
    label = (body.label or "").strip()

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO api_keys (prefix, key_hash, label, user_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (prefix, key_hash, label, user_id),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.error("create_user_key DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Could not create API key") from exc

    log.info("create_user_key user_id=%r prefix=%s", user_id, prefix)
    return {"key": full_key, "prefix": prefix, "id": row[0], "label": label}


@app.get("/keys")
def list_user_keys(
    authorization: str | None = Header(default=None),
) -> list:
    """
    List the authenticated user's API keys (masked).
    task: app-025

    Requires Authorization: Bearer <clerk_session_token>.
    Returns prefix, masked_key (lre_<prefix>****), call_count, last_called_at.
    """
    try:
        user_id = _verify_clerk_jwt(authorization)

        if not _is_db_configured():
            raise HTTPException(status_code=503, detail="Database not configured")

        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, prefix, label, is_active, call_count,
                           last_called_at, created_at
                    FROM api_keys
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        return [
            {
                "id": r[0],
                "prefix": r[1],
                "masked_key": f"lre_{r[1]}{'*' * 16}",
                "label": r[2],
                "is_active": r[3],
                "call_count": r[4],
                "last_called_at": r[5].isoformat() if r[5] else None,
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:
        log.error("list_user_keys unhandled error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"list_user_keys failed: {exc}") from exc


@app.delete("/keys/{key_id}", status_code=200)
def revoke_user_key(
    key_id: int,
    authorization: str | None = Header(default=None),
) -> dict:
    """
    Revoke an API key by setting is_active = false.
    task: app-025

    Requires Authorization: Bearer <clerk_session_token>.
    Only the key's owner can revoke it.
    """
    user_id = _verify_clerk_jwt(authorization)

    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE api_keys
                    SET is_active = false
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                    """,
                    (key_id, user_id),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        log.error("revoke_user_key DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Database error") from exc

    if not row:
        raise HTTPException(status_code=404, detail="Key not found or not owned by user")

    log.info("revoke_user_key key_id=%d user_id=%r", key_id, user_id)
    return {"id": key_id, "revoked": True}


# ---------------------------------------------------------------------------
# Legacy user account endpoints  (data-045)
# POST /auth/register   — create a new account (email + password)
# POST /auth/login      — sign in with email + password, receive JWT
# POST /auth/google     — upsert account from Google OAuth profile (called
#                         server-side by NextAuth after the OAuth dance)
# GET  /auth/me         — return the current user from their Bearer token
#
# All password storage uses bcrypt via backend/app/auth.py.
# Tokens are HS256 JWTs signed with JWT_SECRET (30-day expiry).
# ---------------------------------------------------------------------------


class _RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class _LoginBody(BaseModel):
    email: str
    password: str


class _GoogleBody(BaseModel):
    google_id: str
    email: str
    display_name: str | None = None
    # Optional server-to-server shared secret so only NextAuth can call this.
    # Set NEXTAUTH_BACKEND_SECRET on both Railway and Vercel to enable.
    internal_secret: str | None = None


def _get_auth_conn():
    """Open a DB connection for auth queries. Raises 503 if DB not configured."""
    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Database not configured")
    from backend.scoring.query import get_db_connection
    return get_db_connection()


@app.post("/auth/register", status_code=201)
def auth_register(body: _RegisterBody) -> dict:
    """
    Create a new email+password account.

    Returns { account_id, email, display_name, token } on success.
    Raises HTTP 409 if the email is already registered.
    Raises HTTP 400 if password is fewer than 8 characters.
    """
    from backend.app.auth import create_token, hash_password

    email = body.email.strip().lower()
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    conn = _get_auth_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM accounts WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="An account with this email already exists")

            pw_hash = hash_password(body.password)
            display_name = (body.display_name or "").strip() or None
            cur.execute(
                """
                INSERT INTO accounts (email, password_hash, display_name, email_verified)
                VALUES (%s, %s, %s, false)
                RETURNING id, email, display_name
                """,
                (email, pw_hash, display_name),
            )
            row = cur.fetchone()
            conn.commit()

        account_id, acct_email, acct_name = row
        token = create_token(account_id, acct_email, acct_name)
        log.info("auth register account_id=%d email=%r", account_id, acct_email)
        return {"account_id": account_id, "email": acct_email, "display_name": acct_name, "token": token}
    finally:
        conn.close()


@app.post("/auth/login")
def auth_login(body: _LoginBody) -> dict:
    """
    Sign in with email + password.

    Returns { account_id, email, display_name, token } on success.
    Raises HTTP 401 for unknown email or wrong password.
    """
    from backend.app.auth import create_token, verify_password

    email = body.email.strip().lower()
    conn = _get_auth_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash, display_name FROM accounts WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()

        if not row or not row[2]:
            # No account or OAuth-only account (no password_hash)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        account_id, acct_email, pw_hash, acct_name = row
        if not verify_password(body.password, pw_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Update last_login_at
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE accounts SET last_login_at = now() WHERE id = %s",
                (account_id,),
            )
            conn.commit()

        token = create_token(account_id, acct_email, acct_name)
        log.info("auth login account_id=%d email=%r", account_id, acct_email)
        return {"account_id": account_id, "email": acct_email, "display_name": acct_name, "token": token}
    finally:
        conn.close()


@app.post("/auth/google")
def auth_google(body: _GoogleBody) -> dict:
    """
    Upsert an account from a Google OAuth profile.

    Called server-side by NextAuth after completing the Google OAuth flow.
    The NEXTAUTH_BACKEND_SECRET env var (if set) gates access to this endpoint
    so only the Next.js server can call it.

    Returns { account_id, email, display_name, token }.
    """
    from backend.app.auth import create_token

    # Optional server-to-server secret check
    backend_secret = os.environ.get("NEXTAUTH_BACKEND_SECRET", "").strip()
    if backend_secret and body.internal_secret != backend_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    email = body.email.strip().lower()
    display_name = (body.display_name or "").strip() or None
    conn = _get_auth_conn()
    try:
        with conn.cursor() as cur:
            # Try to find existing account by google_id first, then by email
            cur.execute(
                "SELECT id, email, display_name FROM accounts WHERE google_id = %s",
                (body.google_id,),
            )
            row = cur.fetchone()

            if not row:
                cur.execute(
                    "SELECT id, email, display_name FROM accounts WHERE email = %s",
                    (email,),
                )
                row = cur.fetchone()
                if row:
                    # Link Google to existing email account
                    cur.execute(
                        "UPDATE accounts SET google_id = %s, last_login_at = now() WHERE id = %s",
                        (body.google_id, row[0]),
                    )
                else:
                    # New Google-only account
                    cur.execute(
                        """
                        INSERT INTO accounts (email, google_id, display_name, email_verified)
                        VALUES (%s, %s, %s, true)
                        RETURNING id, email, display_name
                        """,
                        (email, body.google_id, display_name),
                    )
                    row = cur.fetchone()
            else:
                cur.execute(
                    "UPDATE accounts SET last_login_at = now() WHERE id = %s",
                    (row[0],),
                )

            conn.commit()

        account_id, acct_email, acct_name = row[0], row[1], row[2]
        token = create_token(account_id, acct_email, acct_name)
        log.info("auth google account_id=%d email=%r", account_id, acct_email)
        return {"account_id": account_id, "email": acct_email, "display_name": acct_name, "token": token}
    finally:
        conn.close()


class _ClerkSyncBody(BaseModel):
    clerk_user_id: str | None = None
    email: str | None = None


@app.post("/auth/sync", status_code=200)
def auth_clerk_sync(
    body: _ClerkSyncBody,
    authorization: str = Header(default=None),
) -> dict:
    """
    Upsert a Clerk user record into the users table.
    task: app-024

    Called from the frontend after first Clerk sign-in to ensure a minimal
    user row exists in Postgres. Idempotent — safe to call on every sign-in.

    Request body: { clerk_user_id?, email? }
    Response:     { id, email, subscription_tier, created_at }
    """
    try:
        claims = _verify_clerk_claims(authorization)
        clerk_user_id = str(claims["sub"])
        verified_email = _resolve_clerk_email(claims)

        if body.clerk_user_id and body.clerk_user_id != clerk_user_id:
            raise HTTPException(status_code=401, detail="Authenticated Clerk user does not match request body")
        if body.email and body.email.strip().lower() != verified_email:
            raise HTTPException(status_code=401, detail="Authenticated Clerk email does not match request body")

        if not _is_db_configured():
            raise HTTPException(status_code=503, detail="DB not configured")

        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (id, email)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email
                    RETURNING id, email, subscription_tier, created_at
                    """,
                    (clerk_user_id, verified_email),
                )
                row = cur.fetchone()
            conn.commit()
        finally:
            conn.close()

        if row is None:
            raise HTTPException(status_code=500, detail="User upsert returned no row")

        return {
            "id": row[0],
            "email": row[1],
            "subscription_tier": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("auth_clerk_sync unhandled error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"auth_clerk_sync failed: {exc}") from exc


@app.get("/auth/me")
def auth_me(authorization: str = Header(default=None)) -> dict:
    """
    Return the current user's profile from their Bearer JWT.

    Response: { account_id, email, name }
    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    from backend.app.auth import get_current_user
    user = get_current_user(authorization)
    return {"account_id": user["sub"], "email": user["email"], "name": user.get("name")}
