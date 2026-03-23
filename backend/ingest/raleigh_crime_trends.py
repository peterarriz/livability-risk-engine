"""
backend/ingest/raleigh_crime_trends.py
task: data-050
lane: data

Ingests Raleigh Police Department crime data and calculates 12-month
crime trends by district.

Source:
  Socrata — data.raleighnc.gov (Raleigh Open Data Portal)
  Dataset: Raleigh Police Incidents (NIBRS)

  Dataset ID: d9dc-ixwq (MUST VERIFY — run discover to confirm)

  Verify dataset ID:
    curl "https://data.raleighnc.gov/api/catalog/v1?q=police+incident&limit=5"
    curl "https://data.raleighnc.gov/resource/d9dc-ixwq.json?$limit=1"

  Key fields (MUST VERIFY via sample query):
    reported_block_address — address
    reported_date          — ISO 8601 datetime string
    district               — police district
    latitude, longitude    — coordinates

Method:
  1. Aggregate crime counts by district for the last 12 months.
  2. Aggregate crime counts by district for the prior 12 months.
  3. Calculate percent change → crime_trend: INCREASING / DECREASING / STABLE.
  4. Compute approximate district centroids from average lat/lon.

Output:
  data/raw/raleigh_crime_trends.json — district crime trend records

Usage:
  python backend/ingest/raleigh_crime_trends.py
  python backend/ingest/raleigh_crime_trends.py --dry-run

Environment variables (optional):
  SOCRATA_APP_TOKEN  — increases Socrata API rate limits
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

# MUST VERIFY: run the following to confirm the correct dataset ID:
#   curl "https://data.raleighnc.gov/api/catalog/v1?q=police+incident&limit=5"
SOCRATA_DOMAIN = "data.raleighnc.gov"
DATASET_ID = "d9dc-ixwq"
CRIMES_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

DEFAULT_OUTPUT_PATH = Path("data/raw/raleigh_crime_trends.json")

# MUST VERIFY field names via sample query:
#   curl "https://data.raleighnc.gov/resource/d9dc-ixwq.json?$limit=1"
DATE_FIELD = "reported_date"
GROUP_FIELD = "district"

RALEIGH_LAT = 35.7796
RALEIGH_LON = -78.6382

STABLE_THRESHOLD_PCT = 5.0
PAGE_SIZE = 50000


def fetch_crime_counts(
    start_date: datetime,
    end_date: datetime,
) -> tuple[dict[str, int], dict[str, tuple[float, float]]]:
    """
    Fetch crime counts grouped by district, plus centroid coordinates.
    Returns (counts_by_district, centroids_by_district).
    """
    app_token = os.environ.get("SOCRATA_APP_TOKEN", "")
    headers = {"X-App-Token": app_token} if app_token else {}

    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%S")

    select_clause = (
        f"count(*) as crime_count,"
        f" avg(latitude) as centroid_lat,"
        f" avg(longitude) as centroid_lon,"
        f" {GROUP_FIELD}"
    )

    params = {
        "$select": select_clause,
        "$where": (
            f"{DATE_FIELD} >= '{start_str}' "
            f"AND {DATE_FIELD} < '{end_str}' "
            f"AND {GROUP_FIELD} IS NOT NULL"
        ),
        "$group": GROUP_FIELD,
        "$limit": PAGE_SIZE,
    }

    resp = requests.get(CRIMES_URL, headers=headers, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()

    counts: dict[str, int] = {}
    centroids: dict[str, tuple[float, float]] = {}
    for row in rows:
        district = str(row.get(GROUP_FIELD) or "").strip().upper()
        if not district:
            continue
        counts[district] = counts.get(district, 0) + int(row.get("crime_count", 0))
        try:
            lat = float(row.get("centroid_lat") or RALEIGH_LAT)
            lon = float(row.get("centroid_lon") or RALEIGH_LON)
        except (TypeError, ValueError):
            lat, lon = RALEIGH_LAT, RALEIGH_LON
        centroids[district] = (lat, lon)

    return counts, centroids


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
    current_data: dict[str, int],
    prior_data: dict[str, int],
    centroids: dict[str, tuple[float, float]],
) -> list[dict]:
    all_districts = set(current_data.keys()) | set(prior_data.keys())
    records = []
    for district in sorted(all_districts):
        current_count = current_data.get(district, 0)
        prior_count = prior_data.get(district, 0)
        trend, trend_pct = _classify_trend(current_count, prior_count)
        lat, lon = centroids.get(district, (RALEIGH_LAT, RALEIGH_LON))
        slug = district.lower().replace(" ", "_").replace("-", "_")
        records.append({
            "region_type": "district",
            "region_id": f"raleigh_district_{slug}",
            "district_id": district,
            "district_name": f"Raleigh Police District {district}",
            "crime_12mo": current_count,
            "crime_prior_12mo": prior_count,
            "crime_trend": trend,
            "crime_trend_pct": trend_pct,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        })
    return records


def write_staging_file(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = {
        "source": "raleigh_crime_trends",
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
        description="Ingest Raleigh PD crime trends by district from Socrata."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=365)
    prior_start = now - timedelta(days=730)
    prior_end = current_start

    print(f"Fetching current 12-month Raleigh crime counts "
          f"({current_start:%Y-%m-%d} → {now:%Y-%m-%d})...")
    try:
        current_data, centroids = fetch_crime_counts(current_start, now)
    except Exception as exc:
        print(f"ERROR: failed to fetch current crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_current = sum(current_data.values())
    print(f"  {len(current_data)} districts, {total_current:,} total crimes.")

    print(f"\nFetching prior 12-month Raleigh crime counts "
          f"({prior_start:%Y-%m-%d} → {prior_end:%Y-%m-%d})...")
    try:
        prior_data, prior_centroids = fetch_crime_counts(prior_start, prior_end)
    except Exception as exc:
        print(f"ERROR: failed to fetch prior crime counts — {exc}", file=sys.stderr)
        sys.exit(1)
    total_prior = sum(prior_data.values())
    print(f"  {len(prior_data)} districts, {total_prior:,} total crimes.")

    for district, coords in prior_centroids.items():
        if district not in centroids:
            centroids[district] = coords

    records = build_trend_records(current_data, prior_data, centroids)
    print(f"\nBuilt {len(records)} district trend records.")

    trend_counts: dict[str, int] = {}
    for r in records:
        t = r["crime_trend"]
        trend_counts[t] = trend_counts.get(t, 0) + 1
    for trend, count in sorted(trend_counts.items()):
        print(f"  {trend}: {count} districts")

    if args.dry_run:
        print("\nDry-run mode: skipping file write.")
        if records:
            print(f"Sample record:\n{json.dumps(records[0], indent=2)}")
        return

    write_staging_file(records, args.output)
    print("Done.")


if __name__ == "__main__":
    main()
