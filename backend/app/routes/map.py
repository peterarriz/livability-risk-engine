"""
backend/app/routes/map.py

Map-related endpoints extracted from main.py:
  - POST /map/narrate   — AI map narration
  - POST /commute       — commute corridor scoring
  - GET  /nearby-amenities — OSM walkable amenities
  - GET  /api/live-signals — recent active disruption feed
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.app.deps import _is_db_configured, verify_api_key

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

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


class CommuteRequest(BaseModel):
    home: str   # origin / home address
    work: str   # destination / workplace address


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _commute_badge(score: int) -> str:
    if score <= 25:
        return "Low"
    if score <= 55:
        return "Moderate"
    return "High"


# ---------------------------------------------------------------------------
# POST /map/narrate
# ---------------------------------------------------------------------------

@router.post("/map/narrate")
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
# GET /nearby-amenities  (data-064)
# ---------------------------------------------------------------------------

_AMENITY_CACHE_TTL_DAYS = 7


@router.get("/nearby-amenities")
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
# GET /api/live-signals
# ---------------------------------------------------------------------------

@router.get("/api/live-signals")
def live_signals() -> dict:
    """
    Returns the 10 most recently started active disruption signals across
    all cities. Used by the landing page "Live across 50+ cities" feed.
    No authentication required — public endpoint.
    """
    if not _is_db_configured():
        return {"signals": []}
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
    except Exception:
        return {"signals": []}
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT source, address, impact_type, title, start_date
            FROM projects
            WHERE status = 'active'
              AND start_date IS NOT NULL
              AND address IS NOT NULL
            ORDER BY start_date DESC, id DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        signals = []
        for row in rows:
            source, address, impact_type, title, start_date = row
            # Extract city from address (last "City, ST" part) or source
            city = "Unknown"
            if address:
                parts = [p.strip() for p in address.split(",")]
                if len(parts) >= 2:
                    city = parts[-2] if len(parts) >= 3 else parts[0]
            signals.append({
                "city": city,
                "address": address,
                "impact_type": impact_type,
                "title": title,
                "start_date": str(start_date) if start_date else None,
                "source": source,
            })
        return {"signals": signals}
    except Exception:
        return {"signals": []}


# ---------------------------------------------------------------------------
# POST /commute
# ---------------------------------------------------------------------------

@router.post("/commute")
def check_commute(body: CommuteRequest) -> dict:
    """
    Score the disruption along a commute corridor between two addresses.

    Steps:
      1. Geocode home + work -> (lat, lon) pairs
      2. Build a bounding box (with 0.003 deg padding) enclosing the corridor
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
        # are included. 0.003 deg ~= 270 m at Chicago latitude.
        pad = 0.003
        min_lat = min(home_lat, work_lat) - pad
        max_lat = max(home_lat, work_lat) + pad
        min_lon = min(home_lon, work_lon) - pad
        max_lon = max(home_lon, work_lon) + pad

        # Import shared helpers from main (they are also used by /neighborhood)
        from backend.app.main import _get_projects_in_bbox, _BLOCK_IMPACT_WEIGHTS

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
