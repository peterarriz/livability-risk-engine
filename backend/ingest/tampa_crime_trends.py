"""
backend/ingest/tampa_crime_trends.py
task: data-057
lane: data

Ingests Tampa Police Department crime data and calculates 12-month crime trends
by zone/sector.

Source:
  Socrata — opendata.tampa.gov
  Dataset: Tampa Police Department Incidents
  Dataset ID: jcxs-sxan (MUST VERIFY via catalog API)
  Verify: curl "https://opendata.tampa.gov/api/catalog/v1?q=police+incidents&limit=5"

  Key fields (MUST VERIFY field names via --dry-run):
    report_date   — date of incident
    zone          — patrol zone/sector
    latitude      — incident latitude
    longitude     — incident longitude

  If dataset ID or field names are wrong:
    1. curl "https://opendata.tampa.gov/api/catalog/v1?q=crime&limit=10"
    2. Find the active crime/incident dataset and update DATASET_ID below.
    3. Run: python backend/ingest/tampa_crime_trends.py --dry-run

Output:
  data/raw/tampa_crime_trends.json

Usage:
  python backend/ingest/tampa_crime_trends.py
  python backend/ingest/tampa_crime_trends.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SOCRATA_DOMAIN = "opendata.tampa.gov"
# MUST VERIFY dataset ID via: curl "https://opendata.tampa.gov/api/catalog/v1?q=police+incidents&limit=5"
DATASET_ID = "jcxs-sxan"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/tampa_crime_trends.json")

DATE_FIELD = "report_date"     # MUST VERIFY
DISTRICT_FIELD = "zone"        # MUST VERIFY — may be "sector", "beat", or "district"
LAT_FIELD = "latitude"
LON_FIELD = "longitude"

TAMPA_LAT = 27.9506
TAMPA_LON = -82.4572

STABLE_THRESHOLD_PCT = 5.0


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_crime_counts_with_centroids(
    app_token: str | None,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    where_clause = (
        f"{DATE_FIELD} >= '{_date_str(start_date)}' "
        f"AND {DATE_FIELD} < '{_date_str(end_date)}'"
    )
    params: dict = {
        "$select": (
            f"{DISTRICT_FIELD}, "
            "count(*) as crime_count, "
            f"avg({LAT_FIELD} :: number) as avg_lat, "
            f"avg({LON_FIELD} :: number) as avg_lon"
        ),
        "$where": where_clause,
        "$group": DISTRICT_FIELD,
        "$limit": 100,
    }
    if app_token:
        params["$$app_token"] = app_token

    resp = requests.get(CRIMES_URL, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    results: dict[str, dict] = {}
    for row in rows:
        zone = str(row.get(DISTRICT_FIELD, "") or "").strip().upper()
        if not zone:
            continue
        try:
            count = int(row.get("crime_count", 0))
        except (TypeError, ValueError):
            count = 0
        try:
            avg_lat = float(row.get("avg_lat") or 0) or None
        except (TypeError, ValueError):
            avg_lat = None
        try:
            avg_lon = float(row.get("avg_lon") or 0) or None
        except (TypeError, ValueError):
            avg_lon = None
        results[zone] = {"count": count, "lat": avg_lat, "lon": avg_lon}

    return results


def _classify_trend(current: int, prior: int) -> tuple[str, float]:
    if prior == 0:
        if current > 0:
            return "INCREASING", 100.0
        return "STABLE", 0.0
    pct = (current - prior) / prior * 100.0
    if pct >= STABLE_THRESHOLD_PCT:
        return "INCREASING", round(pct, 1)
    if pct <= -STABLE_THRESHOLD_PCT:
        return "DECREASING", round(pct, 1)
    return "STABLE", round(pct, 1)


def build_trend_records(
    current_data: dict[str, dict],
    prior_data: dict[str, dict],
) -> list[dict]:
    all_zones = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for zone in sorted(all_zones):
        curr = current_data.get(zone, {"count": 0, "lat": None, "lon": None})
        prev = prior_data.get(zone, {"count": 0, "lat": None, "lon": None})
        current_count = curr["count"]
        prior_count = prev["count"]
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat = curr["lat"] or prev["lat"]
        lon = curr["lon"] or prev["lon"]
        records.append({
            "region_type": "zone",
            "region_id": f"tampa_zone_{zone}",
            "district_id": zone,
            "district_name": f"Tampa Zone {zone}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": lat or TAMPA_LAT,
            "longitude": lon or TAMPA_LON,
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "tampa_crime_trends",
        "source_url": CRIMES_URL,
        "ingested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "record_count": len(records),
        "records": records,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(staging, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(records)} records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Tampa PD crime trends by zone from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch data but do not write output file.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app_token = os.environ.get("SOCRATA_APP_TOKEN")

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Tampa crime counts...")
    try:
        current_data = fetch_crime_counts_with_centroids(app_token, current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current Tampa crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(current_data)} zones with current crime data.")

    print(f"Fetching prior 12-month Tampa crime counts...")
    try:
        prior_data = fetch_crime_counts_with_centroids(app_token, prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior Tampa crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(prior_data)} zones with prior crime data.")

    records = build_trend_records(current_data, prior_data)
    print(f"\nBuilt {len(records)} zone trend records.")

    if args.dry_run:
        print("Dry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
