"""
backend/app/routes/reports.py

Extracted from backend/app/main.py — report-related endpoints:
  POST /save            (data-021)
  GET  /report/{id}     (data-021)
  GET  /history         (data-025)
  GET  /score-trend     (data-062)
  GET  /export/csv      (data-029)
"""

import csv
import io
import json
import logging
import math
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.deps import DEMO_RESPONSE, _is_db_configured, require_api_key

log = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEMO_REPORT_ID = "00000000-0000-0000-0000-000000000001"

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

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SaveReportRequest(BaseModel):
    """Score JSON payload to persist as a saved report.

    livability_score is the public headline score. disruption_score is retained
    as the backward-compatible near-term disruption risk subscore.
    """
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


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------


@router.post("/save")
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
# GET /report/{report_id}
# ---------------------------------------------------------------------------


@router.get("/report/{report_id}")
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
# GET /history  (data-025)
# ---------------------------------------------------------------------------


@router.get("/history")
def get_history(
    address: str = Query(..., description="US address to look up"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
) -> dict:
    """
    Return the most recent score history entries for a given US address.

    Response shape:
      {
        "address": "<address>",
        "history": [
          {
            "livability_score": 48,
            "disruption_score": 62,
            "confidence": "MEDIUM",
            "mode": "live",
            "scored_at": "<iso>"
          },
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
# GET /score-trend  (data-062)
# ---------------------------------------------------------------------------


@router.get("/score-trend", dependencies=[Depends(require_api_key)])
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
# GET /export/csv  (data-029)
# ---------------------------------------------------------------------------


@router.get("/export/csv", dependencies=[Depends(require_api_key)])
def export_csv(
    address: str = Query(..., description="US address to score and export"),
) -> StreamingResponse:
    """
    data-029: Export score results for an address as a CSV file.

    Returns one row per nearby project plus a summary row.
    Columns: distance_m, title, source, source_id, impact_type, status,
             start_date, end_date, address, weighted_score, livability_score,
             disruption_score.
    A summary row (distance_m=SUMMARY) captures livability_score,
    disruption_score, and confidence.
    Works in demo mode when DB is not configured.
    """
    livability_score: int | None = None

    # -- Live path -----------------------------------------------------------
    if _is_db_configured():
        try:
            from backend.ingest.geocode import geocode_address
            from backend.app.services.livability import _compute_livability_score, _extract_zip
            from backend.scoring.query import (
                compute_score,
                get_db_connection,
                get_nearby_projects,
                get_neighborhood_context,
            )

            conn = get_db_connection()
            try:
                coords = geocode_address(
                    address,
                    allow_national=True,
                    max_retries=1,
                    request_timeout=5,
                )
                if not coords:
                    raise ValueError(f"Could not geocode: {address!r}")
                lat, lon = coords
                nearby = get_nearby_projects(lat, lon, conn)
                result = compute_score(nearby, address)
                disruption_score = result.disruption_score
                confidence = result.confidence

                zip_code = _extract_zip(address)
                neighborhood_context = None
                try:
                    neighborhood_context = get_neighborhood_context(lat, lon, conn, zip_code=zip_code)
                except Exception as nq_exc:
                    log.debug("export_csv neighborhood_context skipped: %s", nq_exc)
                    try:
                        conn.rollback()
                    except Exception:
                        pass

                try:
                    livability_score, _ = _compute_livability_score(
                        disruption_score=disruption_score,
                        neighborhood_context=neighborhood_context,
                        lat=lat,
                        lon=lon,
                        conn=conn,
                        zip_code=zip_code,
                    )
                except Exception as liv_exc:
                    log.warning("export_csv livability_score unavailable: %s", liv_exc)
                    livability_score = None
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            finally:
                conn.close()

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
            livability_score = None
            disruption_score = 62
            confidence = "MEDIUM"
            project_rows = _DEMO_CSV_PROJECTS

    # -- Demo path -----------------------------------------------------------
    else:
        livability_score = DEMO_RESPONSE.get("livability_score")
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
            "address", "weighted_score", "livability_score", "disruption_score",
            # data-043: Claude-generated display fields (empty when not enriched)
            "display_title", "distance", "description", "why_it_matters",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()

    # Summary row first
    writer.writerow({
        "distance_m": "SUMMARY",
        "title": (
            f"livability_score={livability_score if livability_score is not None else 'unavailable'} "
            f"disruption_score={disruption_score} confidence={confidence}"
        ),
        "source": "", "source_id": "", "impact_type": "", "status": "",
        "start_date": "", "end_date": "",
        "address": address,
        "weighted_score": disruption_score,
        "livability_score": "" if livability_score is None else livability_score,
        "disruption_score": disruption_score,
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
