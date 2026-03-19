"""
Seed the projects table with realistic Chicago construction and closure data.
Covers multiple neighborhoods so any address can receive a meaningful score.
Run with:
  DATABASE_URL="postgresql://root@/livability?host=/var/run/postgresql" python scripts/seed_projects.py
"""

import os
import sys
import uuid
from datetime import date, timedelta

import psycopg2

TODAY = date.today()


def d(days_offset: int) -> str:
    return (TODAY + timedelta(days=days_offset)).isoformat()


# ---------------------------------------------------------------------------
# Seed records
# Each tuple: (source, source_id, impact_type, title, notes,
#              start_date, end_date, status, address, lat, lon, severity_hint)
# ---------------------------------------------------------------------------
PROJECTS = [
    # ── West Town / W Chicago Ave corridor ──────────────────────────────────
    (
        "chicago_closures", "cl-wtown-001",
        "closure_multi_lane",
        "2-lane eastbound closure — W Chicago Ave at Ashland",
        "Water main replacement; eastbound lanes restricted between Ashland Ave and Wood St",
        d(-5), d(20), "active",
        "1620 W Chicago Ave, Chicago, IL", 41.8958, -87.6620, "HIGH",
    ),
    (
        "chicago_closures", "cl-wtown-002",
        "closure_single_lane",
        "Curb lane closure — W Chicago Ave near Damen",
        "Gas service installation requires right-turn-lane closure",
        d(-2), d(10), "active",
        "1880 W Chicago Ave, Chicago, IL", 41.8961, -87.6776, "MEDIUM",
    ),
    (
        "chicago_permits", "pm-wtown-003",
        "construction",
        "Mixed-use building construction — 1640 W Chicago Ave",
        "New 6-story mixed-use development; foundation and framing active",
        d(-30), d(180), "active",
        "1640 W Chicago Ave, Chicago, IL", 41.8957, -87.6634, "MEDIUM",
    ),
    (
        "chicago_permits", "pm-wtown-004",
        "demolition",
        "Commercial demolition — 1555 W Chicago Ave",
        "3-story brick commercial structure demolition before new construction",
        d(-3), d(15), "active",
        "1555 W Chicago Ave, Chicago, IL", 41.8953, -87.6567, "HIGH",
    ),
    (
        "chicago_closures", "cl-wtown-005",
        "closure_full",
        "Full sidewalk closure — Grand Ave at Halsted",
        "Scaffold installation for facade repair; pedestrian detour in effect",
        d(-1), d(30), "active",
        "800 W Grand Ave, Chicago, IL", 41.8909, -87.6481, "HIGH",
    ),
    # ── River West / W Grand Ave corridor ────────────────────────────────────
    (
        "chicago_closures", "cl-rwest-001",
        "closure_multi_lane",
        "2-lane northbound closure — N Halsted St at Grand",
        "Elevated train track maintenance work; two northbound lanes closed",
        d(-10), d(14), "active",
        "700 W Grand Ave, Chicago, IL", 41.8910, -87.6466, "HIGH",
    ),
    (
        "chicago_permits", "pm-rwest-002",
        "construction",
        "High-rise residential construction — 611 W Grand Ave",
        "27-story residential tower; crane operations and concrete pours ongoing",
        d(-60), d(365), "active",
        "611 W Grand Ave, Chicago, IL", 41.8909, -87.6432, "MEDIUM",
    ),
    (
        "chicago_closures", "cl-rwest-003",
        "closure_single_lane",
        "Parking lane closure — W Grand Ave between Halsted and Milwaukee",
        "Sewer lateral replacement; excavation in progress",
        d(-4), d(8), "active",
        "680 W Grand Ave, Chicago, IL", 41.8910, -87.6458, "MEDIUM",
    ),
    # ── Loop / W Wacker Dr corridor ──────────────────────────────────────────
    (
        "chicago_closures", "cl-loop-001",
        "closure_multi_lane",
        "Multi-lane closure — S Wacker Dr between Adams and Jackson",
        "Chicago Transit Authority tunnel maintenance; two center lanes closed",
        d(-7), d(21), "active",
        "233 S Wacker Dr, Chicago, IL", 41.8788, -87.6360, "HIGH",
    ),
    (
        "chicago_permits", "pm-loop-002",
        "construction",
        "Office tower renovation — 200 S Wacker Dr",
        "HVAC and facade upgrade on floors 12-30; crane on Wacker Dr",
        d(-45), d(120), "active",
        "200 S Wacker Dr, Chicago, IL", 41.8793, -87.6365, "MEDIUM",
    ),
    (
        "chicago_closures", "cl-loop-003",
        "closure_full",
        "Full sidewalk closure — S Wacker Dr at Monroe",
        "Utility vault repair; all pedestrian traffic diverted to east sidewalk",
        d(-2), d(12), "active",
        "130 S Wacker Dr, Chicago, IL", 41.8800, -87.6368, "HIGH",
    ),
    (
        "chicago_permits", "pm-loop-004",
        "light_permit",
        "Exterior sign installation — 1 S Wacker Dr",
        "New tenant signage on floors 2-4; minimal street impact",
        d(-1), d(3), "active",
        "1 S Wacker Dr, Chicago, IL", 41.8815, -87.6369, "LOW",
    ),
    # ── Lincoln Park / N Clark St ─────────────────────────────────────────────
    (
        "chicago_closures", "cl-lpk-001",
        "closure_multi_lane",
        "2-lane closure — N Clark St at Fullerton",
        "Water main replacement between Fullerton Ave and Belden Ave",
        d(-3), d(25), "active",
        "2400 N Clark St, Chicago, IL", 41.9234, -87.6363, "HIGH",
    ),
    (
        "chicago_permits", "pm-lpk-002",
        "construction",
        "Residential addition — 2250 N Lincoln Ave",
        "Rear addition on existing 3-flat; dumpster and staging in alley",
        d(-10), d(60), "active",
        "2250 N Lincoln Ave, Chicago, IL", 41.9199, -87.6514, "LOW",
    ),
    # ── Wicker Park / Milwaukee Ave ───────────────────────────────────────────
    (
        "chicago_closures", "cl-wpk-001",
        "closure_single_lane",
        "Lane closure — N Milwaukee Ave at Damen",
        "Fiber optic installation; single lane restricted northbound",
        d(-1), d(7), "active",
        "1600 N Milwaukee Ave, Chicago, IL", 41.9091, -87.6776, "MEDIUM",
    ),
    (
        "chicago_permits", "pm-wpk-002",
        "demolition",
        "Building demolition — 1700 W Division St",
        "2-story commercial demolition prior to condo development",
        d(2), d(14), "planned",
        "1700 W Division St, Chicago, IL", 41.9035, -87.6712, "HIGH",
    ),
    # ── Pilsen / W 18th St ────────────────────────────────────────────────────
    (
        "chicago_closures", "cl-pls-001",
        "closure_full",
        "Full closure — W 18th St at Paulina",
        "Bridge inspection and deck repair; detour via 19th St",
        d(-5), d(30), "active",
        "1800 W 18th St, Chicago, IL", 41.8576, -87.6716, "HIGH",
    ),
    (
        "chicago_permits", "pm-pls-002",
        "construction",
        "Mixed-use development — 2000 S Western Ave",
        "4-story mixed-use; active foundation work",
        d(-20), d(210), "active",
        "2000 S Western Ave, Chicago, IL", 41.8549, -87.6841, "MEDIUM",
    ),
    # ── Lakeview / N Broadway ─────────────────────────────────────────────────
    (
        "chicago_closures", "cl-lkv-001",
        "closure_multi_lane",
        "2-lane closure — N Broadway at Belmont",
        "CTA track welding; southbound lanes blocked overnight and weekends",
        d(-2), d(18), "active",
        "3200 N Broadway, Chicago, IL", 41.9396, -87.6441, "HIGH",
    ),
    (
        "chicago_permits", "pm-lkv-002",
        "construction",
        "Condo conversion — 3300 N Clark St",
        "Interior gut rehab and roof replacement; dumpster on Clark St",
        d(-15), d(90), "active",
        "3300 N Clark St, Chicago, IL", 41.9408, -87.6363, "LOW",
    ),
    # ── Hyde Park / S Lake Shore Dr ───────────────────────────────────────────
    (
        "chicago_closures", "cl-hpk-001",
        "closure_single_lane",
        "Right lane closure — S Lake Shore Dr at 55th",
        "Median landscaping work; right lane closed southbound",
        d(-8), d(10), "active",
        "5500 S Lake Shore Dr, Chicago, IL", 41.7955, -87.5868, "MEDIUM",
    ),
    (
        "chicago_permits", "pm-hpk-002",
        "construction",
        "University building addition — 5700 S Ellis Ave",
        "Academic building expansion; staging and crane at Ellis Ave",
        d(-90), d(540), "active",
        "5700 S Ellis Ave, Chicago, IL", 41.7921, -87.5985, "MEDIUM",
    ),
    # ── Fulton Market / W Fulton St ───────────────────────────────────────────
    (
        "chicago_closures", "cl-ftm-001",
        "closure_full",
        "Full closure — N Morgan St between Lake and Randolph",
        "New sewer installation; full closure with detour via N Sangamon St",
        d(-6), d(45), "active",
        "900 W Fulton Market, Chicago, IL", 41.8864, -87.6502, "HIGH",
    ),
    (
        "chicago_permits", "pm-ftm-002",
        "construction",
        "Restaurant/retail buildout — 811 W Fulton Market",
        "Heavy interior demolition and new MEP rough-in; dumpsters on street",
        d(-12), d(60), "active",
        "811 W Fulton Market, Chicago, IL", 41.8863, -87.6494, "LOW",
    ),
    (
        "chicago_closures", "cl-ftm-003",
        "closure_multi_lane",
        "2-lane closure — W Randolph St at Halsted",
        "Gas main replacement; right two lanes restricted",
        d(-3), d(20), "active",
        "820 W Randolph St, Chicago, IL", 41.8840, -87.6494, "HIGH",
    ),
    # ── Near North / Rush St area ─────────────────────────────────────────────
    (
        "chicago_closures", "cl-nn-001",
        "closure_multi_lane",
        "2-lane closure — N Michigan Ave at Chicago Ave",
        "Streetscape improvement project; bus and right lane closed",
        d(-14), d(60), "active",
        "750 N Michigan Ave, Chicago, IL", 41.8962, -87.6243, "HIGH",
    ),
    (
        "chicago_permits", "pm-nn-002",
        "construction",
        "Hotel renovation — 160 E Huron St",
        "Full facade and lobby renovation; sidewalk scaffold in place",
        d(-30), d(180), "active",
        "160 E Huron St, Chicago, IL", 41.8949, -87.6225, "MEDIUM",
    ),
]


def seed(db_url: str) -> None:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    inserted = 0
    skipped = 0

    for row in PROJECTS:
        (
            source, source_id, impact_type, title, notes,
            start_date, end_date, status, address, lat, lon, severity_hint,
        ) = row

        project_id = f"{source}:{source_id}"

        cur.execute(
            """
            INSERT INTO projects
                (project_id, source, source_id, impact_type, title, notes,
                 start_date, end_date, status, address, latitude, longitude,
                 geom, severity_hint, normalized_at, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s, %s,
                 ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, NOW(), NOW())
            ON CONFLICT (source, source_id) DO UPDATE SET
                title         = EXCLUDED.title,
                notes         = EXCLUDED.notes,
                start_date    = EXCLUDED.start_date,
                end_date      = EXCLUDED.end_date,
                status        = EXCLUDED.status,
                impact_type   = EXCLUDED.impact_type,
                severity_hint = EXCLUDED.severity_hint,
                geom          = EXCLUDED.geom,
                updated_at    = NOW()
            """,
            (
                project_id, source, source_id, impact_type, title, notes,
                start_date, end_date, status, address, lat, lon,
                lon, lat,   # ST_MakePoint(lon, lat)
                severity_hint,
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Seed complete: {inserted} inserted/updated, {skipped} unchanged")

    # Verify
    conn2 = psycopg2.connect(db_url)
    cur2 = conn2.cursor()
    cur2.execute("SELECT count(*), count(DISTINCT source) FROM projects")
    count, sources = cur2.fetchone()
    print(f"  projects table now has {count} rows across {sources} source(s)")
    cur2.close()
    conn2.close()


if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    seed(db_url)
