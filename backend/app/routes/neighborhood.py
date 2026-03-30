"""
backend/app/routes/neighborhood.py

Neighborhood-related endpoints extracted from main.py:
  - GET /neighborhood/{slug}              — neighborhood detail with projects
  - GET /neighborhoods                    — list all neighborhoods
  - GET /neighborhood/{slug}/best-streets — quietest/busiest block ranking
"""

import logging
import re

from fastapi import APIRouter, HTTPException

from backend.app.deps import _is_db_configured

log = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Neighborhood-only helper data & functions
# ---------------------------------------------------------------------------

_NEIGHBORHOOD_STREETS: dict[str, dict[str, list[str]]] = {
    "wicker-park":      {"quiet": ["N Wood St", "W Schiller St", "N Wolcott Ave", "W Pierce Ave", "N Paulina St"],
                         "busy":  ["N Milwaukee Ave", "N Damen Ave", "W North Ave", "W Division St", "N Ashland Ave"]},
    "logan-square":     {"quiet": ["N Spaulding Ave", "N Drake Ave", "N Sawyer Ave", "N Troy St", "N Kedzie Ave"],
                         "busy":  ["N Milwaukee Ave", "W Logan Blvd", "W Diversey Ave", "W Armitage Ave", "N California Ave"]},
    "river-north":      {"quiet": ["W Superior St", "W Huron St", "W Ohio St", "W Ontario St", "W Erie St"],
                         "busy":  ["N Michigan Ave", "N State St", "W Grand Ave", "W Chicago Ave", "N Orleans St"]},
    "lincoln-park":     {"quiet": ["W Belden Ave", "W Webster Ave", "W Dickens Ave", "N Racine Ave", "W Montana St"],
                         "busy":  ["N Clark St", "N Halsted St", "N Lincoln Ave", "W Diversey Pkwy", "W Fullerton Ave"]},
    "pilsen":           {"quiet": ["S Calumet Ave", "S Loomis St", "S Sangamon St", "S Morgan St", "S Carpenter St"],
                         "busy":  ["W Cermak Rd", "W 18th St", "W Blue Island Ave", "S Halsted St", "W 21st St"]},
    "loop":             {"quiet": ["N Franklin St", "N Wells St", "N LaSalle St", "N Dearborn St", "N Clark St"],
                         "busy":  ["N State St", "N Michigan Ave", "W Wacker Dr", "W Lake St", "W Madison St"]},
    "uptown":           {"quiet": ["W Winona St", "W Carmen Ave", "W Agatite Ave", "W Gunnison St", "W Sunnyside Ave"],
                         "busy":  ["N Broadway", "W Lawrence Ave", "W Wilson Ave", "N Sheridan Rd", "N Clark St"]},
    "bridgeport":       {"quiet": ["S Emerald Ave", "S Stewart Ave", "S Shields Ave", "S Wallace St", "S Princeton Ave"],
                         "busy":  ["S Halsted St", "W Archer Ave", "W 31st St", "W 35th St", "S Wentworth Ave"]},
    "old-town":         {"quiet": ["W Eugenie St", "W Menomonee St", "N Sedgwick St", "W Wisconsin St", "N Hudson Ave"],
                         "busy":  ["N Wells St", "N Clark St", "W North Ave", "W Division St", "N Larrabee St"]},
    "gold-coast":       {"quiet": ["E Schiller St", "E Goethe St", "E Banks St", "E Scott St", "E Bellevue Pl"],
                         "busy":  ["N Lake Shore Dr", "N Michigan Ave", "N Rush St", "N State St", "W Division St"]},
    "streeterville":    {"quiet": ["E Huron St", "E Erie St", "E Ontario St", "E Ohio St", "E Grand Ave"],
                         "busy":  ["N Michigan Ave", "N Lake Shore Dr", "E Illinois St", "E Chicago Ave", "N St Clair St"]},
    "south-loop":       {"quiet": ["S Plymouth Ct", "S Federal St", "S Dearborn St", "S State St", "S Wabash Ave"],
                         "busy":  ["S Michigan Ave", "S Indiana Ave", "W Roosevelt Rd", "S King Dr", "W Cermak Rd"]},
    "andersonville":    {"quiet": ["N Paulina St", "N Ashland Ave", "W Berwyn Ave", "W Catalpa Ave", "W Summerdale Ave"],
                         "busy":  ["N Clark St", "W Foster Ave", "W Balmoral Ave", "W Bryn Mawr Ave", "N Broadway"]},
    "rogers-park":      {"quiet": ["N Glenwood Ave", "N Greenview Ave", "N Paulina St", "W Chase Ave", "W Farwell Ave"],
                         "busy":  ["N Sheridan Rd", "N Clark St", "W Touhy Ave", "W Morse Ave", "W Howard St"]},
    "bucktown":         {"quiet": ["N Hoyne Ave", "N Leavitt St", "W McLean Ave", "N Oakley Ave", "W Moffat St"],
                         "busy":  ["N Damen Ave", "N Milwaukee Ave", "W Fullerton Ave", "W Armitage Ave", "N Western Ave"]},
    "ukrainian-village":{"quiet": ["N Oakley Blvd", "N Leavitt St", "W Iowa St", "W Thomas St", "W Augusta Blvd"],
                         "busy":  ["W Chicago Ave", "W Division St", "N Western Ave", "N Damen Ave", "W Rice St"]},
    "humboldt-park":    {"quiet": ["N Kedzie Ave", "N St Louis Ave", "W Cortez St", "W Thomas St", "W Augusta Blvd"],
                         "busy":  ["N Pulaski Rd", "W Chicago Ave", "W Division St", "N Western Ave", "W North Ave"]},
    "hyde-park":        {"quiet": ["E 53rd St", "E 54th St", "S Blackstone Ave", "S Dorchester Ave", "S Kimbark Ave"],
                         "busy":  ["S Lake Shore Dr", "S King Dr", "E 55th St", "E 63rd St", "S Cottage Grove Ave"]},
    "ravenswood":       {"quiet": ["W Berteau Ave", "W Sunnyside Ave", "N Hermitage Ave", "N Paulina St", "W Leland Ave"],
                         "busy":  ["N Ravenswood Ave", "W Lawrence Ave", "W Montrose Ave", "N Clark St", "W Wilson Ave"]},
    "avondale":         {"quiet": ["N Hamlin Ave", "N Kedzie Ave", "W Waveland Ave", "N Albany Ave", "W Melrose St"],
                         "busy":  ["N Milwaukee Ave", "N Pulaski Rd", "W Belmont Ave", "N Kimball Ave", "W Diversey Ave"]},
}

_BLOCK_IMPACT_WEIGHTS: dict[str, int] = {
    "closure_full": 35,
    "closure_multi_lane": 25,
    "closure_single_lane": 15,
    "demolition": 20,
    "construction": 15,
    "light_permit": 8,
}


def _get_last_ingest_time() -> str:
    """Return the ISO timestamp of the most recent successful ingest run.
    Falls back to the current UTC time if the table is absent or DB is unavailable."""
    import datetime
    if not _is_db_configured():
        return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    try:
        from backend.scoring.query import get_db_connection
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(finished_at) FROM ingest_runs WHERE status = 'success'"
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0].replace(microsecond=0).isoformat() + "Z"
        finally:
            conn.close()
    except Exception as exc:
        log.debug("ingest_runs query skipped: %s", exc)
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _extract_street_name(title: str | None) -> str | None:
    """Heuristic: pull the first recognizable street reference out of a permit title."""
    if not title:
        return None
    m = re.search(
        r"(\d+\s+)?([NSEW]\s+)?[\w\s]+"
        r"(?:Ave|Blvd|Ct|Cir|Dr|Expy|Hwy|Ln|Pkwy|Pl|Rd|St|Ter|Trl|Way)",
        title,
        re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _compute_blocks_from_projects(projects: list[dict]) -> list[dict]:
    """Aggregate raw projects into scored block cells (0.001 deg grid ~ 90 m)."""
    cells: dict[tuple[float, float], dict] = {}
    for p in projects:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None:
            continue
        key = (round(float(lat), 3), round(float(lon), 3))
        if key not in cells:
            cells[key] = {"score": 0, "count": 0, "street": _extract_street_name(p.get("title"))}
        cells[key]["score"] += _BLOCK_IMPACT_WEIGHTS.get(p.get("impact_type") or "", 8)
        cells[key]["count"] += 1

    blocks = []
    for (clat, _clon), cell in cells.items():
        street = cell["street"] or f"Block near {clat:.3f}\u00b0N"
        block_num = (int(abs(clat * 1000)) % 20) * 100 + 1000
        blocks.append({
            "block": f"{street} {block_num}\u2013{block_num + 99}",
            "avg_score": min(100, cell["score"]),
            "active_projects": cell["count"],
        })
    return blocks


def _make_demo_blocks(slug: str, median_score: int) -> list[dict]:
    """Generate plausible block data for demo mode from the street config."""
    streets = _NEIGHBORHOOD_STREETS.get(
        slug,
        {"quiet": ["N Main St", "W Side St", "N Oak Ave", "W Park Pl", "N Elm St"],
         "busy":  ["W Chicago Ave", "N State St", "W Madison St", "N Clark St", "S Michigan Ave"]},
    )
    blocks: list[dict] = []
    for i, street in enumerate(streets["quiet"][:5]):
        base = 1400 + i * 100
        score = max(2, min(18, median_score - 22 + (i % 3) * 4 - (i // 3) * 2))
        blocks.append({"block": f"{street} {base}\u2013{base + 99}", "avg_score": score, "active_projects": 0})
    for i, street in enumerate(streets["busy"][:5]):
        base = 1100 + i * 100
        score = min(92, max(median_score + 18 + i * 6, 45))
        blocks.append({"block": f"{street} {base}\u2013{base + 99}", "avg_score": score, "active_projects": 2 + i // 2})
    return blocks


def _format_month_year(iso: str) -> str:
    """Convert an ISO timestamp to 'March 2026' format."""
    import datetime
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %Y")
    except Exception:
        return "recent"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/neighborhood/{slug}")
def get_neighborhood(slug: str) -> dict:
    """
    Return neighborhood metadata and all active disruption projects within
    the neighborhood bounding box.

    slug:      one of the 8 pre-defined Chicago neighborhood slugs
    Returns:
      slug, name, description, center, bbox, projects (list), project_count, mode
    """
    from backend.app.routes.dashboard import _NEIGHBORHOODS, _get_projects_in_bbox

    neighborhood = _NEIGHBORHOODS.get(slug)
    if neighborhood is None:
        raise HTTPException(
            status_code=404,
            detail=f"Neighborhood '{slug}' not found. Valid slugs: {', '.join(_NEIGHBORHOODS)}",
        )

    bbox = neighborhood["bbox"]
    projects = _get_projects_in_bbox(
        bbox["min_lat"], bbox["min_lon"], bbox["max_lat"], bbox["max_lon"]
    )
    mode = "live" if _is_db_configured() else "demo"

    return {
        "slug": slug,
        "name": neighborhood["name"],
        "description": neighborhood["description"],
        "center": neighborhood["center"],
        "bbox": bbox,
        "projects": projects,
        "project_count": len(projects),
        "mode": mode,
        # Median disruption score for addresses in this neighborhood.
        # Currently a calibrated static value; will be replaced by a live
        # score_history aggregate query once address geocoding is stored.
        "median_score": neighborhood.get("median_score"),
        "sample_size": 0,
    }


@router.get("/neighborhoods")
def list_neighborhoods() -> dict:
    """
    Return the list of available neighborhood slugs and their names/centers.
    Used by the frontend to render a neighborhood index.
    """
    from backend.app.routes.dashboard import _NEIGHBORHOODS

    return {
        "neighborhoods": [
            {"slug": slug, "name": n["name"], "description": n["description"], "center": n["center"]}
            for slug, n in _NEIGHBORHOODS.items()
        ]
    }


@router.get("/neighborhood/{slug}/best-streets")
def get_neighborhood_best_streets(slug: str) -> dict:
    """
    Return the 5 quietest and 5 most disrupted blocks in a neighborhood.

    In live mode: aggregates active projects in the bbox into ~90-m grid cells
    and scores each cell by impact type weight.
    In demo mode: returns calibrated static block data derived from known
    high- and low-activity corridors for each neighborhood.

    Returns: slug, name, quietest_blocks, busiest_blocks, last_updated,
             mode, meta_description (unique, generated from real data).
    """
    from backend.app.routes.dashboard import _NEIGHBORHOODS, _get_projects_in_bbox

    neighborhood = _NEIGHBORHOODS.get(slug)
    if neighborhood is None:
        raise HTTPException(
            status_code=404,
            detail=f"Neighborhood '{slug}' not found. Valid slugs: {', '.join(_NEIGHBORHOODS)}",
        )

    name = neighborhood["name"]
    last_updated = _get_last_ingest_time()

    if _is_db_configured():
        bbox = neighborhood["bbox"]
        projects = _get_projects_in_bbox(
            bbox["min_lat"], bbox["min_lon"], bbox["max_lat"], bbox["max_lon"]
        )
        all_blocks = _compute_blocks_from_projects(projects)
        mode = "live"
    else:
        all_blocks = _make_demo_blocks(slug, neighborhood.get("median_score", 35))
        mode = "demo"

    quietest = sorted(all_blocks, key=lambda b: b["avg_score"])[:5]
    busiest  = sorted(all_blocks, key=lambda b: b["avg_score"], reverse=True)[:5]
    month_year = _format_month_year(last_updated)

    # Unique meta description generated from the actual block data.
    if quietest and busiest:
        q0, b0 = quietest[0], busiest[0]
        meta_description = (
            f"Find Chicago's quietest streets in {name}. "
            f"{q0['block']} has the lowest disruption score ({q0['avg_score']}/100) "
            f"while {b0['block']} has the highest active construction load "
            f"({b0['avg_score']}/100, {b0['active_projects']} active permit"
            f"{'s' if b0['active_projects'] != 1 else ''}). "
            f"Block-level disruption data for {name}, Chicago \u2014 updated {month_year}."
        )
    else:
        meta_description = (
            f"Block-level disruption intelligence for {name}, Chicago. "
            f"Quietest and most disrupted streets updated {month_year}."
        )

    return {
        "slug": slug,
        "name": name,
        "quietest_blocks": quietest,
        "busiest_blocks": busiest,
        "last_updated": last_updated,
        "mode": mode,
        "meta_description": meta_description,
    }
