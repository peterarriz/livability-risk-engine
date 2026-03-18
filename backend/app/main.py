"""
backend/app/main.py
task: app-008
lane: app

FastAPI /score endpoint — updated to use the real scoring path
when a DB connection is available, with graceful fallback to the
mocked demo response when it is not (preserving demo mode).

API contract: docs/04_api_contracts.md
  GET /score?address=<Chicago address>
  Returns: address, disruption_score, confidence, severity, top_risks, explanation
"""

import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Livability Risk Engine")

# ---------------------------------------------------------------------------
# CORS middleware
# Allows the Next.js dev server (localhost:3000) to call the API directly.
# In production, restrict origins to the deployed frontend domain.
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        os.environ.get("FRONTEND_ORIGIN", ""),
    ],
    allow_methods=["GET"],
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


def _build_demo_response(address: str) -> dict:
    return {**DEMO_RESPONSE, "address": address}


# ---------------------------------------------------------------------------
# DB + scoring path (live mode)
# Only activated when POSTGRES_HOST env var is set.
# ---------------------------------------------------------------------------

def _is_db_configured() -> bool:
    return bool(os.environ.get("POSTGRES_HOST"))


def _score_live(address: str) -> dict:
    """
    Full live scoring path:
      1. Geocode address → (lat, lon)
      2. Query nearby projects from canonical DB
      3. Apply scoring engine → ScoreResult
      4. Return as dict matching API contract
    """
    from backend.ingest.geocode import geocode_address
    from backend.scoring.query import compute_score, get_db_connection, get_nearby_projects

    coords = geocode_address(address)
    if not coords:
        raise ValueError(f"Could not geocode address: {address!r}")

    lat, lon = coords
    conn = get_db_connection()

    try:
        nearby = get_nearby_projects(lat, lon, conn)
    finally:
        conn.close()

    result = compute_score(nearby, address)
    return asdict(result)


# ---------------------------------------------------------------------------
# /score endpoint
# ---------------------------------------------------------------------------

@app.get("/score")
def get_score(
    address: str = Query(..., description="Chicago address to score"),
) -> dict:
    """
    Return a near-term construction disruption risk score for a Chicago address.

    Live mode (when POSTGRES_HOST is set):
      Geocodes the address, queries the canonical projects table,
      and applies the rule-based scoring engine.

    Demo mode (when POSTGRES_HOST is not set):
      Returns the approved mocked example from docs/04_api_contracts.md.
      The frontend handles both modes transparently via its demo fallback.
    """
    if not _is_db_configured():
        return _build_demo_response(address)

    try:
        return _score_live(address)
    except ValueError as exc:
        # Geocoding failure — return demo response rather than a hard error
        # so the frontend stays functional during partial data availability.
        return _build_demo_response(address)
    except Exception as exc:
        # Unexpected DB or scoring error — raise 503 so the frontend
        # falls back to its own demo mode gracefully.
        raise HTTPException(
            status_code=503,
            detail="Scoring service temporarily unavailable.",
        ) from exc


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": "live" if _is_db_configured() else "demo",
    }
