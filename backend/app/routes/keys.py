"""
backend/app/routes/keys.py

API key management endpoints — extracted from main.py.

Endpoints:
  POST   /admin/keys     — admin creates API key (ADMIN_SECRET auth)
  GET    /usage          — key usage metrics (API key auth)
  GET    /docs/api-access — public API access info
  POST   /keys           — user creates key (Clerk auth)
  GET    /keys           — user lists keys (Clerk auth)
  DELETE /keys/{key_id}  — user revokes key (Clerk auth)
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from backend.app.deps import (
    _generate_api_key,
    _hash_key,
    _is_db_configured,
    _require_api_key_enabled,
    verify_api_key,
)
from backend.app.services.clerk import _verify_clerk_jwt

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# /admin/keys  (data-027)
# ---------------------------------------------------------------------------

@router.post("/admin/keys")
def create_api_key(
    label: str = Query(..., description="Human-readable label for this key"),
    x_admin_secret: str | None = Header(None),
) -> dict:
    """Create a new API key. Requires X-Admin-Secret header."""
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
                    "INSERT INTO api_keys (prefix, key_hash, label) VALUES (%s, %s, %s)",
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
# /usage  (data-043)
# ---------------------------------------------------------------------------

@router.get("/usage", dependencies=[Depends(verify_api_key)])
def get_usage(x_api_key: str | None = Header(None)) -> dict:
    """Return usage metrics for the authenticated API key."""
    if not x_api_key or not x_api_key.startswith("lre_"):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    prefix = x_api_key[4:][:8]

    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT prefix, label, call_count, last_called_at FROM api_keys WHERE prefix = %s",
                    (prefix,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:
        log.error("get_usage DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Usage service temporarily unavailable") from exc

    if not row:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    return {
        "prefix": row[0],
        "label": row[1],
        "call_count": row[2],
        "last_called_at": row[3].isoformat() if row[3] else None,
    }


# ---------------------------------------------------------------------------
# /docs/api-access  (data-027)
# ---------------------------------------------------------------------------

@router.get("/docs/api-access")
def api_access_info() -> dict:
    """Public documentation endpoint for B2B API access."""
    return {
        "title": "Livability Risk Engine API",
        "version": "1.0",
        "description": (
            "Nationwide address-level livability and disruption intelligence. "
            "Coverage and evidence depth vary by city, source, and data type."
        ),
        "score_semantics": {
            "livability_score": "Public headline score, 0-100; higher means better address livability and lower near-term risk.",
            "disruption_score": "Backward-compatible risk subscore, 0-100; higher means more near-term disruption risk.",
            "severity": "Disruption dimensions only: noise, traffic, and dust.",
            "confidence": "Evidence trust and specificity, not score direction.",
            "evidence_quality": "User-facing coverage/evidence signal; sparse feeds should be treated as directional.",
        },
        "coverage": (
            "Coverage varies by city and data type. Where permit or closure feeds are sparse, "
            "results rely more on neighborhood context and should be treated as directional."
        ),
        "auth": {
            "required": _require_api_key_enabled(),
            "method": "Pass your API key in the X-API-Key header.",
            "request_access": "Contact the platform operator to request an API key.",
        },
        "endpoints": [
            {"method": "GET", "path": "/score", "description": "Score a US address; returns livability_score and disruption_score."},
            {"method": "POST", "path": "/score/batch", "description": "Score up to 200 US addresses in JSON."},
            {"method": "POST", "path": "/score/batch/csv", "description": "Upload a CSV of addresses and receive score columns."},
            {"method": "GET", "path": "/history", "description": "Recent score history for an address."},
            {"method": "GET", "path": "/export/csv", "description": "Download score and nearby signal context as CSV."},
        ],
        "rate_limits": "Authenticated requests are subject to operator-configured rate limits.",
        "example": {
            "request": "GET /score?address=100+W+Randolph+St+Chicago+IL",
            "response_shape": {
                "address": "string",
                "livability_score": "0-100 integer; higher is better",
                "disruption_score": "0-100 integer; higher means more near-term disruption risk",
                "confidence": "LOW | MEDIUM | HIGH",
                "evidence_quality": "strong | moderate | contextual_only | insufficient",
                "severity": {"noise": "LOW | MEDIUM | HIGH", "traffic": "LOW | MEDIUM | HIGH", "dust": "LOW | MEDIUM | HIGH"},
                "top_risks": ["string"],
                "explanation": "string",
                "mode": "live | demo",
            },
        },
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


# ---------------------------------------------------------------------------
# /keys user CRUD  (app-025) — Clerk auth
# ---------------------------------------------------------------------------

class _CreateKeyBody(BaseModel):
    label: str = ""


@router.post("/keys", status_code=201)
def create_user_key(
    body: _CreateKeyBody,
    authorization: str | None = Header(default=None),
) -> dict:
    """Generate a new API key for the authenticated Clerk user."""
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


@router.get("/keys")
def list_user_keys(
    authorization: str | None = Header(default=None),
) -> list:
    """List the authenticated user's API keys (masked)."""
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


@router.delete("/keys/{key_id}", status_code=200)
def revoke_user_key(
    key_id: int,
    authorization: str | None = Header(default=None),
) -> dict:
    """Revoke an API key. Only the key's owner can revoke it."""
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
                    UPDATE api_keys SET is_active = false
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
