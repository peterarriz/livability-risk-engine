"""
backend/app/main.py

FastAPI application shell for Livability Risk Engine.

Route implementations live in backend/app/routes/* except for app-shell
operations that remain here: CORS preflight, health probes, startup bootstrap,
and the legacy account auth endpoints that have not yet been extracted.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.deps import _is_db_configured

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

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
# missing-variable problems immediately. Values are never logged.
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
# FastAPI's CORSMiddleware, e.g. during cold starts or health-check windows.
# This route handler catches all OPTIONS preflights at the application layer
# and responds immediately with the correct CORS headers.
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
    DB connectivity probe for operators and CI. Separate from /health so the
    Railway liveness check is never blocked by a slow or unavailable DB.
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


# ---------------------------------------------------------------------------
# Legacy user account endpoints  (data-045)
# POST /auth/register   -- create a new account (email + password)
# POST /auth/login      -- sign in with email + password, receive JWT
# POST /auth/google     -- upsert account from Google OAuth profile
# GET  /auth/me         -- return the current user from their Bearer token
#
# All password storage uses bcrypt via backend/app/auth.py.
# Tokens are HS256 JWTs signed with JWT_SECRET.
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
    """Open a DB connection for auth queries. Raises 503 if DB is not configured."""
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
    The NEXTAUTH_BACKEND_SECRET env var, if set, gates access to this endpoint
    so only the Next.js server can call it.
    """
    from backend.app.auth import create_token

    backend_secret = os.environ.get("NEXTAUTH_BACKEND_SECRET", "").strip()
    if backend_secret and body.internal_secret != backend_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    email = body.email.strip().lower()
    display_name = (body.display_name or "").strip() or None
    conn = _get_auth_conn()
    try:
        with conn.cursor() as cur:
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
                    cur.execute(
                        "UPDATE accounts SET google_id = %s, last_login_at = now() WHERE id = %s",
                        (body.google_id, row[0]),
                    )
                else:
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
