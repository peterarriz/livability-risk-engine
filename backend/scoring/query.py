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
from dataclasses import dataclass
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
    IMPACT_SINGLE_LANE,
    Project,
)


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
    """
    address: str
    disruption_score: int       # 0–100
    confidence: str             # HIGH | MEDIUM | LOW
    severity: dict              # {noise: ..., traffic: ..., dust: ...}
    top_risks: list[str]        # up to 3 plain-English strings
    explanation: str            # 1 short paragraph


# ---------------------------------------------------------------------------
# DB query
# ---------------------------------------------------------------------------

# Active statuses to include in scoring queries.
SCOREABLE_STATUSES = ("active", "planned", "unknown")

# Default search radius in meters.
DEFAULT_RADIUS_M = 500

# SQL query uses ST_DWithin for index-efficient radius filtering.
# ST_Distance returns meters when using geography cast.
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
        ST_Distance(
            geom::geography,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
        ) AS distance_m
    FROM projects
    WHERE
        status = ANY(%s)
        AND geom IS NOT NULL
        AND ST_DWithin(
            geom::geography,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
            %s
        )
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

    with db_conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            NEARBY_PROJECTS_SQL,
            (lon, lat, list(SCOREABLE_STATUSES), lon, lat, radius_m),
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
            IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE
        )
    )
    noise_pts = sum(
        w for np, w in contributions
        if np.project.impact_type in (IMPACT_DEMOLITION, IMPACT_CONSTRUCTION)
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
        dist_str = f"within roughly {int(nearby.distance_m)} meters"

        # Build the risk string from what we know.
        if p.impact_type == IMPACT_FULL_CLOSURE:
            risk = f"Full street closure on {p.title} {dist_str}"
        elif p.impact_type == IMPACT_MULTI_LANE:
            risk = f"Multi-lane closure on {p.title} {dist_str}"
        elif p.impact_type == IMPACT_SINGLE_LANE:
            risk = f"Lane or curb closure near {p.title} {dist_str}"
        elif p.impact_type == IMPACT_DEMOLITION:
            risk = f"Active demolition or excavation near {p.title} {dist_str}"
        elif p.impact_type == IMPACT_CONSTRUCTION:
            risk = f"Active construction permit near {p.title} {dist_str}"
        else:
            risk = f"Nearby permit activity: {p.title} {dist_str}"

        # Append active window if available.
        if p.end_date:
            risk += f"; active through {p.end_date.isoformat()}"

        risks.append(risk)

    return risks


def _build_explanation(
    contributions: list[tuple[NearbyProject, float]],
    severity: dict,
) -> str:
    """
    Build the deterministic explanation paragraph.
    Per explanation generation rules in docs/03_scoring_model.md.
    """
    if not contributions:
        return (
            "No significant construction or closure activity was found "
            "near this address within the near-term window."
        )

    top_np, top_w = contributions[0]
    p = top_np.project
    dist_str = f"within roughly {int(top_np.distance_m)} meters"

    # Select explanation pattern based on dominant impact type.
    if p.impact_type in (IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE):
        lead = f"A nearby lane or street closure ({p.title}, {dist_str}) is the main driver"
        category = "traffic disruption"
    elif p.impact_type == IMPACT_DEMOLITION:
        lead = f"Nearby demolition or excavation ({p.title}, {dist_str}) is the main driver"
        category = "noise and dust disruption"
    elif p.impact_type == IMPACT_CONSTRUCTION:
        lead = f"Nearby construction activity ({p.title}, {dist_str}) is the main driver"
        category = "noise disruption"
    else:
        lead = f"Nearby permitted work ({p.title}, {dist_str}) is contributing"
        category = "minor disruption"

    # Add timing detail if available.
    timing = ""
    if p.end_date:
        timing = f" The active window runs through {p.end_date.isoformat()}."

    # Mention secondary driver only if it is meaningfully different in category.
    secondary = ""
    if len(contributions) > 1:
        sec_np, sec_w = contributions[1]
        sec_cat = "traffic" if sec_np.project.impact_type in (
            IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE
        ) else "construction"
        top_cat = "traffic" if p.impact_type in (
            IMPACT_FULL_CLOSURE, IMPACT_MULTI_LANE, IMPACT_SINGLE_LANE
        ) else "construction"
        if sec_cat != top_cat and sec_w >= top_w * 0.50:
            secondary = f" A secondary {sec_cat} signal nearby adds further context."

    return f"{lead}, so this address has elevated short-term {category}.{timing}{secondary}"


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
                "No significant construction or closure activity was found "
                "near this address within the near-term window."
            ),
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
    explanation = _build_explanation(top3, severity)

    return ScoreResult(
        address=address,
        disruption_score=disruption_score,
        confidence=confidence,
        severity=severity,
        top_risks=top_risks,
        explanation=explanation,
    )


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
        return psycopg2.connect(database_url)

    # Fallback to individual environment variables
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "livability"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
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
