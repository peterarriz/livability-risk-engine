"""
backend/app/routes/auth.py

Clerk-related auth endpoints.
Extracted from main.py as part of the APIRouter module split.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()


class _ClerkSyncBody(BaseModel):
    clerk_user_id: str
    email: str


@router.post("/auth/sync", status_code=200)
def auth_clerk_sync(body: _ClerkSyncBody) -> dict:
    """
    Upsert a Clerk user record into the users table.
    task: app-024

    Called from the frontend after first Clerk sign-in to ensure a minimal
    user row exists in Postgres. Idempotent — safe to call on every sign-in.

    Request body: { clerk_user_id, email }
    Response:     { id, email, subscription_tier, created_at }
    """
    # Import here to avoid circular imports during module loading
    from backend.app.main import _is_db_configured

    try:
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
                    (body.clerk_user_id, body.email),
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
