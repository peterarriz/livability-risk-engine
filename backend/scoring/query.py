"""
backend/scoring/query.py
task: data-009
lane: data

Radius query for nearby projects — the core data dependency for the
live /score endpoint (unblocks app-008).

Queries the canonical `projects` table for all active/planned projects
within a given radius of a lat/lon coordinate, ordered by distance.
Returns structured results the scoring engine can apply weights to.

This module is called by the scoring engine at request time:
  projects = get_nearby_projects(lat, lon, db, radius_m=500)
  score_result = compute_score(projects, lat, lon)

Usage (standalone test with DB):
  python backend/scoring/query.py --lat 41.8960 --lon -87.6704

Notes for app-008:
  Once this module exists, the /score endpoint can:
  1. Call geocode_address(address) → (lat, lon)
  2. Call get_nearby_projects(lat, lon, db) → list[NearbyProject]
  3. Call compute_score(nearby_projects) → ScoreResult
  The mocked response in backend/app/main.py can then be replaced
  with a real scoring call without changing the API contract shape.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# DB connection
# We use psycopg2 directly to keep dependencies minimal for the MVP.
# ---------------------------------------------------------------------------

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from backend.models.project import (
    BASE_WEIGHTS,
    IMPACT_CONSTRUCTION,
    IMPACT_DEMOLITION,
    IMPACT_FULL_CLOSURE,
    IMPACT_LIGHT_PERMIT,
    IMPACT_MULTI_LANE,
    IMPACT_ROAD_CONSTRUCTION,
    IMPACT_SINGLE_LANE,
    IMPACT_UTILITY_OUTAGE,
    IMPACT_UTILITY_REPAIR,
    Project,
)
from backend.scoring.sanitize import format_date, sanitize_notes, sanitize_title


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class NearbyProject:
    """A canonical project enriched with distance from the query point."""
    project: Project
    distance_m: float           # meters from query lat/lon


@dataclass
class ScoreResult:
    """
    Final output of the scoring engine.
    Shape matches docs/04_api_contracts.md exactly.
    top_risk_details added in data-024: structured metadata for permit drill-down.
    """
    address: str
    disruption_score: int       # 0–100
    confidence: str             # HIGH | MEDIUM | LOW
    severity: dict              # {noise: ..., traffic: ..., dust: ...}
    top_risks: list[str]        # up to 3 plain-English strings
    explanation: str            # 1 short paragraph
    top_risk_details: list      # list[dict] — structured metadata per top risk (data-024)
    # All scored nearby signals with lat/lon, for the map heat layer (fixed in bug-fix commit).
    # Previously built locally in compute_score() but never attached to the return value.
    nearby_signals: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

# Active statuses to include in scoring queries.
SCOREABLE_STATUSES = ("active", "planned", "unknown")

# Default search radius in meters.
DEFAULT_RADIUS_M = 500

# SQL query uses a haversine bounding-box pre-filter + exact haversine distance.
# No PostGIS required — works on Railway's standard Postgres.
#
# Parameter order: lon, lat, statuses, lat, lat, lon, lat_min, lat_max, lon_min, lon_max, radius_m
#
# The bounding-box WHERE clause uses the projects_location_idx composite index
# to avoid a full-table scan before computing haversine distance.
NEARBY_PROJECTS_SQL = """
    SELECT
        project_id,
        source,
        source_id,
        impact_type,
        title,
        notes,
        start_date,
        end_date,
        status,
        address,
        latitude,
        longitude,
        severity_hint,
        6371000.0 * 2.0 * asin(
            sqrt(
                power(sin(radians((latitude - %s) / 2.0)), 2) +
                cos(radians(%s)) * cos(radians(latitude)) *
                power(sin(radians((longitude - %s) / 2.0)), 2)
            )
        ) AS distance_m
    FROM projects
    WHERE
        status = ANY(%s)
        AND (end_date IS NULL OR end_date >= CURRENT_DATE - INTERVAL '30 days')
        AND latitude  IS NOT NULL
        AND longitude IS NOT NULL
        AND latitude  BETWEEN %s AND %s
        AND longitude BETWEEN %s AND %s
        AND 6371000.0 * 2.0 * asin(
            sqrt(
                power(sin(radians((latitude - %s) / 2.0)), 2) +
                cos(radians(%s)) * cos(radians(latitude)) *
                power(sin(radians((longitude - %s) / 2.0)), 2)
            )
        ) <= %s
    ORDER BY distance_m ASC
    LIMIT 20;
"""


def get_nearby_projects(
    lat: float,
    lon: float,
    db_conn,
    radius_m: int = DEFAULT_RADIUS_M,
) -> list[NearbyProject]:
    """
    Query the canonical projects table for all active/planned projects
    within radius_m meters of (lat, lon).

    Args:
        lat: Query latitude (WGS84).
        lon: Query longitude (WGS84).
        db_conn: An open psycopg2 connection.
        radius_m: Search radius in meters (default 500).

    Returns:
        List of NearbyProject sorted by ascending distance.
    """
    if not HAS_PSYCOPG2:
        raise ImportError(
            "psycopg2 is required for DB queries. "
            "Install with: pip install psycopg2-binary"
        )

    # Bounding box degrees for pre-filter.
    # 1° lat ≈ 111,320 m; 1° lon ≈ 111,320 * cos(lat) m.
    # Use slightly generous divisors so the bbox is never smaller than the radius.
    lat_delta = radius_m / 111_000.0
    lon_delta = radius_m / (111_000.0 * math.cos(math.radians(lat)) + 1e-9)

    with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            NEARBY_PROJECTS_SQL,
            (
                # SELECT distance_m expression params (lat, lat, lon)
                lat, lat, lon,
                # WHERE status
                list(SCOREABLE_STATUSES),
                # WHERE bounding box
                lat - lat_delta, lat + lat_delta,
                lon - lon_delta, lon + lon_delta,
                # WHERE haversine <= radius_m (lat, lat, lon, radius_m)
                lat, lat, lon, radius_m,
            ),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        project = Project(
            project_id=row["project_id"],
            source=row["source"],
            source_id=row["source_id"],
            impact_type=row["impact_type"],
            title=row["title"],
            notes=row["notes"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
            address=row["address"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            severity_hint=row["severity_hint"],
        )
        results.append(NearbyProject(project=project, distance_m=row["distance_m"]))

    return results


# ---------------------------------------------------------------------------
# Scoring engine
# Implements the heuristic rubric from docs/03_scoring_model.md.
# ---------------------------------------------------------------------------

def _distance_multiplier(distance_m: float) -> float:
    """Distance decay per docs/03_scoring_model.md."""
    if distance_m <= 75:
        return 1.00
    if distance_m <= 150:
        return 0.80
    if distance_m <= 300:
        return 0.55
    if distance_m <= 500:
        return 0.30
    return 0.10


def _time_multiplier(start_date: Optional[date], end_date: Optional[date]) -> float:
    """Timing multiplier per docs/03_scoring_model.md."""
    today = date.today()

    # Active now or ending within 7 days.
    if end_date and (today <= end_date <= date.fromordinal(today.toordinal() + 7)):
        return 1.00
    if end_date and end_date >= today and (start_date is None or start_date <= today):
        return 1.00  # currently active

    if start_date:
        days_until_start = (start_date - today).days
        if days_until_start < 0:
            # Already started.
            if end_date and end_date >= today:
                return 1.00  # active now
            if end_date and 0 <= (today - end_date).days <= 7:
                return 0.25  # recently ended, ambiguous
            return 0.25

        if days_until_start <= 7:
            return 0.90
        if days_until_start <= 21:
            return 0.65
        if days_until_start <= 45:
            return 0.35

    return 0.15  # stale or undated


def _weighted_score(nearby: NearbyProject) -> float:
    """
    Compute the weighted contribution of a single nearby project.
    base_weight × distance_multiplier × time_multiplier
    """
    base = BASE_WEIGHTS.get(nearby.project.impact_type, BASE_WEIGHTS[IMPACT_LIGHT_PERMIT])
    dist_mult = _distance_multiplier(nearby.distance_m)
    time_mult = _time_multiplier(nearby.project.start_date, nearby.project.end_date)
    return base * dist_mult * time_mult


def _derive_severity(contributions: list[tuple[NearbyProject, float]]) -> dict:
    """
    Derive severity for noise, traffic, and dust from weighted contributions.
    Per the severity alignment guidance in docs/03_scoring_model.md.
    """
    traffic_pts = sum(
        w for np, w in contributions
        if np.project.impact_type in (
            IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE,
            IMPACT_ROAD_CONSTRUCTION, IMPACT_UTILITY_OUTAGE,
        )
    )
    noise_pts = sum(
        w for np, w in contributions
        if np.project.impact_type in (
            IMPACT_DEMOLITION, IMPACT_CONSTRUCTION,
            IMPACT_UTILITY_OUTAGE, IMPACT_UTILITY_REPAIR,
        )
    )
    dust_pts = sum(
        w for np, w in contributions
        if np.project.impact_type in (IMPACT_DEMOLITION,)
    )

    def sev(pts: float, high_thresh: float, med_thresh: float) -> str:
        if pts >= high_thresh:
            return "HIGH"
        if pts >= med_thresh:
            return "MEDIUM"
        return "LOW"

    return {
        "noise":   sev(noise_pts,   18, 10),
        "traffic": sev(traffic_pts, 25, 12),
        "dust":    sev(dust_pts,    18, 10),
    }


def _derive_confidence(contributions: list[tuple[NearbyProject, float]]) -> str:
    """
    Derive confidence from evidence quality of the top contributors.
    Per the confidence ladder in docs/03_scoring_model.md.
    """
    if not contributions:
        return "LOW"

    top_np, top_w = contributions[0]
    today = date.today()

    # HIGH: recent, specific, directly tied to address-level disruption.
    if (
        top_np.project.impact_type in (IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE)
        and top_np.project.start_date
        and top_np.project.end_date
        and top_np.project.start_date <= today <= top_np.project.end_date
        and top_w >= 20
    ):
        return "HIGH"

    # MEDIUM: plausible but still somewhat ambiguous.
    if top_w >= 12 and top_np.project.status in ("active", "planned"):
        return "MEDIUM"

    return "LOW"


def _build_top_risks(
    contributions: list[tuple[NearbyProject, float]],
) -> list[str]:
    """
    Build up to 3 plain-English top-risk strings per the contract.
    Per docs/04_api_contracts.md: display-ready strings the frontend
    renders directly without further parsing.
    """
    risks = []
    for nearby, weight in contributions[:3]:
        p = nearby.project
        title = sanitize_title(p.title)
        dist_str = f"within roughly {int(nearby.distance_m)} meters"

        # Build the risk string from what we know.
        if p.impact_type == IMPACT_FULL_CLOSURE:
            risk = f"Full street closure on {title} {dist_str}"
        elif p.impact_type == IMPACT_MULTI_LANE:
            risk = f"Multi-lane closure on {title} {dist_str}"
        elif p.impact_type == IMPACT_SINGLE_LANE:
            risk = f"Lane or curb closure near {title} {dist_str}"
        elif p.impact_type == IMPACT_DEMOLITION:
            risk = f"Active demolition or excavation near {title} {dist_str}"
        elif p.impact_type == IMPACT_ROAD_CONSTRUCTION:
            risk = f"Active road reconstruction or resurfacing near {title} {dist_str}"
        elif p.impact_type == IMPACT_CONSTRUCTION:
            risk = f"Active construction permit near {title} {dist_str}"
        elif p.impact_type == IMPACT_UTILITY_OUTAGE:
            risk = f"Active utility emergency near {title} {dist_str}"
        else:
            risk = f"Nearby permit activity: {title} {dist_str}"

        # Append active window if available — human-readable date, not ISO.
        if p.end_date:
            risk += f"; active through {format_date(p.end_date)}"

        risks.append(risk)

    return risks


def _temporal_status(start_date_str: str | None, end_date_str: str | None) -> str:
    """Classify a signal's temporal status relative to today."""
    today = date.today()
    start = date.fromisoformat(start_date_str) if start_date_str else None
    end = date.fromisoformat(end_date_str) if end_date_str else None

    if end and end < today:
        return "recently_ended"
    if start and start > today:
        days_until = (start - today).days
        if days_until <= 7:
            return "starts_soon"
        return "upcoming"
    if end:
        days_left = (end - today).days
        if days_left <= 7:
            return "ending_soon"
    return "active_now"


# Attribution strength ranking: lower = stronger.
_ATTRIBUTION_RANK = {"direct": 0, "nearby": 1, "area_context": 2}


def _signal_attribution(impact_type: str, distance_m: float) -> str:
    """Classify how directly a signal relates to the scored address."""
    if impact_type.startswith("crime_trend"):
        return "area_context"
    if distance_m < 50:
        return "direct"
    if distance_m <= 200:
        return "nearby"
    return "area_context"


def _build_top_risk_details(
    contributions: list[tuple[NearbyProject, float]],
    limit: int = 10,
) -> list[dict]:
    """
    Build structured permit/closure detail dicts for scoring contributions.
    Takes more than the final display count so clustering can group nearby
    same-street signals before the top N are selected.

    _lat/_lon are temporary fields used by _cluster_risk_details for
    distance computation and stripped before the response is sent.
    """
    details = []
    for nearby, weight in contributions[:limit]:
        p = nearby.project
        attribution = _signal_attribution(p.impact_type, nearby.distance_m)
        details.append({
            "project_id": p.project_id,
            "source": p.source,
            "source_id": p.source_id,
            "impact_type": p.impact_type,
            "title": sanitize_title(p.title),
            "notes": sanitize_notes(p.notes),
            "status": p.status,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "address": p.address,
            "distance_m": round(nearby.distance_m),
            "weighted_score": round(weight, 1),
            "attribution": attribution,
            "temporal_status": _temporal_status(
                p.start_date.isoformat() if p.start_date else None,
                p.end_date.isoformat() if p.end_date else None,
            ),
            # Temporary: used for clustering distance calc, stripped later.
            "_lat": p.latitude,
            "_lon": p.longitude,
        })
    return details


# ---------------------------------------------------------------------------
# Signal clustering — group nearby same-street signals into parent cards
# ---------------------------------------------------------------------------

_CLOSURE_IMPACT_GROUP = frozenset({
    IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE,
})
_CONSTRUCTION_IMPACT_GROUP = frozenset({
    IMPACT_CONSTRUCTION, IMPACT_ROAD_CONSTRUCTION, IMPACT_DEMOLITION,
})
_UTILITY_IMPACT_GROUP = frozenset({
    IMPACT_UTILITY_OUTAGE, IMPACT_UTILITY_REPAIR,
})

# Human-readable group names for synthesized cluster titles.
_GROUP_LABELS = {
    "closure": "closure",
    "closures": "closures",
    "construction": "construction permit",
    "constructions": "construction permits",
    "utility": "utility signal",
    "utilities": "utility signals",
    "other": "signal",
    "others": "signals",
}


def _impact_group(impact_type: str) -> str:
    """Return a group key for clustering compatibility."""
    if impact_type in _CLOSURE_IMPACT_GROUP:
        return "closure"
    if impact_type in _CONSTRUCTION_IMPACT_GROUP:
        return "construction"
    if impact_type in _UTILITY_IMPACT_GROUP:
        return "utility"
    return "other"


def _extract_street(address: str | None) -> str | None:
    """
    Extract a normalized street name from an address string.
    "713 W Ohio St, Chicago, IL" → "W OHIO"
    "4306 N Lexington St" → "N LEXINGTON"
    """
    if not address:
        return None
    # Take the portion before any comma (strip city/state).
    street_part = address.split(",")[0].strip().upper()
    # Remove leading street number.
    parts = street_part.split(None, 1)
    if len(parts) >= 2 and parts[0].isdigit():
        street_part = parts[1]
    # Strip common suffixes: ST, AVE, BLVD, DR, RD, CT, PL, WAY, LN, PKWY
    street_part = re.sub(
        r"\s+(ST|AVE|AVENUE|BLVD|BOULEVARD|DR|DRIVE|RD|ROAD|CT|COURT|PL|PLACE|WAY|LN|LANE|PKWY|PARKWAY|TER|TERRACE|CIR|CIRCLE)\b\.?$",
        "",
        street_part,
    )
    return street_part.strip() or None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Quick haversine distance in meters between two points."""
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cluster_risk_details(details: list[dict], max_distance_m: float = 200.0) -> list[dict]:
    """
    Cluster nearby same-street signals into parent cards.

    Two signals belong to the same cluster if:
    - They share the same street name
    - They are within max_distance_m of each other
    - They have compatible impact types (same group)

    Returns a new list where clustered signals are merged into parent
    cards with children arrays.  Standalone signals get children=None,
    cluster_count=1.
    """
    if len(details) <= 1:
        for d in details:
            d["children"] = None
            d["cluster_count"] = 1
        return details

    # Assign each detail to a cluster.
    n = len(details)
    cluster_ids = list(range(n))  # union-find parent

    def find(i: int) -> int:
        while cluster_ids[i] != i:
            cluster_ids[i] = cluster_ids[cluster_ids[i]]
            i = cluster_ids[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            cluster_ids[ri] = rj

    for i in range(n):
        si = details[i]
        street_i = _extract_street(si.get("address"))
        group_i = _impact_group(si.get("impact_type", ""))
        lat_i = si.get("_lat")
        lon_i = si.get("_lon")

        for j in range(i + 1, n):
            sj = details[j]
            # Same impact group?
            if _impact_group(sj.get("impact_type", "")) != group_i:
                continue
            # Same street?
            street_j = _extract_street(sj.get("address"))
            if not street_i or not street_j or street_i != street_j:
                continue
            # Within distance?
            lat_j = sj.get("_lat")
            lon_j = sj.get("_lon")
            if lat_i and lon_i and lat_j and lon_j:
                dist = _haversine_m(lat_i, lon_i, lat_j, lon_j)
                if dist > max_distance_m:
                    continue
            union(i, j)

    # Group by cluster root.
    from collections import defaultdict
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    result = []
    for indices in groups.values():
        members = [details[i] for i in indices]
        if len(members) == 1:
            m = members[0]
            m.pop("_lat", None)
            m.pop("_lon", None)
            m["children"] = None
            m["cluster_count"] = 1
            result.append(m)
        else:
            # Build synthesized parent card.
            group_key = _impact_group(members[0].get("impact_type", ""))
            street = _extract_street(members[0].get("address"))
            count = len(members)
            plural_key = group_key + "s" if group_key in _GROUP_LABELS else "others"
            type_label = _GROUP_LABELS.get(
                plural_key if count > 1 else group_key,
                "signals" if count > 1 else "signal",
            )

            # Clean up internal fields from children.
            for m in members:
                m.pop("_lat", None)
                m.pop("_lon", None)
                m["children"] = None
                m["cluster_count"] = 1

            # Synthesize parent fields.
            start_dates = [m["start_date"] for m in members if m.get("start_date")]
            end_dates = [m["end_date"] for m in members if m.get("end_date")]

            parent = {
                "project_id": members[0]["project_id"],
                "source": members[0]["source"],
                "source_id": members[0]["source_id"],
                "impact_type": members[0]["impact_type"],
                "title": f"{count} {type_label} on {street or 'nearby street'}",
                "notes": None,
                "status": members[0]["status"],
                "start_date": min(start_dates) if start_dates else None,
                "end_date": max(end_dates) if end_dates else None,
                "address": members[0].get("address"),
                "distance_m": min(m["distance_m"] for m in members),
                "weighted_score": round(sum(m["weighted_score"] for m in members), 1),
                # Strongest child attribution wins (direct > nearby > area_context).
                "attribution": min(
                    (m.get("attribution", "area_context") for m in members),
                    key=lambda a: _ATTRIBUTION_RANK.get(a, 99),
                ),
                "children": members,
                "cluster_count": count,
            }
            result.append(parent)

    # Sort by weighted_score descending to preserve ranking.
    result.sort(key=lambda d: d.get("weighted_score", 0), reverse=True)
    return result


def _clean_signal_name(title: str, address: str | None) -> str:
    """
    Extract a short, plain-English location reference for use in the
    explanation sentence.  Strips parenthetical permit types, street
    number ranges, and falls back to the project address if the title
    is still noisy.

    Examples:
        "Ohio between 713-733 (Opening in the Public Way) closure"
            → "W Ohio St"  (from address fallback)
        "161 N Clark St building renovation"
            → "161 N Clark St"
    """
    # Prefer the address field if it looks like a street address — it's
    # cleaner than the raw permit title.
    if address:
        addr = address.strip()
        # Use address if it starts with a number or directional
        if re.match(r"^(\d|[NSEW]\s)", addr):
            # Take just the street portion (before any city/state)
            street_part = addr.split(",")[0].strip()
            if street_part:
                return street_part

    cleaned = sanitize_title(title)
    # Strip parenthetical noise: "(Opening in the Public Way)", etc.
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned)
    # Strip street number ranges like "between 713-733" or "713–733"
    cleaned = re.sub(r"\s*between\s+\d+[\-–]\d+", "", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or sanitize_title(title)


# Plain-English cause labels keyed by impact_type.
# "verdict_cause" reads after "from" in sentence 1 (e.g. "from nearby lane closures").
# "signal_cause" reads after "is" in sentence 2 (e.g. "is a lane closure on…").
_CAUSE_VERDICT: dict[str | None, str] = {
    IMPACT_FULL_CLOSURE: "street closures",
    IMPACT_MULTI_LANE: "lane closures",
    IMPACT_SINGLE_LANE: "lane closures",
    IMPACT_ROAD_CONSTRUCTION: "road construction",
    IMPACT_DEMOLITION: "demolition activity",
    IMPACT_CONSTRUCTION: "active construction",
    IMPACT_UTILITY_OUTAGE: "a utility emergency",
}
_CAUSE_SIGNAL: dict[str | None, str] = {
    IMPACT_FULL_CLOSURE: "a full street closure",
    IMPACT_MULTI_LANE: "a multi-lane closure",
    IMPACT_SINGLE_LANE: "a lane closure",
    IMPACT_ROAD_CONSTRUCTION: "road construction",
    IMPACT_DEMOLITION: "demolition work",
    IMPACT_CONSTRUCTION: "a construction project",
    IMPACT_UTILITY_OUTAGE: "a utility emergency",
}

# Disruption category per impact type, used in sentence 1.
_DISRUPTION_CATEGORIES: dict[str | None, str] = {
    IMPACT_FULL_CLOSURE: "traffic disruption",
    IMPACT_MULTI_LANE: "traffic disruption",
    IMPACT_SINGLE_LANE: "traffic disruption",
    IMPACT_ROAD_CONSTRUCTION: "traffic and access disruption",
    IMPACT_DEMOLITION: "noise and dust disruption",
    IMPACT_CONSTRUCTION: "noise disruption",
    IMPACT_UTILITY_OUTAGE: "traffic and service disruption",
}


def _build_explanation(
    contributions: list[tuple[NearbyProject, float]],
    severity: dict,
) -> str:
    """
    Build a concise 2-sentence explanation.

    Sentence 1: Verdict — what's happening and what it means.
    Sentence 2: Strongest evidence — the single most impactful signal, simplified.
    """
    if not contributions:
        return (
            "Low disruption risk — no significant construction or closures "
            "detected nearby. The nearest signals are minor permits with "
            "limited impact."
        )

    top_np, _ = contributions[0]
    p = top_np.project

    verdict_cause = _CAUSE_VERDICT.get(p.impact_type, "permitted work")
    signal_cause = _CAUSE_SIGNAL.get(p.impact_type, "permitted work")
    category = _DISRUPTION_CATEGORIES.get(p.impact_type, "minor disruption")
    location = _clean_signal_name(p.title, p.address)

    # Sentence 1: verdict
    sentence1 = (
        f"This address has elevated short-term {category} from nearby {verdict_cause}."
    )

    # Sentence 2: strongest signal with optional timing
    if p.end_date:
        sentence2 = (
            f"The strongest signal is {signal_cause} on {location}, "
            f"active through {format_date(p.end_date)}."
        )
    else:
        sentence2 = (
            f"The strongest signal is {signal_cause} on {location}."
        )

    return f"{sentence1} {sentence2}"


# ---------------------------------------------------------------------------
# Closure line geometry estimation
# ---------------------------------------------------------------------------

_RANGE_RE = re.compile(
    r"(?:from\s+(\d+)\s+to\s+(\d+))"   # "from 4306 to 4354"
    r"|(?:(\d+)\s*[-–]\s*(\d+))",        # "4306-4354" or "4306–4354"
)

_CLOSURE_TYPES = frozenset({
    IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE,
})

# Chicago grid: ~800 address numbers = 1 mile = 1609m
_ADDR_PER_MILE = 800
_METERS_PER_MILE = 1609.0
_MIN_SEGMENT_M = 50.0
_MAX_SEGMENT_M = 500.0
_METERS_PER_LAT_DEG = 111_000.0


def _estimate_closure_geometry(
    title: str,
    address: str | None,
    lat: float,
    lon: float,
) -> dict | None:
    """
    Estimate line_start/line_end for a closure signal using Chicago's
    address grid system.  Returns {"line_start": [lat,lon], "line_end": [lat,lon]}
    or None if the signal can't be mapped to a line.
    """
    import math

    # 1. Parse address range from title
    m = _RANGE_RE.search(title or "")
    if m:
        lo = int(m.group(1) or m.group(3))
        hi = int(m.group(2) or m.group(4))
        length_m = abs(hi - lo) / _ADDR_PER_MILE * _METERS_PER_MILE
    else:
        # No range found — use a sensible default for closures
        length_m = 120.0

    # 2. Clamp
    length_m = max(_MIN_SEGMENT_M, min(_MAX_SEGMENT_M, length_m))

    # 3. Determine orientation from address or title
    #    N/S addresses → street runs north-south → offset latitude
    #    W/E addresses → street runs east-west → offset longitude
    orientation = _detect_orientation(address, title)

    # 4. Compute start/end by offsetting from center
    half = length_m / 2.0
    if orientation == "ns":
        # North-south street: offset latitude
        delta_lat = half / _METERS_PER_LAT_DEG
        return {
            "line_start": [lat - delta_lat, lon],
            "line_end": [lat + delta_lat, lon],
        }
    else:
        # East-west street: offset longitude
        meters_per_lon_deg = _METERS_PER_LAT_DEG * math.cos(math.radians(lat))
        delta_lon = half / meters_per_lon_deg
        return {
            "line_start": [lat, lon - delta_lon],
            "line_end": [lat, lon + delta_lon],
        }


def _detect_orientation(address: str | None, title: str | None) -> str:
    """Return 'ns' for north-south streets, 'ew' for east-west (default)."""
    for text in (address, title):
        if not text:
            continue
        stripped = text.strip()
        # Check leading directional: "N ", "S " → NS; "W ", "E " → EW
        if stripped[:2] in ("N ", "S "):
            return "ns"
        if stripped[:2] in ("W ", "E "):
            return "ew"
        # Check after street number: "123 N Clark" or "4306 N LEXINGTON"
        parts = stripped.split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit():
            if parts[1] in ("N", "S", "North", "South"):
                return "ns"
            if parts[1] in ("W", "E", "West", "East"):
                return "ew"
    return "ew"  # Default: east-west


def compute_score(
    nearby: list[NearbyProject],
    address: str,
) -> ScoreResult:
    """
    Apply the heuristic scoring model to a list of nearby projects.

    Implements the aggregation rules from docs/03_scoring_model.md:
    - Score each project: base_weight × distance_mult × time_mult
    - Sum the top 3 contributions
    - Cap at 100

    Args:
        nearby: List of NearbyProject from get_nearby_projects().
        address: The original query address string (echoed in response).

    Returns:
        A ScoreResult matching the docs/04_api_contracts.md shape.
    """
    if not nearby:
        return ScoreResult(
            address=address,
            disruption_score=0,
            confidence="LOW",
            severity={"noise": "LOW", "traffic": "LOW", "dust": "LOW"},
            top_risks=["No significant construction or closure activity found nearby."],
            explanation=(
                "Low disruption risk — no significant construction or closures "
                "detected nearby. The nearest signals are minor permits with "
                "limited impact."
            ),
            top_risk_details=[],
        )

    # Score all nearby projects.
    scored = [(np, _weighted_score(np)) for np in nearby]

    # Sort by weighted contribution descending, take top 3.
    scored.sort(key=lambda x: x[1], reverse=True)
    top3 = scored[:3]

    # Sum top 3 contributions and cap at 100.
    raw_score = sum(w for _, w in top3)
    disruption_score = min(100, int(round(raw_score)))

    severity = _derive_severity(top3)
    confidence = _derive_confidence(top3)
    top_risks = _build_top_risks(top3)
    # Build details from more signals (up to 10) so clustering can group
    # same-street signals, then take the top 3 clusters for display.
    top_risk_details_raw = _build_top_risk_details(scored, limit=10)
    top_risk_details = _cluster_risk_details(top_risk_details_raw)[:3]
    explanation = _build_explanation(top3, severity)

    # Build nearby_signals for the map heat layer.
    # Include all scored projects that have valid coordinates (not just top 3).
    nearby_signals = []
    for np, weight in scored:
        p = np.project
        if p.latitude is None or p.longitude is None:
            continue
        signal: dict = {
            "project_id": p.project_id,
            "lat": p.latitude,
            "lon": p.longitude,
            "impact_type": p.impact_type,
            "title": p.title,
            "address": p.address,
            "source": p.source,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "distance_m": round(np.distance_m),
            "severity_hint": p.severity_hint,
            "weight": round(weight, 1),
            "temporal_status": _temporal_status(
                p.start_date.isoformat() if p.start_date else None,
                p.end_date.isoformat() if p.end_date else None,
            ),
        }
        # Add estimated line geometry for closure signals.
        if p.impact_type in _CLOSURE_TYPES:
            geom = _estimate_closure_geometry(
                p.title, p.address, p.latitude, p.longitude,
            )
            if geom:
                signal.update(geom)
        nearby_signals.append(signal)

    return ScoreResult(
        address=address,
        disruption_score=disruption_score,
        confidence=confidence,
        severity=severity,
        top_risks=top_risks,
        explanation=explanation,
        top_risk_details=top_risk_details,
        nearby_signals=nearby_signals,
    )


# ---------------------------------------------------------------------------
# Neighborhood quality context lookup  (data-040)
# ---------------------------------------------------------------------------

NEIGHBORHOOD_CONTEXT_SQL = {
    "flood": """
        SELECT fema_flood_zone, flood_risk
        FROM neighborhood_quality
        WHERE region_type = 'flood_zone' AND geom IS NOT NULL
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1;
    """,
    "crime": """
        SELECT crime_12mo, crime_prior_12mo, crime_trend, crime_trend_pct
        FROM neighborhood_quality
        WHERE region_type = 'community_area' AND geom IS NOT NULL
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1;
    """,
    "census": """
        SELECT median_income, population, vacancy_rate, housing_age_med
        FROM neighborhood_quality
        WHERE region_type = 'census_tract' AND geom IS NOT NULL
        ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        LIMIT 1;
    """,
    "hpi_zip": """
        SELECT hpi_index_value, hpi_1yr_change, hpi_5yr_change,
               hpi_10yr_change, hpi_period
        FROM neighborhood_quality
        WHERE region_type = 'zip' AND region_id = %s
        LIMIT 1;
    """,
    "hpi_metro": """
        SELECT hpi_index_value, hpi_1yr_change, hpi_5yr_change,
               hpi_10yr_change, hpi_period
        FROM neighborhood_quality
        WHERE region_type = 'metro' AND hpi_index_value IS NOT NULL
        ORDER BY hpi_period DESC NULLS LAST
        LIMIT 1;
    """,
}


def get_neighborhood_context(
    lat: float,
    lon: float,
    db_conn,
    zip_code: Optional[str] = None,
) -> dict | None:
    """
    Return neighborhood quality context for a lat/lon coordinate.

    Performs KNN spatial queries against the neighborhood_quality table:
      1. Nearest flood zone record (FEMA flood risk)
      2. Nearest community area record (Chicago crime trend)
      3. Nearest census tract record (Census ACS demographics)
      4. FHFA HPI fields by zip code, falling back to metro (data-083)

    Returns a dict with all available fields, or None if the table is empty
    or does not exist yet (graceful degradation before data-040 ingest runs).

    Args:
        lat: Query latitude (WGS84).
        lon: Query longitude (WGS84).
        db_conn: An open psycopg2 connection.
        zip_code: 5-digit ZIP code string for HPI lookup (optional).

    Returns:
        Dict with neighborhood context fields, or None.
    """
    if not HAS_PSYCOPG2:
        return None

    context: dict = {}

    try:
        with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Flood zone
            cur.execute(NEIGHBORHOOD_CONTEXT_SQL["flood"], (lon, lat))
            row = cur.fetchone()
            if row:
                context["fema_flood_zone"] = row["fema_flood_zone"]
                context["flood_risk"] = row["flood_risk"]

            # Crime trend
            cur.execute(NEIGHBORHOOD_CONTEXT_SQL["crime"], (lon, lat))
            row = cur.fetchone()
            if row:
                context["crime_trend"] = row["crime_trend"]
                context["crime_trend_pct"] = (
                    float(row["crime_trend_pct"])
                    if row["crime_trend_pct"] is not None
                    else None
                )
                context["crime_12mo"] = row["crime_12mo"]

            # Census ACS demographics
            cur.execute(NEIGHBORHOOD_CONTEXT_SQL["census"], (lon, lat))
            row = cur.fetchone()
            if row:
                context["median_income"] = row["median_income"]
                context["population"] = row["population"]
                context["vacancy_rate"] = (
                    float(row["vacancy_rate"])
                    if row["vacancy_rate"] is not None
                    else None
                )
                context["housing_age_med"] = row["housing_age_med"]

    except Exception:
        # neighborhood_quality table may not exist yet (pre data-040 schema).
        # Return None so the /score endpoint degrades gracefully.
        return None

    # FHFA HPI lookup (data-083): zip-level first, metro fallback.
    # Non-fatal: skip if table/columns are absent or zip_code not provided.
    if zip_code:
        try:
            with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                hpi_row = None

                # Try zip-level first
                cur.execute(NEIGHBORHOOD_CONTEXT_SQL["hpi_zip"], (zip_code,))
                row = cur.fetchone()
                if row and row["hpi_1yr_change"] is not None:
                    hpi_row = row

                # Fall back to metro if zip-level missing or HPI columns null
                if hpi_row is None:
                    cur.execute(NEIGHBORHOOD_CONTEXT_SQL["hpi_metro"])
                    row = cur.fetchone()
                    if row and row["hpi_1yr_change"] is not None:
                        hpi_row = row

                if hpi_row is not None:
                    context["hpi_index_value"] = (
                        float(hpi_row["hpi_index_value"])
                        if hpi_row["hpi_index_value"] is not None
                        else None
                    )
                    context["hpi_1yr_change"] = (
                        float(hpi_row["hpi_1yr_change"])
                        if hpi_row["hpi_1yr_change"] is not None
                        else None
                    )
                    context["hpi_5yr_change"] = (
                        float(hpi_row["hpi_5yr_change"])
                        if hpi_row["hpi_5yr_change"] is not None
                        else None
                    )
                    context["hpi_10yr_change"] = (
                        float(hpi_row["hpi_10yr_change"])
                        if hpi_row["hpi_10yr_change"] is not None
                        else None
                    )
                    context["hpi_period"] = hpi_row["hpi_period"]
        except Exception:
            # HPI columns may not exist yet (pre data-081 schema).
            # Skip gracefully; neighborhood_context still returns other fields.
            pass

    return context if context else None


# ---------------------------------------------------------------------------
# FHFA HPI context  (data-083)
# ---------------------------------------------------------------------------

def get_hpi_context(zip_code: str | None, conn) -> dict | None:
    """
    Return FHFA House Price Index fields for a zip code.

    Queries neighborhood_quality for region_type='zip' first; falls back to
    region_type='metro' with the Chicago MSA code (16980) when no zip-level
    row is found.  Returns None if the table/columns are absent or zip is None.

    Args:
        zip_code: 5-digit zip string, or None.
        conn: An open psycopg2 connection.

    Returns:
        Dict with hpi_* fields, or None.
    """
    if not HAS_PSYCOPG2 or not zip_code:
        return None

    _HPI_FIELDS = (
        "hpi_index_value", "hpi_1yr_change", "hpi_5yr_change",
        "hpi_10yr_change", "hpi_period",
    )

    def _row_to_hpi(row) -> dict | None:
        if row is None:
            return None
        result = {}
        for field in _HPI_FIELDS:
            val = row[field]
            if val is not None:
                result[field] = float(val) if field != "hpi_period" else val
        return result if result else None

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Zip-level lookup
            cur.execute(NEIGHBORHOOD_CONTEXT_SQL["hpi_zip"], (zip_code,))
            hpi = _row_to_hpi(cur.fetchone())
            if hpi:
                return hpi

            # Metro fallback: Chicago-Naperville-Elgin MSA (CBSA 16980)
            cur.execute(NEIGHBORHOOD_CONTEXT_SQL["hpi_metro"], ("16980",))
            return _row_to_hpi(cur.fetchone())

    except Exception as exc:
        log.debug("get_hpi_context skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Crime trend map signals  (data-054)
# ---------------------------------------------------------------------------

# SQL fetches the nearest community_area record from neighborhood_quality,
# extracts centroid lat/lon from the stored POINT geometry, and computes
# haversine distance from the query coordinate.
CRIME_SIGNALS_SQL = """
    SELECT
        region_id,
        crime_12mo,
        crime_prior_12mo,
        crime_trend,
        crime_trend_pct,
        ST_Y(geom) AS centroid_lat,
        ST_X(geom) AS centroid_lon,
        6371000.0 * 2.0 * asin(
            sqrt(
                power(sin(radians((ST_Y(geom) - %s) / 2.0)), 2) +
                cos(radians(%s)) * cos(radians(ST_Y(geom))) *
                power(sin(radians((ST_X(geom) - %s) / 2.0)), 2)
            )
        ) AS distance_m
    FROM neighborhood_quality
    WHERE region_type = 'community_area' AND geom IS NOT NULL
    ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
    LIMIT 1;
"""

# Maps crime_trend string from the DB → synthetic impact_type for the map.
_CRIME_TREND_IMPACT = {
    "INCREASING": "crime_trend_increasing",
    "DECREASING": "crime_trend_decreasing",
    "STABLE":     "crime_trend_stable",
}


def get_nearby_crime_signals(
    lat: float,
    lon: float,
    db_conn,
) -> list[dict]:
    """
    Return a synthetic nearby_signals entry for the nearest crime community area.

    Queries neighborhood_quality for the nearest community_area record using
    PostGIS KNN ordering and haversine distance math. Maps crime_trend to a
    synthetic impact_type (crime_trend_increasing / _decreasing / _stable)
    and returns a signal dict in the same shape as nearby_signals from
    compute_score() so the map renderer can display it without changes.

    Args:
        lat: Query latitude (WGS84).
        lon: Query longitude (WGS84).
        db_conn: An open psycopg2 connection.

    Returns:
        A list with 0 or 1 signal dict. Empty list if the table is absent,
        empty, or an error occurs (graceful degradation).
    """
    if not HAS_PSYCOPG2:
        return []

    try:
        with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(CRIME_SIGNALS_SQL, (lat, lat, lon, lon, lat))
            row = cur.fetchone()
    except Exception:
        return []

    if not row:
        return []

    # Filter out absurdly distant matches (e.g., Chicago crime matching NYC).
    # 50km is generous — crime data should be from the same metro area.
    if float(row["distance_m"]) > 50000:
        return []

    crime_trend = (row["crime_trend"] or "").upper()
    impact_type = _CRIME_TREND_IMPACT.get(crime_trend, "crime_trend_stable")

    crime_12mo = row["crime_12mo"] or 0
    crime_trend_pct = (
        float(row["crime_trend_pct"]) if row["crime_trend_pct"] is not None else None
    )

    trend_word = crime_trend.capitalize() if crime_trend else "Stable"
    pct_str = f" ({crime_trend_pct:+.0f}%)" if crime_trend_pct is not None else ""
    title = f"Crime trend: {trend_word}{pct_str} · {crime_12mo:,} incidents (12 mo)"

    severity_map = {"INCREASING": "HIGH", "STABLE": "MEDIUM", "DECREASING": "LOW"}

    return [{
        "lat": row["centroid_lat"],
        "lon": row["centroid_lon"],
        "impact_type": impact_type,
        "title": title,
        "address": None,
        "source": "chicago_crime_trends",
        "start_date": None,
        "end_date": None,
        "distance_m": round(float(row["distance_m"])),
        "severity_hint": severity_map.get(crime_trend, "MEDIUM"),
        "weight": 0.0,
    }]


# ---------------------------------------------------------------------------
# Nearby schools  (data-061)
# ---------------------------------------------------------------------------

NEARBY_SCHOOLS_SQL = """
    SELECT
        school_name,
        school_rating,
        latitude,
        longitude,
        6371000.0 * 2.0 * asin(
            sqrt(
                power(sin(radians((latitude - %s) / 2.0)), 2) +
                cos(radians(%s)) * cos(radians(latitude)) *
                power(sin(radians((longitude - %s) / 2.0)), 2)
            )
        ) AS distance_m
    FROM neighborhood_quality
    WHERE
        region_type = 'school'
        AND latitude  IS NOT NULL
        AND longitude IS NOT NULL
        AND latitude  BETWEEN %s AND %s
        AND longitude BETWEEN %s AND %s
        AND 6371000.0 * 2.0 * asin(
            sqrt(
                power(sin(radians((latitude - %s) / 2.0)), 2) +
                cos(radians(%s)) * cos(radians(latitude)) *
                power(sin(radians((longitude - %s) / 2.0)), 2)
            )
        ) <= %s
    ORDER BY distance_m ASC
    LIMIT 20;
"""

_SCHOOL_RADIUS_M = 1000


def get_nearby_schools(
    lat: float,
    lon: float,
    db_conn,
) -> list[dict]:
    """
    Return schools within 1 km of (lat, lon) from neighborhood_quality.

    Non-fatal: returns an empty list if the table is absent, columns are
    missing, or any other error occurs (graceful degradation before
    data-061 ingest runs).

    Args:
        lat: Query latitude (WGS84).
        lon: Query longitude (WGS84).
        db_conn: An open psycopg2 connection.

    Returns:
        List of dicts with lat, lon, name, rating, distance_m.
    """
    if not HAS_PSYCOPG2:
        return []

    lat_delta = _SCHOOL_RADIUS_M / 111_000.0
    lon_delta = _SCHOOL_RADIUS_M / (111_000.0 * math.cos(math.radians(lat)) + 1e-9)

    try:
        with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                NEARBY_SCHOOLS_SQL,
                (
                    # SELECT distance_m expression (lat, lat, lon)
                    lat, lat, lon,
                    # WHERE bounding box
                    lat - lat_delta, lat + lat_delta,
                    lon - lon_delta, lon + lon_delta,
                    # WHERE haversine <= radius_m (lat, lat, lon, radius_m)
                    lat, lat, lon, _SCHOOL_RADIUS_M,
                ),
            )
            rows = cur.fetchall()
    except Exception:
        return []

    return [
        {
            "lat": row["latitude"],
            "lon": row["longitude"],
            "name": row["school_name"],
            "rating": row["school_rating"],
            "distance_m": round(float(row["distance_m"])),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# DB connection helper
# ---------------------------------------------------------------------------

def get_db_connection():
    """
    Create a psycopg2 connection from environment variables.

    Supports two formats:
    1. DATABASE_URL (Railway standard): postgresql://user:pass@host:port/db
    2. Individual variables: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
       POSTGRES_USER, POSTGRES_PASSWORD

    Falls back to individual variables if DATABASE_URL is not set.
    """
    if not HAS_PSYCOPG2:
        raise ImportError("psycopg2 is required. pip install psycopg2-binary")

    # Try DATABASE_URL first (Railway/Heroku standard)
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=5)

    # Fallback to individual environment variables
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "livability"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=5,
    )


# ---------------------------------------------------------------------------
# Entry point (smoke test with real DB)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test the nearby projects radius query."
    )
    parser.add_argument("--lat", type=float, default=41.8960)
    parser.add_argument("--lon", type=float, default=-87.6704)
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS_M)
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Skip DB query and just test the scoring engine with fake data.",
    )
    args = parser.parse_args()

    if args.no_db:
        print("Testing scoring engine with synthetic nearby projects (no DB)...\n")

        from backend.models.project import Project
        from datetime import date, timedelta

        fake_nearby = [
            NearbyProject(
                project=Project(
                    project_id="chicago_closures:TEST-1",
                    source="chicago_closures",
                    source_id="TEST-1",
                    impact_type=IMPACT_MULTI_LANE,
                    title="W Chicago Ave multi-lane closure",
                    notes="2-lane closure, eastbound",
                    start_date=date.today(),
                    end_date=date.today() + timedelta(days=4),
                    status="active",
                    address="1600 W Chicago Ave, Chicago, IL",
                    latitude=41.8960,
                    longitude=-87.6704,
                    severity_hint="HIGH",
                ),
                distance_m=120.0,
            ),
            NearbyProject(
                project=Project(
                    project_id="chicago_permits:TEST-2",
                    source="chicago_permits",
                    source_id="TEST-2",
                    impact_type=IMPACT_CONSTRUCTION,
                    title="New construction at 1550 W Chicago Ave",
                    notes="Multi-story residential",
                    start_date=date.today() - timedelta(days=10),
                    end_date=date.today() + timedelta(days=60),
                    status="active",
                    address="1550 W Chicago Ave, Chicago, IL",
                    latitude=41.8958,
                    longitude=-87.6690,
                    severity_hint="MEDIUM",
                ),
                distance_m=85.0,
            ),
        ]

        result = compute_score(fake_nearby, "1600 W Chicago Ave, Chicago, IL")
        import json
        from dataclasses import asdict
        print(json.dumps(asdict(result), indent=2))
    else:
        print(f"Querying DB for projects near lat={args.lat}, lon={args.lon}, radius={args.radius}m...\n")
        conn = get_db_connection()
        nearby = get_nearby_projects(args.lat, args.lon, conn, args.radius)
        print(f"Found {len(nearby)} nearby projects.\n")
        for np in nearby:
            print(f"  {np.project.project_id} | {np.project.impact_type} | {np.distance_m:.0f}m | {np.project.title}")
