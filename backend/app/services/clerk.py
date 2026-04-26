"""
backend/app/services/clerk.py

Clerk JWT verification — extracted from main.py.

Contains:
  - _JWKS_CACHE / _JWKS_CACHE_TTL — in-memory JWKS cache
  - _jwks_b64decode() — URL-safe base64 decode with auto-padding
  - _fetch_jwks() — fetches/caches Clerk JWKS
  - _verify_clerk_jwt() — verifies Clerk session JWT, returns user_id
  - _resolve_clerk_email() — resolves a verified Clerk user's primary email
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

import requests as _requests
from fastapi import HTTPException

# python-jose for RS256 JWT verification
from jose import jwt as _jose_jwt
from jose.exceptions import ExpiredSignatureError as _JoseExpired, JWTError as _JoseJWTError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_JWKS_CACHE: dict = {}
_JWKS_CACHE_TTL = 3600  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_issuer_for_compare(value: str | None) -> str:
    """Normalize a Clerk issuer URL for exact allowlist comparison."""
    if not value:
        return ""
    return value.strip().rstrip("/")


def _configured_allowed_issuers() -> set[str]:
    """Return normalized Clerk issuers allowed to sign backend tokens."""
    issuers: set[str] = set()
    raw_allowed = os.environ.get("CLERK_ALLOWED_ISSUERS", "")
    for issuer in raw_allowed.split(","):
        normalized = _normalize_issuer_for_compare(issuer)
        if normalized:
            issuers.add(normalized)

    fallback = _normalize_issuer_for_compare(os.environ.get("CLERK_ISSUER"))
    if fallback:
        issuers.add(fallback)

    return issuers


def _require_allowed_issuer(issuer: str) -> str:
    """
    Require the unverified token issuer to match explicit backend config.

    This runs before JWKS fetch so a token cannot choose its own signing-key URL.
    """
    normalized = _normalize_issuer_for_compare(issuer)
    allowed_issuers = _configured_allowed_issuers()
    if not allowed_issuers:
        log.error("clerk_jwt: CLERK_ALLOWED_ISSUERS or CLERK_ISSUER is not configured")
        raise HTTPException(status_code=503, detail="Clerk issuer allowlist not configured on backend")

    if normalized not in allowed_issuers:
        log.warning("clerk_jwt: token issuer is not in the configured allowlist")
        raise HTTPException(status_code=401, detail="Token issuer is not allowed")

    return normalized


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


def _normalize_email(value: object) -> str | None:
    """Normalize an email string for DB storage and comparisons."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _fetch_clerk_user(user_id: str) -> dict:
    """
    Fetch a Clerk user from the Backend API using CLERK_SECRET_KEY.

    Uses the REST API directly to avoid adding a Clerk backend SDK dependency
    to the FastAPI service.
    """
    secret_key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        log.error("clerk_user: CLERK_SECRET_KEY is not set")
        raise HTTPException(status_code=503, detail="CLERK_SECRET_KEY not configured on backend")

    url = f"https://api.clerk.com/v1/users/{user_id}"
    try:
        resp = _requests.get(
            url,
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
    except Exception as exc:
        log.exception("clerk_user: network error fetching %s: %s", url, exc)
        raise HTTPException(
            status_code=503,
            detail=f"Could not fetch Clerk user ({exc})",
        ) from exc

    if not resp.ok:
        log.error("clerk_user: non-OK response status=%d body=%s", resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=503,
            detail=f"Clerk user lookup returned {resp.status_code}",
        )

    try:
        return resp.json()
    except Exception as exc:
        log.exception("clerk_user: invalid JSON for %s: %s", url, exc)
        raise HTTPException(status_code=503, detail="Clerk user lookup returned invalid JSON") from exc


def _resolve_clerk_email(claims: dict) -> str:
    """
    Resolve a verified Clerk user's usable email address.

    Priority:
      1. Verified token claim `email`, when present.
      2. Server-side Clerk user lookup via verified `sub`.

    Raises 503 if Clerk backend configuration or lookup fails.
    Raises 401 only when the token is valid but Clerk cannot produce a usable
    email for the verified user.
    """
    token_email = _normalize_email(claims.get("email"))
    if token_email:
        return token_email

    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not resolve user from token")

    user = _fetch_clerk_user(user_id)
    primary_id = user.get("primary_email_address_id") or user.get("primaryEmailAddressId")
    email_addresses = user.get("email_addresses") or user.get("emailAddresses") or []

    if isinstance(email_addresses, list):
        for email_obj in email_addresses:
            if not isinstance(email_obj, dict):
                continue
            email_id = email_obj.get("id")
            candidate = _normalize_email(
                email_obj.get("email_address") or email_obj.get("emailAddress")
            )
            if primary_id and email_id == primary_id and candidate:
                return candidate
        for email_obj in email_addresses:
            if not isinstance(email_obj, dict):
                continue
            candidate = _normalize_email(
                email_obj.get("email_address") or email_obj.get("emailAddress")
            )
            if candidate:
                return candidate

    raise HTTPException(status_code=401, detail="Could not resolve email for authenticated Clerk user")


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------

def _verify_clerk_claims(authorization: str | None) -> dict:
    """
    Verify a Clerk frontend session token locally via RS256 + JWKS and return
    the verified JWT claims.

    Strategy:
      1. Decode the JWT header/payload (unverified) to get kid, alg, iss, exp.
      2. Require iss to match CLERK_ALLOWED_ISSUERS / CLERK_ISSUER.
      3. Fetch Clerk's public JWKS from the allowed <iss>/.well-known/jwks.json.
      4. Find the matching public key by kid.
      5. Verify the JWT signature + expiry with PyJWT (RS256, local — no network call).
      6. Return the verified payload claims.

    Raises HTTP 401 if the token is missing, malformed, expired, or signature invalid.
    Raises HTTP 503 if Clerk auth config is incomplete or JWKS is unreachable.
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

    # ── Step 2: require issuer allowlist before any JWKS fetch ────────────────
    iss = _require_allowed_issuer(iss)

    # ── Step 3: require CLERK_SECRET_KEY as a config guard ────────────────────
    if not os.environ.get("CLERK_SECRET_KEY", ""):
        log.error("clerk_jwt: CLERK_SECRET_KEY is not set")
        raise HTTPException(status_code=503, detail="CLERK_SECRET_KEY not configured on backend")

    # ── Step 4: get JWKS and find the matching public key ─────────────────────
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

    # ── Step 5: verify signature + expiry locally (no network call) ───────────
    try:
        payload = _jose_jwt.decode(
            token,
            key_dict,
            algorithms=["RS256"],
            # TODO: Enforce audience and authorized-party after current Clerk
            # token claim shape is verified across local, preview, and prod.
            options={"verify_aud": False},
        )
    except _JoseExpired:
        log.warning("clerk_jwt: token expired for iss=%s", iss)
        raise HTTPException(status_code=401, detail="Token expired")
    except _JoseJWTError as exc:
        log.error("clerk_jwt: signature/claim validation failed: %s", exc)
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    # ── Step 6: extract user_id ───────────────────────────────────────────────
    user_id = payload.get("sub")
    if not user_id:
        log.error("clerk_jwt: no sub claim in verified payload keys=%s", list(payload.keys()))
        raise HTTPException(status_code=401, detail="Could not resolve user from token")

    log.info("clerk_jwt: OK user_id=%r iss=%s", user_id, iss)
    return payload


def _verify_clerk_jwt(authorization: str | None) -> str:
    """Verify a Clerk token and return the Clerk user_id."""
    payload = _verify_clerk_claims(authorization)
    return str(payload["sub"])
