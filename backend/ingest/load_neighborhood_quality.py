"""
backend/ingest/load_neighborhood_quality.py
task: data-040, data-044
lane: data

Loads neighborhood quality staging files into the neighborhood_quality DB table.

Reads from staging files written by:
  backend/ingest/fema_flood_zones.py      → data/raw/fema_flood_zones.json
  backend/ingest/chicago_crime_trends.py  → data/raw/chicago_crime_trends.json
  backend/ingest/austin_crime_trends.py   → data/raw/austin_crime_trends.json
  backend/ingest/seattle_crime_trends.py  → data/raw/seattle_crime_trends.json
  backend/ingest/nyc_crime_trends.py      → data/raw/nyc_crime_trends.json
  backend/ingest/census_acs.py            → data/raw/census_acs.json

Each record is upserted into neighborhood_quality keyed on (region_type, region_id).

Usage:
  python backend/ingest/load_neighborhood_quality.py
  python backend/ingest/load_neighborhood_quality.py --dry-run
  python backend/ingest/load_neighborhood_quality.py --source fema
  python backend/ingest/load_neighborhood_quality.py --source crime
  python backend/ingest/load_neighborhood_quality.py --source crime_austin
  python backend/ingest/load_neighborhood_quality.py --source crime_seattle
  python backend/ingest/load_neighborhood_quality.py --source crime_nyc
  python backend/ingest/load_neighborhood_quality.py --source census

Prerequisites:
  - DATABASE_URL or POSTGRES_* env vars must be set
  - db/schema.sql must be applied (neighborhood_quality table must exist)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STAGING_FILES = {
    "fema":          Path("data/raw/fema_flood_zones.json"),
    "crime":         Path("data/raw/chicago_crime_trends.json"),
    "census":        Path("data/raw/census_acs.json"),
    # data-044: US city crime trends
    "crime_austin":  Path("data/raw/austin_crime_trends.json"),
    "crime_seattle": Path("data/raw/seattle_crime_trends.json"),
    "crime_nyc":     Path("data/raw/nyc_crime_trends.json"),
}

CURRENT_YEAR = _dt.datetime.now().year

UPSERT_SQL = """
    INSERT INTO neighborhood_quality (
        region_type, region_id,
        fema_flood_zone, flood_risk,
        crime_12mo, crime_prior_12mo, crime_trend, crime_trend_pct,
        median_income, population, vacancy_rate, housing_age_med,
        geom, data_year
    )
    VALUES (
        %s, %s,
        %s, %s,
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        ST_GeomFromText(%s, 4326),
        %s
    )
    ON CONFLICT (region_type, region_id) DO UPDATE SET
        fema_flood_zone  = EXCLUDED.fema_flood_zone,
        flood_risk       = EXCLUDED.flood_risk,
        crime_12mo       = EXCLUDED.crime_12mo,
        crime_prior_12mo = EXCLUDED.crime_prior_12mo,
        crime_trend      = EXCLUDED.crime_trend,
        crime_trend_pct  = EXCLUDED.crime_trend_pct,
        median_income    = EXCLUDED.median_income,
        population       = EXCLUDED.population,
        vacancy_rate     = EXCLUDED.vacancy_rate,
        housing_age_med  = EXCLUDED.housing_age_med,
        geom             = EXCLUDED.geom,
        data_year        = EXCLUDED.data_year,
        updated_at       = now();
"""


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def get_db_connection():
    if not HAS_PSYCOPG2:
        raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=10)
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ.get("POSTGRES_DB", "livability"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        connect_timeout=10,
    )


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def _geom_wkt(record: dict) -> str | None:
    """Build a WKT POINT string from lat/lon, or return None if coordinates absent."""
    lat = record.get("latitude")
    lon = record.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return f"POINT({float(lon)} {float(lat)})"
    except (TypeError, ValueError):
        return None


def _record_to_params(record: dict) -> tuple:
    """Convert a staging record to the SQL parameter tuple for UPSERT_SQL (14 params)."""
    return (
        record.get("region_type"),
        record.get("region_id"),
        # FEMA flood fields
        record.get("fema_flood_zone"),
        record.get("flood_risk"),
        # Crime trend fields
        record.get("crime_12mo"),
        record.get("crime_prior_12mo"),
        record.get("crime_trend"),
        record.get("crime_trend_pct"),
        # Census ACS fields
        record.get("median_income"),
        record.get("population"),
        record.get("vacancy_rate"),
        record.get("housing_age_med"),
        # geom as WKT (NULL-safe: ST_GeomFromText(NULL, 4326) → NULL)
        _geom_wkt(record),
        # data_year
        CURRENT_YEAR,
    )


# ---------------------------------------------------------------------------
# Load logic
# ---------------------------------------------------------------------------

def load_source(
    source_key: str,
    staging_path: Path,
    conn,
    dry_run: bool,
) -> int:
    """
    Load records from one staging file into the neighborhood_quality table.
    Returns the count of records processed.
    """
    if not staging_path.exists():
        print(f"  SKIP: {staging_path} not found — run the ingest script first.")
        return 0

    with staging_path.open("r", encoding="utf-8") as f:
        staging = json.load(f)

    records = staging.get("records", [])
    if not records:
        print(f"  SKIP: {staging_path} contains no records.")
        return 0

    print(f"\nLoading {source_key} from {staging_path}: {len(records)} records...")

    if dry_run:
        print(f"  Dry-run: would upsert {len(records)} records into neighborhood_quality.")
        if records:
            sample = {k: v for k, v in records[0].items() if k != "zone_subty"}
            print(f"  Sample params: {json.dumps(sample)[:300]}")
        return len(records)

    batch_size = 500
    upserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            params_list = [_record_to_params(r) for r in batch]
            psycopg2.extras.execute_batch(cur, UPSERT_SQL, params_list)
            upserted += len(batch)
            print(f"  Upserted {upserted}/{len(records)} records...")

    conn.commit()
    print(f"  Done. Upserted {upserted} neighborhood_quality records from {source_key}.")
    return upserted


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load neighborhood quality staging files into the database."
    )
    parser.add_argument(
        "--source",
        choices=["fema", "crime", "census", "crime_austin", "crime_seattle", "crime_nyc", "all"],
        default="all",
        help="Which staging source to load (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be loaded without writing to the database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not HAS_PSYCOPG2:
        print(
            "ERROR: psycopg2 is required. Install with: pip install psycopg2-binary",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.dry_run:
        db_url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_HOST")
        if not db_url:
            print(
                "ERROR: DATABASE_URL or POSTGRES_HOST env var must be set.",
                file=sys.stderr,
            )
            sys.exit(1)

    sources = (
        list(STAGING_FILES.keys())
        if args.source == "all"
        else [args.source]
    )

    conn = None
    if not args.dry_run:
        try:
            conn = get_db_connection()
        except Exception as exc:
            print(f"ERROR: Could not connect to database: {exc}", file=sys.stderr)
            sys.exit(1)

    total = 0
    try:
        for source_key in sources:
            staging_path = STAGING_FILES[source_key]
            count = load_source(source_key, staging_path, conn, args.dry_run)
            total += count
    finally:
        if conn:
            conn.close()

    print(f"\nTotal neighborhood_quality records processed: {total}")
    print("Done.")


if __name__ == "__main__":
    main()
