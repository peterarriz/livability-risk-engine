"""
backend/app/deps.py

Shared dependencies for the FastAPI app — imported by main.py and route modules.

Contains:
  - _is_db_configured() — checks for DATABASE_URL or POSTGRES_HOST
  - _require_api_key_enabled() — checks REQUIRE_API_KEY env var
  - _hash_key(full_key) — sha256 hash for API key verification
  - _generate_api_key() — creates lre_ prefixed API keys
  - verify_api_key — FastAPI dependency, optional API key enforcement
  - require_api_key — FastAPI dependency, strict API key enforcement
  - require_admin_secret — FastAPI dependency for internal operator endpoints
  - DEMO_RESPONSE — demo score result dict
  - _build_demo_response — wraps DEMO_RESPONSE with address/fallback
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets

from fastapi import Header, HTTPException

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB configuration check
# ---------------------------------------------------------------------------

def _is_db_configured() -> bool:
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST"))


# ---------------------------------------------------------------------------
# API key auth  (data-027)
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


async def require_admin_secret(x_admin_secret: str | None = Header(None)) -> None:
    """Require X-Admin-Secret to match ADMIN_SECRET for operator endpoints."""
    admin_secret = os.environ.get("ADMIN_SECRET", "").strip()
    if not admin_secret:
        raise HTTPException(status_code=503, detail="Admin auth is not configured")

    submitted = (x_admin_secret or "").strip()
    if not submitted or not hmac.compare_digest(submitted, admin_secret):
        raise HTTPException(status_code=403, detail="Forbidden")


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

    row = None
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
                    # Update usage counters — best-effort, non-blocking
                    try:
                        cur.execute(
                            """UPDATE api_keys
                               SET last_used_at = now(),
                                   last_called_at = now(),
                                   call_count = call_count + 1
                               WHERE prefix = %s""",
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


async def require_api_key(x_api_key: str | None = Header(None)) -> None:
    """
    Strict API key enforcement — always required, regardless of REQUIRE_API_KEY env var.
    Used for batch endpoints where unauthenticated access is never permitted.
    """
    if not x_api_key or not x_api_key.startswith("lre_"):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    random_portion = x_api_key[4:]
    if len(random_portion) < 8:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")

    prefix = random_portion[:8]
    submitted_hash = _hash_key(x_api_key)

    if not _is_db_configured():
        raise HTTPException(status_code=503, detail="Auth service unavailable (DB not configured)")

    row = None
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
                    try:
                        cur.execute(
                            """UPDATE api_keys
                               SET last_used_at = now(),
                                   last_called_at = now(),
                                   call_count = call_count + 1
                               WHERE prefix = %s""",
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
        log.error("require_api_key DB error: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    if not row or not row[1] or row[0] != submitted_hash:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")


# ---------------------------------------------------------------------------
# Demo response
# ---------------------------------------------------------------------------

DEMO_RESPONSE = {
    "address": None,            # filled in at request time
    "disruption_score": 62,
    "livability_score": 48,
    "livability_breakdown": {
        "weights": {
            "disruption_risk": 0.35,
            "crime_trend": 0.25,
            "school_rating": 0.20,
            "demographics_stability": 0.10,
            "flood_environmental": 0.10,
        },
        "components": {
            "disruption_risk": {"raw_score": 38, "weighted_contribution": 13.3},
            "crime_trend": {"raw_score": 55, "weighted_contribution": 13.8},
            "school_rating": {"raw_score": 60, "weighted_contribution": 12.0},
            "demographics_stability": {"raw_score": 52, "weighted_contribution": 5.2},
            "flood_environmental": {"raw_score": 40, "weighted_contribution": 4.0},
        },
    },
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
    """
    return {
        **DEMO_RESPONSE,
        "address": address,
        "mode": "demo",
        "fallback_reason": fallback_reason,
        "latitude": lat,
        "longitude": lon,
    }
