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
import os

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.deps import _is_db_configured

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
