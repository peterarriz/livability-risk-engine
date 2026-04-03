"""
backend/app/routes/score.py

Score-related endpoints extracted from main.py:
  - GET  /score           — single address scoring
  - POST /score/batch     — batch address scoring (JSON)
  - POST /score/batch/csv — batch address scoring (CSV upload)
  - GET  /debug/score     — operator debug endpoint
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.deps import (
    DEMO_RESPONSE,
    _build_demo_response,
    _is_db_configured,
    require_api_key,
    verify_api_key,
)
from backend.app.services.livability import _compute_livability_score, _extract_zip

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Core scoring function
# ---------------------------------------------------------------------------

def _score_live(address: str, coords: tuple[float, float] | None = None) -> dict:
    """
    Full live scoring path:
      1. Confirm the canonical DB is reachable
      2. Geocode address -> (lat, lon)
      3. Query nearby projects from canonical DB
      4. Apply scoring engine -> ScoreResult
      5. Query neighborhood quality context (data-040) -- non-fatal if table absent
      6. Enrich top_risk_details with Claude-rewritten titles (data-042, cache-first)
      7. Return as dict matching API contract (includes latitude/longitude)
    """
    from backend.ingest.geocode import geocode_address
    from backend.scoring.query import (
        compute_score,
        get_db_connection,
        get_hpi_context,
        get_nearby_crime_signals,
        get_nearby_projects,
        get_nearby_schools,
        get_neighborhood_context,
    )
    from backend.scoring.rewrite import enrich_top_risk_details

    conn = get_db_connection()
    try:
        resolved_coords = coords
        if resolved_coords is None:
            resolved_coords = geocode_address(address)
        if not resolved_coords:
            raise ValueError(f"Could not geocode address: {address!r}")

        lat, lon = resolved_coords
        nearby = get_nearby_projects(lat, lon, conn)

        # Neighborhood quality context (data-040, data-083).
        # Non-fatal: returns None if neighborhood_quality table is not yet populated.
        address_zip = _extract_zip(address)
        neighborhood_context = None
        try:
            neighborhood_context = get_neighborhood_context(lat, lon, conn, zip_code=address_zip)
        except Exception as nq_exc:
            log.debug("neighborhood_context lookup skipped: %s", nq_exc)
            try:
                conn.rollback()
            except Exception:
                pass

        result = compute_score(nearby, address)
        livability_score, livability_breakdown = _compute_livability_score(
            disruption_score=result.disruption_score,
            neighborhood_context=neighborhood_context,
            lat=lat,
            lon=lon,
            conn=conn,
            zip_code=address_zip,
        )
        result_dict = {
            **asdict(result),
            "livability_score": livability_score,
            "livability_breakdown": livability_breakdown,
            "mode": "live",
            "fallback_reason": None,
            "latitude": lat,
            "longitude": lon,
            "neighborhood_context": neighborhood_context,
        }

        # FHFA HPI context (data-083). Non-fatal; merges into neighborhood_context.
        try:
            hpi = get_hpi_context(address_zip, conn)
            if hpi:
                if result_dict["neighborhood_context"] is None:
                    result_dict["neighborhood_context"] = {}
                result_dict["neighborhood_context"].update(hpi)
        except Exception as hpi_exc:
            log.debug("hpi_context lookup skipped: %s", hpi_exc)
            try:
                conn.rollback()
            except Exception:
                pass

        # Crime trend map signal (data-054). Non-fatal if table absent.
        try:
            crime_signals = get_nearby_crime_signals(lat, lon, conn)
            if crime_signals:
                result_dict["nearby_signals"] = (
                    result_dict.get("nearby_signals") or []
                ) + crime_signals
        except Exception as crime_exc:
            log.debug("crime_signals lookup skipped: %s", crime_exc)
            try:
                conn.rollback()
            except Exception:
                pass

        # Nearby schools for map layer (data-061). Non-fatal if table absent.
        try:
            result_dict["nearby_schools"] = get_nearby_schools(lat, lon, conn)
        except Exception as school_exc:
            log.debug("nearby_schools lookup skipped: %s", school_exc)
            result_dict["nearby_schools"] = []
            try:
                conn.rollback()
            except Exception:
                pass

        # Enrich top_risk_details with Claude-rewritten titles and descriptions
        # (data-042).  Cache-first: only calls Claude for project_ids not yet
        # seen.  Non-fatal: falls back gracefully when API key is absent.
        result_dict["top_risk_details"] = enrich_top_risk_details(
            result_dict.get("top_risk_details") or [], conn
        )
    finally:
        conn.close()

    # Evidence quality assessment (data-085)
    nearby_signals = result_dict.get("nearby_signals") or []
    strong_signals = [
        s for s in nearby_signals
        if s.get("impact_type") not in (
            "light_permit", "crime_trend_stable",
            "crime_trend_decreasing", "crime_trend_increasing",
        )
    ]
    evidence_strength = (
        "strong" if len(strong_signals) >= 3
        else "moderate" if len(strong_signals) >= 1
        else "limited"
    )
    has_neighborhood = neighborhood_context is not None and any(
        v is not None for v in [
            neighborhood_context.get("crime_trend"),
            neighborhood_context.get("median_income"),
            neighborhood_context.get("fema_flood_zone"),
        ]
    )
    if evidence_strength == "limited" and not has_neighborhood:
        evidence_quality = "insufficient"
    elif evidence_strength == "limited":
        evidence_quality = "contextual_only"
    else:
        evidence_quality = evidence_strength

    result_dict["evidence_quality"] = evidence_quality
    result_dict["strong_signal_count"] = len(strong_signals)

    # Downgrade explanation language when evidence is thin.
    if evidence_quality == "insufficient":
        result_dict["explanation"] = (
            "Insufficient address-level data to assess disruption risk. "
            "This score should be treated as directional only."
        )
    elif evidence_quality == "contextual_only":
        # Reference the top signal if one exists, otherwise keep generic.
        top_details = result_dict.get("top_risk_details") or []
        if top_details:
            top = top_details[0]
            from backend.scoring.sanitize import sanitize_title
            title = top.get("display_title") or sanitize_title(top.get("title", ""))
            result_dict["explanation"] = (
                "Limited direct evidence for this address — the score is "
                "based primarily on neighborhood-level data. "
                f"The nearest relevant signal is {title.lower()}."
            )
        else:
            result_dict["explanation"] = (
                "Limited direct evidence for this address — the score is "
                "based primarily on neighborhood-level data."
            )

    return result_dict


# ---------------------------------------------------------------------------
# Score history helpers  (data-025)
# ---------------------------------------------------------------------------

def _write_score_history(address: str, result: dict) -> None:
    """
    Persist a live /score result to the score_history table.
    Intended for use as a BackgroundTask -- failures are logged but not raised.
    Only live-mode scores are written; demo results are silently skipped.
    """
    if result.get("mode") != "live":
        return
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO score_history (
                        address, disruption_score, livability_score, livability_breakdown,
                        confidence, mode, latitude, longitude
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                    """,
                    (
                        address,
                        result["disruption_score"],
                        result.get("livability_score", result["disruption_score"]),
                        json.dumps(result.get("livability_breakdown") or {}),
                        result["confidence"],
                        result.get("mode", "live"),
                        result.get("latitude"),
                        result.get("longitude"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        log.debug("score_history written address=%r score=%s", address, result["disruption_score"])
    except Exception as exc:
        log.warning("score_history write failed address=%r error=%s", address, exc)


# ---------------------------------------------------------------------------
# Batch scoring helpers  (data-045)
# ---------------------------------------------------------------------------

# Maximum addresses allowed in a single batch request.
_BATCH_MAX = 200

# Parallelism limit for geocoding + scoring worker threads.
_BATCH_WORKERS = 10


class BatchScoreRequest(BaseModel):
    addresses: list[str]


def _score_one(address: str) -> dict:
    """
    Score a single address. Returns a result dict with an 'error' key on failure.
    Designed to run inside a ThreadPoolExecutor worker.
    """
    try:
        result = _score_live(address)
        result.pop("nearby_signals", None)  # not included in batch output
        return result
    except Exception as exc:
        return {
            "address": address,
            "disruption_score": None,
            "confidence": None,
            "severity": None,
            "top_risks": None,
            "explanation": None,
            "mode": None,
            "error": str(exc),
        }


def _write_batch_history(results: list[dict], batch_id: str) -> None:
    """
    Persist live-mode results from a batch request to score_history.
    Writes all successful results in a single connection; failures are skipped.
    """
    live_results = [r for r in results if r.get("mode") == "live" and r.get("disruption_score") is not None]
    if not live_results:
        return
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                for r in live_results:
                    cur.execute(
                        """
                        INSERT INTO score_history (
                            address, disruption_score, livability_score, livability_breakdown,
                            confidence, mode, batch_id, latitude, longitude
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                        """,
                        (
                            r["address"],
                            r["disruption_score"],
                            r.get("livability_score", r["disruption_score"]),
                            json.dumps(r.get("livability_breakdown") or {}),
                            r["confidence"],
                            r["mode"],
                            batch_id,
                            r.get("latitude"),
                            r.get("longitude"),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()
        log.info("batch_history written batch_id=%s count=%d", batch_id, len(live_results))
    except Exception as exc:
        log.warning("batch_history write failed batch_id=%s error=%s", batch_id, exc)


@router.post("/score/batch", dependencies=[Depends(require_api_key)])
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


@router.post("/score/batch/csv", dependencies=[Depends(require_api_key)])
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


# ---------------------------------------------------------------------------
# GET /score endpoint
# ---------------------------------------------------------------------------

@router.get("/score", dependencies=[Depends(verify_api_key)])
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
    from backend.app.routes.dashboard import (
        _address_row_by_canonical_id,
        _debug_search_flow,
    )

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
# GET /debug/score endpoint (app-021)
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


@router.get("/debug/score")
def debug_score(
    address: str = Query(..., description="Chicago address to inspect"),
) -> dict:
    """
    Internal operator endpoint -- not part of the public API contract.

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
