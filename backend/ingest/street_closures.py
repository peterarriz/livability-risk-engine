"""
Ingest Chicago street closure permits from the City of Chicago Data Portal (Socrata).

Dataset: Street Closures (Right-of-Way permits with closure details)
Socrata endpoint: https://data.cityofchicago.org/resource/Ansr-8mav.json

Usage
-----
# Full pull (first run or weekly re-sync):
    python backend/ingest/street_closures.py

# Incremental pull (daily delta, closures active or updated in last N days):
    python backend/ingest/street_closures.py --days 7

Environment variables
---------------------
DATABASE_URL  PostgreSQL connection string (psycopg2 format).
              Defaults to postgresql://localhost/livability if not set.
SOCRATA_APP_TOKEN  Optional Socrata app token to raise rate limits.
"""

import argparse
import logging
import os
from datetime import date, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import requests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SOCRATA_BASE = "https://data.cityofchicago.org/resource/Ansr-8mav.json"
PAGE_SIZE = 1000
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/livability")
APP_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "")


def fetch_pages(since_close_date: str | None = None) -> list[dict]:
    """Fetch all street closure records, optionally filtered to recent closures."""
    headers = {}
    if APP_TOKEN:
        headers["X-App-Token"] = APP_TOKEN

    # Prioritize planned closures: only fetch records whose reopen_date is in the future
    # or whose close_date falls within the recent window.
    where_clauses = []
    if since_close_date:
        where_clauses.append(f"close_date >= '{since_close_date}'")
    else:
        # For a full pull, still focus on non-ancient closures (past 180 days forward).
        cutoff = (date.today() - timedelta(days=180)).isoformat()
        where_clauses.append(f"close_date >= '{cutoff}'")

    where_clause = " AND ".join(where_clauses)

    records: list[dict] = []
    offset = 0
    while True:
        params: dict = {
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "close_date ASC",
            "$where": where_clause,
        }

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
    return value[:10]


def upsert_records(conn, records: list[dict]) -> int:
    """Upsert closure records into raw_street_closures. Returns the count inserted/updated."""
    sql = """
        INSERT INTO raw_street_closures (
            source_id, closure_type, street_name, work_description, permit_type, status,
            address, zip_code, community_area, ward,
            latitude, longitude, location_geom,
            close_date, reopen_date,
            source_updated_at, ingested_at
        ) VALUES (
            %(source_id)s, %(closure_type)s, %(street_name)s, %(work_description)s,
            %(permit_type)s, %(status)s,
            %(address)s, %(zip_code)s, %(community_area)s, %(ward)s,
            %(latitude)s, %(longitude)s,
            CASE
                WHEN %(latitude)s IS NOT NULL AND %(longitude)s IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)
                ELSE NULL
            END,
            %(close_date)s, %(reopen_date)s,
            %(source_updated_at)s, NOW()
        )
        ON CONFLICT (source_id) DO UPDATE SET
            closure_type       = EXCLUDED.closure_type,
            street_name        = EXCLUDED.street_name,
            work_description   = EXCLUDED.work_description,
            permit_type        = EXCLUDED.permit_type,
            status             = EXCLUDED.status,
            address            = EXCLUDED.address,
            zip_code           = EXCLUDED.zip_code,
            community_area     = EXCLUDED.community_area,
            ward               = EXCLUDED.ward,
            latitude           = EXCLUDED.latitude,
            longitude          = EXCLUDED.longitude,
            location_geom      = EXCLUDED.location_geom,
            close_date         = EXCLUDED.close_date,
            reopen_date        = EXCLUDED.reopen_date,
            source_updated_at  = EXCLUDED.source_updated_at,
            ingested_at        = EXCLUDED.ingested_at
        WHERE raw_street_closures.source_updated_at IS DISTINCT FROM EXCLUDED.source_updated_at
           OR raw_street_closures.source_updated_at IS NULL
    """

    rows = []
    for r in records:
        lat = _float_or_none(r.get("latitude") or (r.get("location") or {}).get("latitude"))
        lng = _float_or_none(r.get("longitude") or (r.get("location") or {}).get("longitude"))
        try:
            ward = int(r["ward"]) if r.get("ward") else None
        except (ValueError, TypeError):
            ward = None

        rows.append(
            {
                "source_id": r.get("id") or r.get("permit_number"),
                "closure_type": r.get("closure_type"),
                "street_name": r.get("street_name"),
                "work_description": r.get("work_description"),
                "permit_type": r.get("permit_type"),
                "status": r.get("status"),
                "address": r.get("address"),
                "zip_code": r.get("zip_code"),
                "community_area": r.get("community_area"),
                "ward": ward,
                "latitude": lat,
                "longitude": lng,
                "close_date": _date_or_none(r.get("close_date")),
                "reopen_date": _date_or_none(r.get("reopen_date")),
                "source_updated_at": r.get("updated_date"),
            }
        )

    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)
    conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Chicago street closure permits")
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help=(
            "Only pull closures whose close_date is within the last N days "
            "(incremental). Omit for full pull (last 180 days forward)."
        ),
    )
    args = parser.parse_args()

    since_close_date: str | None = None
    if args.days is not None:
        cutoff = date.today() - timedelta(days=args.days)
        since_close_date = cutoff.isoformat()
        logger.info("Incremental pull: closures with close_date >= %s", since_close_date)
    else:
        logger.info("Full pull: closures from the last 180 days forward")

    records = fetch_pages(since_close_date=since_close_date)
    logger.info("Fetched %d total records from source", len(records))

    if not records:
        logger.info("No new records to ingest.")
        return

    with psycopg2.connect(DATABASE_URL) as conn:
        count = upsert_records(conn, records)
    logger.info("Upserted %d records into raw_street_closures.", count)


if __name__ == "__main__":
    main()
