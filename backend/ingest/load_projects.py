"""
backend/ingest/load_projects.py
task: data-013
lane: data

DB loader — reads raw staging JSON files and upserts normalized
Project records into the canonical `projects` table.

This is the bridge between the ingest scripts (data-002, data-004, data-014)
and the scoring engine (data-009). Once this runs successfully,
the /score endpoint returns real data.

End-to-end pipeline:
  1. python backend/ingest/building_permits.py    → data/raw/building_permits.json
  2. python backend/ingest/street_closures.py     → data/raw/street_closures.json
  3. python backend/ingest/idot_road_projects.py  → data/raw/idot_road_projects.json
  4. python backend/ingest/geocode_fill.py        → fills missing lat/lon in staging files
  5. python backend/ingest/load_projects.py       → upserts into `projects` table
  6. uvicorn app.main:app --reload                → live /score endpoint

Usage:
  # Load both sources
  python backend/ingest/load_projects.py

  # Load both sources and prune completed records older than 90 days
  python backend/ingest/load_projects.py --prune-days 90

  # Load only one source
  python backend/ingest/load_projects.py --source permits
  python backend/ingest/load_projects.py --source closures

  # Dry-run (normalize, validate, and show prune count; no DB writes)
  python backend/ingest/load_projects.py --dry-run --prune-days 90

  # Custom staging file paths
  python backend/ingest/load_projects.py \\
      --permits-file data/raw/building_permits.json \\
      --closures-file data/raw/street_closures.json

Environment variables (required for DB writes):
  POSTGRES_HOST      (default: localhost)
  POSTGRES_PORT      (default: 5432)
  POSTGRES_DB        (default: livability)
  POSTGRES_USER      (default: postgres)
  POSTGRES_PASSWORD  (required)

Acceptance criteria (data-013):
  - Reads normalized Project records from both staging files.
  - Upserts into the canonical `projects` table idempotently
    (re-running does not create duplicates).
  - Populates the geom column from latitude/longitude so the
    ST_DWithin radius query in data-009 works correctly.
  - Logs row counts and any skipped records clearly.
  - Dry-run mode validates normalization without touching the DB.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from backend.models.project import (
    Project,
    normalize_closure,
    normalize_cook_county_permit,
    normalize_idot_project,
    normalize_permit,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PERMITS_FILE       = Path("data/raw/building_permits.json")
DEFAULT_CLOSURES_FILE      = Path("data/raw/street_closures.json")
DEFAULT_IDOT_FILE          = Path("data/raw/idot_road_projects.json")
DEFAULT_COOK_COUNTY_FILE   = Path("data/raw/cook_county_permits.json")

# Statuses we consider worth loading into the scoring table.
# Completed records are skipped to keep the projects table focused
# on the near-term window the scoring engine cares about.
LOAD_STATUSES = {"active", "planned", "unknown"}


# ---------------------------------------------------------------------------
# Load stats
# ---------------------------------------------------------------------------

@dataclass
class LoadStats:
    source: str
    total_raw: int = 0
    normalized: int = 0
    upserted: int = 0
    skipped_status: int = 0
    skipped_no_coords: int = 0
    skipped_no_source_id: int = 0
    errors: int = 0
    pruned: int = 0

    def report(self) -> str:
        lines = [
            f"\n── {self.source} ──────────────────────────",
            f"  Raw records read:       {self.total_raw}",
            f"  Normalized:             {self.normalized}",
            f"  Upserted to DB:         {self.upserted}",
            f"  Skipped (status):       {self.skipped_status}",
            f"  Skipped (no coords):    {self.skipped_no_coords}",
            f"  Skipped (no source_id): {self.skipped_no_source_id}",
            f"  Errors:                 {self.errors}",
            f"  Pruned (stale):         {self.pruned}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO projects (
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
    geom,
    severity_hint,
    normalized_at,
    updated_at
)
VALUES (
    %(project_id)s,
    %(source)s,
    %(source_id)s,
    %(impact_type)s,
    %(title)s,
    %(notes)s,
    %(start_date)s,
    %(end_date)s,
    %(status)s,
    %(address)s,
    %(latitude)s,
    %(longitude)s,
    ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326),
    %(severity_hint)s,
    NOW(),
    NOW()
)
ON CONFLICT (source, source_id) DO UPDATE SET
    impact_type    = EXCLUDED.impact_type,
    title          = EXCLUDED.title,
    notes          = EXCLUDED.notes,
    start_date     = EXCLUDED.start_date,
    end_date       = EXCLUDED.end_date,
    status         = EXCLUDED.status,
    address        = EXCLUDED.address,
    latitude       = EXCLUDED.latitude,
    longitude      = EXCLUDED.longitude,
    geom           = EXCLUDED.geom,
    severity_hint  = EXCLUDED.severity_hint,
    updated_at     = NOW();
"""

LOG_INGEST_RUN_START = """
INSERT INTO ingest_runs (source, started_at, status)
VALUES (%(source)s, NOW(), 'running')
RETURNING id;
"""

LOG_INGEST_RUN_FINISH = """
UPDATE ingest_runs
SET finished_at = NOW(), record_count = %(record_count)s, status = %(status)s, error_msg = %(error_msg)s
WHERE id = %(run_id)s;
"""

# Prune completed records whose end_date is older than N days.
# Only removes `completed` status rows — never touches active or planned records.
PRUNE_SQL = """
DELETE FROM projects
WHERE status = 'completed'
  AND end_date < CURRENT_DATE - %(prune_days)s * INTERVAL '1 day';
"""

PRUNE_COUNT_SQL = """
SELECT COUNT(*) FROM projects
WHERE status = 'completed'
  AND end_date < CURRENT_DATE - %(prune_days)s * INTERVAL '1 day';
"""


# ---------------------------------------------------------------------------
# Stale-record pruning
# ---------------------------------------------------------------------------

def prune_stale_projects(conn, prune_days: int, dry_run: bool) -> int:
    """
    Remove completed projects whose end_date is older than prune_days.

    In dry-run mode, counts and reports the rows that would be removed
    without deleting anything.

    Returns the number of rows deleted (or that would be deleted).
    """
    params = {"prune_days": prune_days}

    with conn.cursor() as cur:
        cur.execute(PRUNE_COUNT_SQL, params)
        count = cur.fetchone()[0]

    if dry_run:
        print(f"  Dry-run: {count} completed record(s) older than {prune_days} days would be pruned.")
        return count

    if count == 0:
        print(f"  No completed records older than {prune_days} days to prune.")
        return 0

    with conn.cursor() as cur:
        cur.execute(PRUNE_SQL, params)
    conn.commit()

    print(f"  Pruned {count} completed record(s) older than {prune_days} days.")
    return count


# ---------------------------------------------------------------------------
# Staging file reader
# ---------------------------------------------------------------------------

def read_staging_file(path: Path) -> list[dict]:
    """Read raw records from a staging JSON file produced by the ingest scripts."""
    if not path.exists():
        print(f"  Staging file not found: {path}", file=sys.stderr)
        return []

    with path.open(encoding="utf-8") as f:
        staging = json.load(f)

    records = staging.get("records", [])
    ingested_at = staging.get("ingested_at", "unknown")
    print(f"  Read {len(records)} records from {path} (ingested {ingested_at})")
    return records


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _project_to_db_params(project: Project) -> dict:
    """Convert a Project dataclass to a psycopg2 parameter dict."""
    return {
        "project_id":    project.project_id,
        "source":        project.source,
        "source_id":     project.source_id,
        "impact_type":   project.impact_type,
        "title":         project.title,
        "notes":         project.notes,
        "start_date":    project.start_date,
        "end_date":      project.end_date,
        "status":        project.status,
        "address":       project.address,
        "latitude":      project.latitude,
        "longitude":     project.longitude,
        "severity_hint": project.severity_hint,
    }


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def normalize_records(
    raw_records: list[dict],
    normalizer,           # normalize_permit or normalize_closure
    stats: LoadStats,
) -> list[Project]:
    """
    Normalize a list of raw records into Project objects.
    Filters out completed, no-coord, and no-source-id records.
    Updates stats in place.
    """
    stats.total_raw = len(raw_records)
    projects: list[Project] = []

    for record in raw_records:
        try:
            project = normalizer(record)
            stats.normalized += 1
        except Exception as exc:
            stats.errors += 1
            print(f"  WARN: normalization error — {exc}", file=sys.stderr)
            continue

        # Skip completed records — not relevant for near-term scoring.
        if project.status not in LOAD_STATUSES:
            stats.skipped_status += 1
            continue

        # Skip records without coordinates — can't do radius queries.
        if project.latitude is None or project.longitude is None:
            stats.skipped_no_coords += 1
            continue

        # Skip records without a stable source_id.
        if not project.source_id:
            stats.skipped_no_source_id += 1
            continue

        projects.append(project)

    return projects


def upsert_projects(
    projects: list[Project],
    conn,
    stats: LoadStats,
    run_id: Optional[int] = None,
    batch_size: int = 500,
) -> None:
    """
    Upsert Project records into the canonical `projects` table in batches.
    Uses ON CONFLICT (source, source_id) DO UPDATE for idempotency.
    """
    with conn.cursor() as cur:
        for i in range(0, len(projects), batch_size):
            batch = projects[i : i + batch_size]
            params_list = [_project_to_db_params(p) for p in batch]

            try:
                psycopg2.extras.execute_batch(cur, UPSERT_SQL, params_list)
                stats.upserted += len(batch)
                print(f"  Upserted batch {i // batch_size + 1}: {len(batch)} records")
            except Exception as exc:
                conn.rollback()
                stats.errors += len(batch)
                print(f"  ERROR: batch upsert failed — {exc}", file=sys.stderr)
                raise

    conn.commit()


# ---------------------------------------------------------------------------
# Ingest run logging
# ---------------------------------------------------------------------------

def log_run_start(conn, source: str) -> Optional[int]:
    """Insert an ingest_runs row and return its id."""
    try:
        with conn.cursor() as cur:
            cur.execute(LOG_INGEST_RUN_START, {"source": source})
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id
    except Exception:
        return None


def log_run_finish(conn, run_id: int, stats: LoadStats, status: str, error_msg: str = None) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(LOG_INGEST_RUN_FINISH, {
                "run_id":       run_id,
                "record_count": stats.upserted,
                "status":       status,
                "error_msg":    error_msg,
            })
        conn.commit()
    except Exception:
        pass  # Don't fail the whole load over a logging error.


# ---------------------------------------------------------------------------
# Per-source load functions
# ---------------------------------------------------------------------------

def load_permits(
    permits_file: Path,
    conn=None,
    dry_run: bool = False,
) -> LoadStats:
    """Load building permits from staging file into projects table."""
    print("\nLoading building permits...")
    stats = LoadStats(source="chicago_building_permits")

    raw = read_staging_file(permits_file)
    if not raw:
        return stats

    projects = normalize_records(raw, normalize_permit, stats)
    print(f"  Normalized to {len(projects)} scoreable projects")

    if dry_run:
        print("  Dry-run: skipping DB write.")
        if projects:
            sample = _project_to_db_params(projects[0])
            print(f"  Sample project: {json.dumps({k: str(v) for k, v in sample.items()}, indent=4)}")
        return stats

    run_id = log_run_start(conn, "chicago_building_permits")
    try:
        upsert_projects(projects, conn, stats)
        log_run_finish(conn, run_id, stats, "done")
    except Exception as exc:
        log_run_finish(conn, run_id, stats, "failed", str(exc))
        raise

    return stats


def load_closures(
    closures_file: Path,
    conn=None,
    dry_run: bool = False,
) -> LoadStats:
    """Load street closures from staging file into projects table."""
    print("\nLoading street closures...")
    stats = LoadStats(source="chicago_street_closures")

    raw = read_staging_file(closures_file)
    if not raw:
        return stats

    projects = normalize_records(raw, normalize_closure, stats)
    print(f"  Normalized to {len(projects)} scoreable projects")

    if dry_run:
        print("  Dry-run: skipping DB write.")
        if projects:
            sample = _project_to_db_params(projects[0])
            print(f"  Sample project: {json.dumps({k: str(v) for k, v in sample.items()}, indent=4)}")
        return stats

    run_id = log_run_start(conn, "chicago_street_closures")
    try:
        upsert_projects(projects, conn, stats)
        log_run_finish(conn, run_id, stats, "done")
    except Exception as exc:
        log_run_finish(conn, run_id, stats, "failed", str(exc))
        raise

    return stats


def load_idot_projects(
    idot_file: Path,
    conn=None,
    dry_run: bool = False,
) -> LoadStats:
    """Load IDOT road construction projects from staging file into projects table."""
    print("\nLoading IDOT road projects...")
    stats = LoadStats(source="idot_road_projects")

    raw = read_staging_file(idot_file)
    if not raw:
        return stats

    projects = normalize_records(raw, normalize_idot_project, stats)
    print(f"  Normalized to {len(projects)} scoreable projects")

    if dry_run:
        print("  Dry-run: skipping DB write.")
        if projects:
            sample = _project_to_db_params(projects[0])
            print(f"  Sample project: {json.dumps({k: str(v) for k, v in sample.items()}, indent=4)}")
        return stats

    run_id = log_run_start(conn, "idot_road_projects")
    try:
        upsert_projects(projects, conn, stats)
        log_run_finish(conn, run_id, stats, "done")
    except Exception as exc:
        log_run_finish(conn, run_id, stats, "failed", str(exc))
        raise

    return stats


def load_cook_county_permits(
    cook_county_file: Path,
    conn=None,
    dry_run: bool = False,
) -> LoadStats:
    """Load Cook County building permits from staging file into projects table."""
    print("\nLoading Cook County permits...")
    stats = LoadStats(source="cook_county_permits")

    raw = read_staging_file(cook_county_file)
    if not raw:
        return stats

    projects = normalize_records(raw, normalize_cook_county_permit, stats)
    print(f"  Normalized to {len(projects)} scoreable projects")

    if dry_run:
        print("  Dry-run: skipping DB write.")
        if projects:
            sample = _project_to_db_params(projects[0])
            print(f"  Sample project: {json.dumps({k: str(v) for k, v in sample.items()}, indent=4)}")
        return stats

    run_id = log_run_start(conn, "cook_county_permits")
    try:
        upsert_projects(projects, conn, stats)
        log_run_finish(conn, run_id, stats, "done")
    except Exception as exc:
        log_run_finish(conn, run_id, stats, "failed", str(exc))
        raise

    return stats


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def get_db_connection():
    if not HAS_PSYCOPG2:
        raise ImportError(
            "psycopg2 is required. Install with: pip install psycopg2-binary"
        )
    
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
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load normalized projects from staging JSON into the canonical DB table."
    )
    parser.add_argument(
        "--source",
        choices=["permits", "closures", "idot", "cook_county", "all"],
        default="all",
        help="Which source to load (default: all).",
    )
    parser.add_argument(
        "--permits-file",
        type=Path,
        default=DEFAULT_PERMITS_FILE,
        help=f"Path to building permits staging file (default: {DEFAULT_PERMITS_FILE}).",
    )
    parser.add_argument(
        "--closures-file",
        type=Path,
        default=DEFAULT_CLOSURES_FILE,
        help=f"Path to street closures staging file (default: {DEFAULT_CLOSURES_FILE}).",
    )
    parser.add_argument(
        "--idot-file",
        type=Path,
        default=DEFAULT_IDOT_FILE,
        help=f"Path to IDOT road projects staging file (default: {DEFAULT_IDOT_FILE}).",
    )
    parser.add_argument(
        "--cook-county-file",
        type=Path,
        default=DEFAULT_COOK_COUNTY_FILE,
        help=f"Path to Cook County permits staging file (default: {DEFAULT_COOK_COUNTY_FILE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Normalize and validate only; do not write to DB.",
    )
    parser.add_argument(
        "--prune-days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "After upserting, delete completed projects whose end_date is "
            "older than N days. Dry-run mode reports the count without deleting. "
            "Recommended: 90."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        print("── DRY-RUN MODE: no DB writes ──────────────────────")
        conn = None
    else:
        print("Connecting to database...")
        try:
            conn = get_db_connection()
            print("  Connected.")
        except Exception as exc:
            print(f"  ERROR: could not connect to DB — {exc}", file=sys.stderr)
            print(
                "\nTip: set POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, "
                "POSTGRES_PASSWORD env vars, or use --dry-run to test normalization.",
                file=sys.stderr,
            )
            sys.exit(1)

    all_stats: list[LoadStats] = []
    total_pruned = 0

    try:
        if args.source in ("permits", "all"):
            stats = load_permits(args.permits_file, conn, args.dry_run)
            all_stats.append(stats)

        if args.source in ("closures", "all"):
            stats = load_closures(args.closures_file, conn, args.dry_run)
            all_stats.append(stats)

        if args.source in ("idot", "all"):
            stats = load_idot_projects(args.idot_file, conn, args.dry_run)
            all_stats.append(stats)

        if args.source in ("cook_county", "all"):
            stats = load_cook_county_permits(args.cook_county_file, conn, args.dry_run)
            all_stats.append(stats)

        if args.prune_days is not None and conn is not None:
            print(f"\nPruning completed records older than {args.prune_days} days...")
            total_pruned = prune_stale_projects(conn, args.prune_days, args.dry_run)
        elif args.prune_days is not None and args.dry_run:
            print(f"\nPruning completed records older than {args.prune_days} days...")
            # For dry-run we still need a connection to count rows.
            try:
                _conn = get_db_connection()
                total_pruned = prune_stale_projects(_conn, args.prune_days, dry_run=True)
                _conn.close()
            except Exception:
                print("  (Cannot count prune candidates without a DB connection in dry-run mode.)")
    finally:
        if conn:
            conn.close()

    # Summary
    print("\n══ LOAD SUMMARY ════════════════════════════════════")
    for s in all_stats:
        print(s.report())

    total_upserted = sum(s.upserted for s in all_stats)
    total_errors   = sum(s.errors   for s in all_stats)
    print(f"\nTotal upserted: {total_upserted}")
    print(f"Total pruned:   {total_pruned}")
    print(f"Total errors:   {total_errors}")

    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
