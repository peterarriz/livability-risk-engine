"""
Ingest Chicago building permits from the City of Chicago Data Portal (Socrata).

Dataset: Building Permits
Socrata endpoint: https://data.cityofchicago.org/resource/ydr8-5enu.json

Usage
-----
# Full pull (first run or weekly re-sync):
    python backend/ingest/building_permits.py

# Incremental pull (daily delta, last N days):
    python backend/ingest/building_permits.py --days 2

Environment variables
---------------------
DATABASE_URL  PostgreSQL connection string (psycopg2 format).
              Defaults to postgresql://localhost/livability if not set.
SOCRATA_APP_TOKEN  Optional Socrata app token to raise rate limits.
"""

import argparse
import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SOCRATA_BASE = "https://data.cityofchicago.org/resource/ydr8-5enu.json"
PAGE_SIZE = 1000
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/livability")
APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")


def fetch_pages(since_date: str | None = None) -> list[dict]:
    """Fetch all permit records from the Socrata API, optionally filtered by updated_date."""
    headers = {}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN

    where_clause = ""
    if since_date:
        where_clause = f"updated_date > '{since_date}'"

    records: list[dict] = []
    offset = 0
    while True:
        params: dict = {
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "updated_date ASC",
        }
        if where_clause:
            params["$where"] = where_clause

        resp = requests.get(SOCRATA_BASE, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        page = resp.json()
        if not page:
            break
        records.extend(page)
        logger.info("Fetched %d records (offset=%d)", len(records), offset)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return records


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _date_or_none(value: str | None) -> str | None:
    if not value:
        return None
    # Socrata returns ISO 8601 timestamps; keep only the date portion for DATE columns.
    return value[:10]


def upsert_records(conn, records: list[dict]) -> int:
    """Upsert permit records into raw_building_permits. Returns the count inserted/updated."""
    sql = """
        INSERT INTO raw_building_permits (
            source_id, permit_type, work_description, status,
            address, zip_code, community_area, ward,
            latitude, longitude, location_geom,
            issue_date, expiration_date, reported_cost,
            source_updated_at, ingested_at
        ) VALUES (
            %(source_id)s, %(permit_type)s, %(work_description)s, %(status)s,
            %(address)s, %(zip_code)s, %(community_area)s, %(ward)s,
            %(latitude)s, %(longitude)s,
            CASE
                WHEN %(latitude)s IS NOT NULL AND %(longitude)s IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)
                ELSE NULL
            END,
            %(issue_date)s, %(expiration_date)s, %(reported_cost)s,
            %(source_updated_at)s, NOW()
        )
        ON CONFLICT (source_id) DO UPDATE SET
            permit_type        = EXCLUDED.permit_type,
            work_description   = EXCLUDED.work_description,
            status             = EXCLUDED.status,
            address            = EXCLUDED.address,
            zip_code           = EXCLUDED.zip_code,
            community_area     = EXCLUDED.community_area,
            ward               = EXCLUDED.ward,
            latitude           = EXCLUDED.latitude,
            longitude          = EXCLUDED.longitude,
            location_geom      = EXCLUDED.location_geom,
            issue_date         = EXCLUDED.issue_date,
            expiration_date    = EXCLUDED.expiration_date,
            reported_cost      = EXCLUDED.reported_cost,
            source_updated_at  = EXCLUDED.source_updated_at,
            ingested_at        = EXCLUDED.ingested_at
        WHERE raw_building_permits.source_updated_at IS DISTINCT FROM EXCLUDED.source_updated_at
           OR raw_building_permits.source_updated_at IS NULL
    """

    rows = []
    for r in records:
        lat = _float_or_none(r.get("latitude") or (r.get("location") or {}).get("latitude"))
        lng = _float_or_none(r.get("longitude") or (r.get("location") or {}).get("longitude"))
        try:
            ward = int(r["ward"]) if r.get("ward") else None
        except (ValueError, TypeError):
            ward = None
        try:
            cost = float(r["reported_cost"]) if r.get("reported_cost") else None
        except (ValueError, TypeError):
            cost = None

        rows.append(
            {
                "source_id": r.get("id") or r.get("permit_"),
                "permit_type": r.get("permit_type"),
                "work_description": r.get("work_description"),
                "status": r.get("current_status"),
                "address": r.get("street_number", "").strip()
                + " "
                + r.get("street_direction", "").strip()
                + " "
                + r.get("street_name", "").strip()
                + " "
                + r.get("suffix", "").strip(),
                "zip_code": r.get("zip_code"),
                "community_area": r.get("community_area"),
                "ward": ward,
                "latitude": lat,
                "longitude": lng,
                "issue_date": _date_or_none(r.get("issue_date")),
                "expiration_date": _date_or_none(r.get("expiration_date")),
                "reported_cost": cost,
                "source_updated_at": r.get("updated_date"),
            }
        )

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)
    conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Chicago building permits")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Only pull records updated in the last N days (incremental). Omit for full pull.",
    )
    args = parser.parse_args()

    since_date: str | None = None
    if args.days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=args.days)
        since_date = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
        logger.info("Incremental pull: records updated since %s", since_date)
    else:
        logger.info("Full pull: fetching all records")

    records = fetch_pages(since_date=since_date)
    logger.info("Fetched %d total records from source", len(records))

    if not records:
        logger.info("No new records to ingest.")
        return

    with psycopg2.connect(DATABASE_URL) as conn:
        count = upsert_records(conn, records)
    logger.info("Upserted %d records into raw_building_permits.", count)


if __name__ == "__main__":
    main()
